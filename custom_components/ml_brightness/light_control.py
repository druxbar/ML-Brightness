from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, Context
from homeassistant.helpers import entity_registry as er

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
    entry_cfg,
)
from .model import ModelConfig, predict
from .storage import MLBrightnessStore, LightModelState
from .utils import clamp, in_time_window, knn_predict_median


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
    if sun_elev is None:
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


def _extract_features(
    *,
    hass: HomeAssistant,
    now: datetime,
    sun_elev: float | None,
    presence_any: bool | None,
    lux: float | None,
    context_on_ratio: float | None,
) -> list[float]:
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


def presence_union_for_features(hass: HomeAssistant, cfg: dict, area_ids: set[str]) -> bool | None:
    """OR global presence + per-area presence for configured areas. None if no presence configured."""
    ents_g = list(cfg.get(CONF_PRESENCE_ENTITIES) or [])
    by_area = cfg.get(CONF_PRESENCE_BY_AREA) or {}
    has_cfg = bool(ents_g) or (isinstance(by_area, dict) and len(by_area) > 0)
    if not has_cfg:
        return None

    active = False
    if ents_g:
        active = active or any(
            (st := hass.states.get(e)) is not None
            and st.state not in ("off", "0", "false", "unknown", "unavailable")
            for e in ents_g
        )
    if isinstance(by_area, dict) and area_ids:
        for aid in area_ids:
            if aid not in by_area:
                continue
            ents = by_area.get(aid) or []
            if not isinstance(ents, list):
                continue
            active = active or any(
                (pst := hass.states.get(e)) is not None
                and pst.state not in ("off", "0", "false", "unknown", "unavailable")
                for e in ents
            )
    return active


def presence_ok_for_light(
    hass: HomeAssistant,
    cfg: dict,
    light_id: str,
    *,
    presence_by_area: dict | None = None,
    presence_any: bool | None = None,
) -> bool | None:
    """Same presence gate as turn-on path: per-area list if set, else global union."""
    ent_reg = er.async_get(hass)
    ent = ent_reg.async_get(light_id)
    area_id = ent.area_id if ent else None
    pba = presence_by_area if presence_by_area is not None else (cfg.get(CONF_PRESENCE_BY_AREA) or {})
    pany = presence_any if presence_any is not None else presence_union_for_features(
        hass, cfg, set(cfg.get(CONF_AREAS) or [])
    )
    presence_ok = pany
    if area_id and isinstance(pba, dict) and area_id in pba:
        ents = pba.get(area_id) or []
        if isinstance(ents, list) and ents:
            presence_ok = any(
                (pst := hass.states.get(e)) is not None
                and pst.state not in ("off", "0", "false", "unknown", "unavailable")
                for e in ents
            )
    return presence_ok


def _autodiscover_context_entities(
    hass: HomeAssistant,
    area_ids: set[str],
    blacklist: set[str],
    blacklist_domains: set[str],
    *,
    config_entry_id: str | None,
    cap: int = 60,
) -> list[str]:
    if not area_ids:
        return []
    ent_reg = er.async_get(hass)
    out: list[str] = []
    for ent in ent_reg.entities.values():
        if ent.area_id not in area_ids:
            continue
        if config_entry_id and ent.config_entry_id == config_entry_id:
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


def _light_supports_brightness(st) -> bool:
    modes = set(st.attributes.get("supported_color_modes") or [])
    if not modes:
        return True
    return "brightness" in modes or "rgb" in modes or "rgbw" in modes or "rgbww" in modes


def _light_supports_color_temp(st) -> bool:
    modes = set(st.attributes.get("supported_color_modes") or [])
    if not modes:
        return False
    return "color_temp" in modes


