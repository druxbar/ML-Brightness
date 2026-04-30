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
    CONF_TRANSITION_SECONDS,
    CONF_DONT_TURN_ON,
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


async def apply_recommendations(
    hass: HomeAssistant,
    entry: ConfigEntry,
    store: MLBrightnessStore,
    last_set: dict[str, tuple[datetime, int | None]],
    last_manual: dict[str, datetime],
    pred_hold: dict[str, tuple[float, int]] | None = None,
) -> Recommendation:
    if not entry.data.get(CONF_ENABLE_AUTO, True):
        return Recommendation(None, None)

    now = datetime.now(timezone.utc)

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

    context_entities = list(entry.data.get(CONF_CONTEXT_ENTITIES) or [])
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
    model_type = entry.data.get(CONF_MODEL_TYPE, MODEL_KNN_MEDIAN)

    # CT clamp maps
    ct_min_global = entry.data.get(CONF_CT_MIN)
    ct_max_global = entry.data.get(CONF_CT_MAX)
    ct_by_area = entry.data.get(CONF_CT_BOUNDS_BY_AREA) or {}
    ct_by_light = entry.data.get(CONF_CT_BOUNDS_BY_LIGHT) or {}

    # v0 recommendation sensor: average across target lights (if any model exists)
    rec_values: list[float] = []
    conf_values: list[float] = []

    for light in sorted(lights):
        st = hass.states.get(light)
        if not st or st.state in ("unknown", "unavailable"):
            continue

        if dont_turn_on and st.state == "off":
            continue

        # cooldown after manual
        lm = last_manual.get(light)
        if lm and (now - lm).total_seconds() < cooldown:
            continue

        cur_pct = _pct_from_brightness(st.attributes.get("brightness"))
        if cur_pct is None:
            continue

        model_state = store.data.by_light.get(light)
        if model_state is None:
            model_state = LightModelState(w=[], p=[], n=0)
            store.data.by_light[light] = model_state

        if model_type == MODEL_KNN_MEDIAN:
            yhat, conf = _knn_predict_median(model_state.examples, x)
            if yhat is None:
                yhat = _clamp(predict(model_state.w, x), 0.0, 100.0)
                conf = 0.0
        else:
            yhat = _clamp(predict(model_state.w, x), 0.0, 100.0)
            conf = 1.0 - math.exp(-float(model_state.n) / 40.0)

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

