from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, Context
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.sun import get_astral_event_date

from .const import (
    CONF_AREAS,
    CONF_AUTODISCOVER_CONTEXT,
    CONF_CONTEXT_BLACKLIST,
    CONF_CONTEXT_BLACKLIST_DOMAINS,
    CONF_CONTEXT_ENTITIES,
    CONF_COOLDOWN_SECONDS,
    CONF_CT_BOUNDS_BY_AREA,
    CONF_CT_BOUNDS_BY_LIGHT,
    CONF_CT_MAX,
    CONF_CT_MIN,
    CONF_ENABLE_AUTO,
    CONF_HYSTERESIS,
    CONF_LIGHTS,
    CONF_LUX_ENTITIES,
    CONF_MAX_DELTA_PER_MIN,
    CONF_PRESENCE_ENTITIES,
    CONF_PRESENCE_BY_AREA,
    CONF_TRANSITION_SECONDS,
    CONF_DONT_TURN_ON,
    CONF_TURN_ON_ON_PRESENCE,
    CONF_NIGHT_SLOW_FACTOR,
    CONF_NIGHT_TRANSITION_SECONDS,
    CONF_SLEEP_START,
    CONF_SLEEP_END,
    CONF_SLEEP_MAX_BRIGHTNESS_PCT,
    CONF_SLEEP_SLOW_FACTOR,
    CONF_MODEL_TYPE,
    MODEL_KNN_MEDIAN,
    MODEL_RIDGE,
)
from .model import ModelConfig, online_update_diag, predict
from .storage import MLBrightnessStore, LightModelState


@dataclass(frozen=True)
class Recommendation:
    recommended_brightness_pct: float | None
    confidence: float | None


def _pct_from_brightness(brightness: int | None) -> float | None:
    if brightness is None:
        return None
    return max(0.0, min(100.0, brightness * 100.0 / 255.0))


def _brightness_from_pct(pct: float) -> int:
    return int(max(0.0, min(255.0, round(pct * 255.0 / 100.0))))


def _circadian_mired(now: datetime, sun_elev: float | None) -> int:
    # 153..500 typical. Warm at night, cool at day.
    if sun_elev is None:
        # fallback by hour
        h = now.hour + now.minute / 60.0
        if 7 <= h <= 18:
            return 250
        if 18 < h <= 23:
            return 350
        return 450

    if sun_elev >= 25:
        return 220
    if sun_elev >= 5:
        return 280
    if sun_elev >= -6:
        return 340
    return 430


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