async def apply_recommendations(
    hass: HomeAssistant,
    entry: ConfigEntry,
    store: MLBrightnessStore,
    last_set: dict[str, tuple[datetime, int | None]],
    last_manual: dict[str, datetime],
    pred_hold: dict[str, tuple[float, int]] | None = None,
    override_until: datetime | None = None,
    ml_context_ids: list[str] | None = None,
) -> Recommendation:
    cfg = entry_cfg(entry)
    if not cfg.get(CONF_ENABLE_AUTO, True):
        return Recommendation(None, None)

    now = datetime.now(timezone.utc)
    if override_until and now < override_until:
        return Recommendation(None, None)

    lights: set[str] = set(cfg.get(CONF_LIGHTS) or [])
    area_ids = set(cfg.get(CONF_AREAS) or [])
    if area_ids:
        ent_reg = er.async_get(hass)
        for ent in ent_reg.entities.values():
            if ent.domain == "light" and ent.area_id in area_ids:
                lights.add(ent.entity_id)
    if not lights:
        return Recommendation(None, None)

    presence_by_area = cfg.get(CONF_PRESENCE_BY_AREA) or {}
    presence_any = presence_union_for_features(hass, cfg, area_ids)

    lux_entities = list(cfg.get(CONF_LUX_ENTITIES) or [])
    lux: float | None = None
    for e in lux_entities:
        st = hass.states.get(e)
        if st and st.state not in ("unknown", "unavailable"):
            try:
                lux = float(st.state)
                break
            except ValueError:
                continue

    blacklist = set(cfg.get(CONF_CONTEXT_BLACKLIST) or [])
    bd = cfg.get(CONF_CONTEXT_BLACKLIST_DOMAINS) or []
    blacklist_domains = set(bd) if isinstance(bd, (list, set, tuple)) else set()
    context_entities = [e for e in (cfg.get(CONF_CONTEXT_ENTITIES) or []) if e not in blacklist]
    if cfg.get(CONF_AUTODISCOVER_CONTEXT, True):
        auto_ctx = _autodiscover_context_entities(
            hass,
            area_ids,
            blacklist,
            blacklist_domains,
            config_entry_id=entry.entry_id,
        )
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

    cooldown = int(cfg.get(CONF_COOLDOWN_SECONDS, 180))
    hysteresis = float(cfg.get(CONF_HYSTERESIS, 3.0))
    max_delta_per_min = float(cfg.get(CONF_MAX_DELTA_PER_MIN, 25.0))
    transition_s = int(cfg.get(CONF_TRANSITION_SECONDS, 2))
    dont_turn_on = bool(cfg.get(CONF_DONT_TURN_ON, True))
    turn_on_on_presence = bool(cfg.get(CONF_TURN_ON_ON_PRESENCE, True))
    night_slow_factor = float(cfg.get(CONF_NIGHT_SLOW_FACTOR, 0.25))
    night_transition_s = int(cfg.get(CONF_NIGHT_TRANSITION_SECONDS, 8))
    model_type = cfg.get(CONF_MODEL_TYPE, MODEL_KNN_MEDIAN)

    ct_min_global = cfg.get(CONF_CT_MIN)
    ct_max_global = cfg.get(CONF_CT_MAX)
    ct_by_area = cfg.get(CONF_CT_BOUNDS_BY_AREA) or {}
    ct_by_light = cfg.get(CONF_CT_BOUNDS_BY_LIGHT) or {}

    rec_values: list[float] = []
    conf_values: list[float] = []

    night = _is_night(now, sun_elev)
    if night:
        max_delta_per_min = max(0.1, max_delta_per_min * night_slow_factor)
        transition_s = max(transition_s, night_transition_s)

    sleep_start = cfg.get(CONF_SLEEP_START, "23:00")
    sleep_end = cfg.get(CONF_SLEEP_END, "06:00")
    if in_time_window(now, str(sleep_start), str(sleep_end)):
        sleep_cap = float(cfg.get(CONF_SLEEP_MAX_BRIGHTNESS_PCT, 35.0))
        sleep_slow = float(cfg.get(CONF_SLEEP_SLOW_FACTOR, 0.20))
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

        presence_ok = presence_ok_for_light(
            hass, cfg, light, presence_by_area=presence_by_area, presence_any=presence_any
        )

        if st.state == "off":
            if not _light_supports_brightness(st) and not _light_supports_color_temp(st):
                continue
            if dont_turn_on or not (turn_on_on_presence and bool(presence_ok)):
                continue

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
            y_l, c_l = knn_predict_median(model_state.examples, x)
            y_a, c_a = knn_predict_median(area_state.examples, x) if area_state else (None, 0.0)
            if y_l is None and y_a is None:
                yhat = clamp(predict(model_state.w, x), 0.0, 100.0)
                conf = 0.0
            elif y_l is None:
                yhat = float(y_a)
                conf = float(c_a)
            elif y_a is None:
                yhat = float(y_l)
                conf = float(c_l)
            else:
                wl = 0.35 + 0.65 * c_l
                wa = 0.65 + 0.35 * c_a
                yhat = (wl * float(y_l) + wa * float(y_a)) / (wl + wa)
                conf = max(c_l, c_a)
            if yhat is None:
                yhat = clamp(predict(model_state.w, x), 0.0, 100.0)
                conf = 0.0
        else:
            y_l = clamp(predict(model_state.w, x), 0.0, 100.0)
            c_l = 1.0 - math.exp(-float(model_state.n) / 40.0)
            if area_state:
                y_a = clamp(predict(area_state.w, x), 0.0, 100.0)
                c_a = 1.0 - math.exp(-float(area_state.n) / 60.0)
                yhat = 0.35 * y_l + 0.65 * y_a
                conf = max(c_l, c_a)
            else:
                yhat = y_l
                conf = c_l

        if sleep_cap is not None:
            yhat = min(float(sleep_cap), float(yhat))

        if abs(yhat - cur_pct) <= hysteresis:
            rec_values.append(yhat)
            conf_values.append(conf)
            continue

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
        target_pct = cur_pct + clamp(yhat - cur_pct, -max_step, max_step)

        service_data: dict = {"entity_id": light}
        if _light_supports_brightness(st):
            service_data["brightness"] = _brightness_from_pct(target_pct)
        elif st.state == "off":
            continue
        if transition_s > 0:
            service_data["transition"] = transition_s

        if _light_supports_color_temp(st):
            ct_target = _circadian_mired(now, sun_elev)
            ct_min = None
            ct_max = None
            if isinstance(ct_by_light, dict) and light in ct_by_light and isinstance(ct_by_light[light], dict):
                ct_min = ct_by_light[light].get("ct_min")
                ct_max = ct_by_light[light].get("ct_max")
            if ct_min is None or ct_max is None:
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
        if ml_context_ids is not None and ctx.id is not None:
            ml_context_ids.append(ctx.id)
        last_set[light] = (now, st.attributes.get("brightness"))

        rec_values.append(yhat)
        conf_values.append(conf)

    if not rec_values:
        return Recommendation(None, None)
    return Recommendation(
        recommended_brightness_pct=sum(rec_values) / len(rec_values),
        confidence=sum(conf_values) / len(conf_values) if conf_values else None,
    )