def _weighted_median(pairs: list[tuple[float, float]]) -> float | None:
    if not pairs:
        return None
    pairs = sorted(pairs, key=lambda t: t[0])
    total = sum(w for _, w in pairs)
    if total <= 0:
        return pairs[len(pairs) // 2][0]
    acc = 0.0
    for y, w in pairs:
        acc += w
        if acc >= total * 0.5:
            return y
    return pairs[-1][0]


def _knn_predict_median(examples: list[dict], x: list[float]) -> tuple[float | None, float]:
    if not examples:
        return None, 0.0
    scored: list[tuple[float, float]] = []
    for ex in examples[-250:]:
        xv = ex.get("x")
        yv = ex.get("y")
        if not isinstance(xv, list) or yv is None:
            continue
        d = 0.0
        for i in range(min(len(x), len(xv))):
            di = float(x[i]) - float(xv[i])
            d += di * di
        d = math.sqrt(d)
        w = 1.0 / (0.15 + d)
        scored.append((float(yv), w))
    # take top-k by weight (closest)
    scored.sort(key=lambda t: t[1], reverse=True)
    top = scored[:25]
    pred = _weighted_median(top)
    conf = min(1.0, len(top) / 40.0)
    return pred, conf


def _extract_features(
    *,
    hass: HomeAssistant,
    now: datetime,
    sun_elev: float | None,
    presence_any: bool | None,
    lux: float | None,
    context_on_ratio: float | None,
) -> list[float]:
    # fixed dim features: time cyc (2), sun elev (1), presence (1), log1p(lux) (1), context_on_ratio (1)
    t = now.hour + now.minute / 60.0
    ang = 2.0 * math.pi * (t / 24.0)
    f_time_sin = math.sin(ang)
    f_time_cos = math.cos(ang)
    f_sun = (sun_elev or 0.0) / 90.0
    f_presence = 1.0 if presence_any else 0.0
    f_lux = math.log1p(max(0.0, lux or 0.0)) / 10.0
    f_ctx = context_on_ratio if context_on_ratio is not None else 0.0
    return [f_time_sin, f_time_cos, f_sun, f_presence, f_lux, f_ctx]


def _is_night(now: datetime, sun_elev: float | None) -> bool:
    if sun_elev is not None:
        return sun_elev < -6.0
    return now.hour < 6 or now.hour >= 23


def _autodiscover_context_entities(
    hass: HomeAssistant,
    area_ids: set[str],
    blacklist: set[str],
    blacklist_domains: set[str],
    cap: int = 60,
) -> list[str]:
    if not area_ids:
        return []
    ent_reg = er.async_get(hass)
    out: list[str] = []
    for ent in ent_reg.entities.values():
        if ent.area_id not in area_ids:
            continue
        if ent.domain in ("light", "sensor", "binary_sensor") and ent.entity_id.startswith("sensor.ml_brightness"):
            continue
        if ent.domain in ("light", "sun"):
            continue
        if ent.domain in blacklist_domains:
            continue
        if ent.entity_id in blacklist:
            continue
        out.append(ent.entity_id)
        if len(out) >= cap:
            break
    return out


def _parse_hhmm(s: str) -> tuple[int, int] | None:
    try:
        parts = s.strip().split(":")
        if len(parts) != 2:
            return None
        h = int(parts[0])
        m = int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            return None
        return h, m
    except Exception:
        return None


def _in_window(now: datetime, start: str, end: str) -> bool:
    st = _parse_hhmm(start)
    en = _parse_hhmm(end)
    if not st or not en:
        return False
    cur = now.hour * 60 + now.minute
    s = st[0] * 60 + st[1]
    e = en[0] * 60 + en[1]
    if s == e:
        return False
    if s < e:
        return s <= cur < e
    return cur >= s or cur < e


async def apply_recommendations(
    hass: HomeAssistant,
    entry: ConfigEntry,
    store: MLBrightnessStore,
    last_set: dict[str, tuple[datetime, int | None]],
    last_manual: dict[str, datetime],
    pred_hold: dict[str, tuple[float, int]] | None = None,
    override_until: datetime | None = None,
) -> Recommendation:
    if not entry.data.get(CONF_ENABLE_AUTO, True):
        return Recommendation(None, None)

    now = datetime.now(timezone.utc)
    if override_until and now < override_until:
        return Recommendation(None, None)

    lights: set[str] = set(entry.data.get(CONF_LIGHTS) or [])
    area_ids = set(entry.data.get(CONF_AREAS) or [])
    if area_ids:
        ent_reg = er.async_get(hass)
        for ent in ent_reg.entities.values():
            if ent.domain == "light" and ent.area_id in area_ids:
                lights.add(ent.entity_id)
    if not lights:
        return Recommendation(None, None)

    # gather optional signals (global, coarse)
    presence_entities = list(entry.data.get(CONF_PRESENCE_ENTITIES) or [])
    presence_by_area = entry.data.get(CONF_PRESENCE_BY_AREA) or {}
    presence_any: bool | None = None
    if presence_entities:
        presence_any = any(
            (st := hass.states.get(e)) is not None and st.state not in ("off", "0", "false", "unknown", "unavailable")
            for e in presence_entities
        )

    lux_entities = list(entry.data.get(CONF_LUX_ENTITIES) or [])
    lux: float | None = None
    for e in lux_entities:
        st = hass.states.get(e)
        if st and st.state not in ("unknown", "unavailable"):
            try:
                lux = float(st.state)
                break
            except ValueError:
                continue

    blacklist = set(entry.data.get(CONF_CONTEXT_BLACKLIST) or [])
    blacklist_domains = set(entry.data.get(CONF_CONTEXT_BLACKLIST_DOMAINS) or [])
    context_entities = [e for e in (entry.data.get(CONF_CONTEXT_ENTITIES) or []) if e not in blacklist]
    if entry.data.get(CONF_AUTODISCOVER_CONTEXT, True):
        auto_ctx = _autodiscover_context_entities(hass, area_ids, blacklist, blacklist_domains)
        # union, stable order
        seen = set(context_entities)
        for e in auto_ctx:
            if e not in seen:
                context_entities.append(e)
                seen.add(e)
    context_on_ratio: float | None = None
    if context_entities:
        on = 0
        known = 0
        for e in context_entities:
            st = hass.states.get(e)
            if not st or st.state in ("unknown", "unavailable"):
                continue
            known += 1
            if st.state not in ("off", "0", "false"):
                on += 1
        if known:
            context_on_ratio = on / known

    sun = hass.states.get("sun.sun")
    sun_elev: float | None = None
    if sun and sun.attributes.get("elevation") is not None:
        try:
            sun_elev = float(sun.attributes["elevation"])
        except (TypeError, ValueError):
            sun_elev = None

    x = _extract_features(
        hass=hass,
        now=now,
        sun_elev=sun_elev,
        presence_any=presence_any,
        lux=lux,
        context_on_ratio=context_on_ratio,
    )
    cfg = ModelConfig(dim=len(x), ridge=1.0, huber_k=12.0)

    cooldown = int(entry.data.get(CONF_COOLDOWN_SECONDS, 180))
    hysteresis = float(entry.data.get(CONF_HYSTERESIS, 3.0))
    max_delta_per_min = float(entry.data.get(CONF_MAX_DELTA_PER_MIN, 25.0))
    transition_s = int(entry.data.get(CONF_TRANSITION_SECONDS, 2))
    dont_turn_on = bool(entry.data.get(CONF_DONT_TURN_ON, True))
    turn_on_on_presence = bool(entry.data.get(CONF_TURN_ON_ON_PRESENCE, True))
    night_slow_factor = float(entry.data.get(CONF_NIGHT_SLOW_FACTOR, 0.25))
    night_transition_s = int(entry.data.get(CONF_NIGHT_TRANSITION_SECONDS, 8))
    model_type = entry.data.get(CONF_MODEL_TYPE, MODEL_KNN_MEDIAN)

    # CT clamp maps
    ct_min_global = entry.data.get(CONF_CT_MIN)
    ct_max_global = entry.data.get(CONF_CT_MAX)
    ct_by_area = entry.data.get(CONF_CT_BOUNDS_BY_AREA) or {}
    ct_by_light = entry.data.get(CONF_CT_BOUNDS_BY_LIGHT) or {}

    # v0 recommendation sensor: average across target lights (if any model exists)
    rec_values: list[float] = []
    conf_values: list[float] = []

    night = _is_night(now, sun_elev)
    if night:
        max_delta_per_min = max(0.1, max_delta_per_min * night_slow_factor)
        transition_s = max(transition_s, night_transition_s)

    # sleep window (extra clamp + extra slow)
    sleep_start = entry.data.get(CONF_SLEEP_START, "23:00")
    sleep_end = entry.data.get(CONF_SLEEP_END, "06:00")
    if _in_window(now, sleep_start, sleep_end):
        sleep_cap = float(entry.data.get(CONF_SLEEP_MAX_BRIGHTNESS_PCT, 35.0))
        sleep_slow = float(entry.data.get(CONF_SLEEP_SLOW_FACTOR, 0.20))
        max_delta_per_min = max(0.05, max_delta_per_min * sleep_slow)
    else:
        sleep_cap = None

    for light in sorted(lights):
        st = hass.states.get(light)
        if not st or st.state in ("unknown", "unavailable"):
            continue

        ent_reg = er.async_get(hass)
        ent = ent_reg.async_get(light)
        area_id = ent.area_id if ent else None

        # per-area presence gate (if configured)
        presence_ok = presence_any
        if area_id and isinstance(presence_by_area, dict) and area_id in presence_by_area:
            ents = presence_by_area.get(area_id) or []
            if isinstance(ents, list) and ents:
                presence_ok = any(
                    (pst := hass.states.get(e)) is not None
                    and pst.state not in ("off", "0", "false", "unknown", "unavailable")
                    for e in ents
                )

        if st.state == "off" and (dont_turn_on or not (turn_on_on_presence and presence_ok)):
            continue

        # cooldown after manual
        lm = last_manual.get(light)
        if lm and (now - lm).total_seconds() < cooldown:
            continue

        cur_pct = _pct_from_brightness(st.attributes.get("brightness"))
        if cur_pct is None:
            cur_pct = 0.0 if st.state == "off" else None
        if cur_pct is None:
            continue

        model_state = store.data.by_light.get(light)
        if model_state is None:
            model_state = LightModelState(w=[], p=[], n=0)
            store.data.by_light[light] = model_state

        area_state = store.data.by_area.get(area_id) if area_id else None

        if model_type == MODEL_KNN_MEDIAN:
            y_l, c_l = _knn_predict_median(model_state.examples, x)
            y_a, c_a = _knn_predict_median(area_state.examples, x) if area_state else (None, 0.0)
            if y_l is None and y_a is None:
                yhat = _clamp(predict(model_state.w, x), 0.0, 100.0)
                conf = 0.0
            elif y_l is None:
                yhat = float(y_a)
                conf = float(c_a)
            elif y_a is None:
                yhat = float(y_l)
                conf = float(c_l)
            else:
                # blend by confidence; prefer area when light has little data
                wl = 0.35 + 0.65 * c_l
                wa = 0.65 + 0.35 * c_a
                yhat = (wl * float(y_l) + wa * float(y_a)) / (wl + wa)
                conf = max(c_l, c_a)
            if yhat is None:
                yhat = _clamp(predict(model_state.w, x), 0.0, 100.0)
                conf = 0.0
        else:
            y_l = _clamp(predict(model_state.w, x), 0.0, 100.0)
            c_l = 1.0 - math.exp(-float(model_state.n) / 40.0)
            if area_state:
                y_a = _clamp(predict(area_state.w, x), 0.0, 100.0)
                c_a = 1.0 - math.exp(-float(area_state.n) / 60.0)
                yhat = (0.35 * y_l + 0.65 * y_a)
                conf = max(c_l, c_a)
            else:
                yhat = y_l
                conf = c_l

        if sleep_cap is not None:
            yhat = min(float(sleep_cap), float(yhat))

        # smoothing: hysteresis + rate limit
        if abs(yhat - cur_pct) <= hysteresis:
            rec_values.append(yhat)
            conf_values.append(conf)
            continue

        # debounce: require target stable across 2 cycles
        if pred_hold is not None:
            prev = pred_hold.get(light)
            if prev is None or abs(prev[0] - yhat) > 1.5:
                pred_hold[light] = (yhat, 1)
                rec_values.append(yhat)
                conf_values.append(conf)
                continue
            pred_hold[light] = (yhat, prev[1] + 1)
            if prev[1] + 1 < 2:
                rec_values.append(yhat)
                conf_values.append(conf)
                continue

        last = last_set.get(light)
        if last:
            dt_min = max(0.01, (now - last[0]).total_seconds() / 60.0)
        else:
            dt_min = 1.0
        max_step = max_delta_per_min * dt_min
        target_pct = cur_pct + _clamp(yhat - cur_pct, -max_step, max_step)

        # apply brightness + CT (if supported)
        service_data = {"entity_id": light, "brightness": _brightness_from_pct(target_pct)}
        if transition_s > 0:
            service_data["transition"] = transition_s

        ct_target = _circadian_mired(now, sun_elev)
        ct_min = None
        ct_max = None
        if isinstance(ct_by_light, dict) and light in ct_by_light and isinstance(ct_by_light[light], dict):
            ct_min = ct_by_light[light].get("ct_min")
            ct_max = ct_by_light[light].get("ct_max")
        # area bounds (if we can map)
        if ct_min is None or ct_max is None:
            ent_reg = er.async_get(hass)
            ent = ent_reg.async_get(light)
            if ent and ent.area_id and isinstance(ct_by_area, dict) and ent.area_id in ct_by_area:
                area_cfg = ct_by_area.get(ent.area_id) or {}
                ct_min = ct_min if ct_min is not None else area_cfg.get("ct_min")
                ct_max = ct_max if ct_max is not None else area_cfg.get("ct_max")
        if ct_min is None:
            ct_min = ct_min_global
        if ct_max is None:
            ct_max = ct_max_global

        if ct_min is not None or ct_max is not None:
            ct_target_f = float(ct_target)
            if ct_min is not None:
                ct_target_f = max(float(ct_min), ct_target_f)
            if ct_max is not None:
                ct_target_f = min(float(ct_max), ct_target_f)
            service_data["color_temp"] = int(round(ct_target_f))

        ctx = Context()
        await hass.services.async_call("light", "turn_on", service_data, blocking=False, context=ctx)
        last_set[light] = (now, st.attributes.get("brightness"))

        rec_values.append(yhat)
        conf_values.append(conf)

        # training: if user manually moved, update model from current brightness
        # (learn only from manual events; here only minor catch-up if context changes)

        model_state.n += 0  # keep counter in one place (manual training)

    # persist store occasionally (cheap; v0 always)
    await store.async_save()

    if not rec_values:
        return Recommendation(None, None)
    return Recommendation(
        recommended_brightness_pct=sum(rec_values) / len(rec_values),
        confidence=sum(conf_values) / len(conf_values) if conf_values else None,
    )

