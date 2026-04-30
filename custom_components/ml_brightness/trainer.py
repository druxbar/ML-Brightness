from __future__ import annotations

import math
from datetime import datetime, timezone

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_AREAS,
    CONF_CONTEXT_ENTITIES,
    CONF_LIGHTS,
    CONF_LUX_ENTITIES,
    CONF_PRESENCE_ENTITIES,
    CONF_MODEL_TYPE,
    MODEL_KNN_MEDIAN,
)
from .light_control import _extract_features, _pct_from_brightness
from .model import ModelConfig, online_update_diag, predict
from .storage import MLBrightnessStore, LightModelState


def _example_weight(*, now: datetime, y_pct: float) -> float:
    # downweight extreme targets a bit (night search max-bright) unless repeated.
    # later: incorporate context rarity; v1 simple.
    edge = 1.0
    if y_pct >= 95.0:
        edge *= 0.35
    if y_pct <= 5.0:
        edge *= 0.6
    # small boost at normal ranges
    return edge


async def train_from_manual_change(
    *,
    hass: HomeAssistant,
    entry: ConfigEntry,
    store: MLBrightnessStore,
    entity_id: str,
    new_state: State,
) -> None:
    now = datetime.now(timezone.utc)

    # must be tracked light
    lights: set[str] = set(entry.data.get(CONF_LIGHTS) or [])
    area_ids = set(entry.data.get(CONF_AREAS) or [])
    if area_ids:
        ent_reg = er.async_get(hass)
        for ent in ent_reg.entities.values():
            if ent.domain == "light" and ent.area_id in area_ids:
                lights.add(ent.entity_id)
    if entity_id not in lights:
        return

    y_pct = _pct_from_brightness(new_state.attributes.get("brightness"))
    if y_pct is None:
        return

    # optional signals (global, coarse)
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

    st = store.data.by_light.get(entity_id)
    if st is None:
        st = LightModelState(w=[], p=[], n=0)
        store.data.by_light[entity_id] = st

    # store example for kNN always (cheap, robust)
    st.examples.append({"x": x, "y": float(y_pct), "t": int(now.timestamp())})
    if len(st.examples) > 250:
        st.examples = st.examples[-250:]

    model_type = entry.data.get(CONF_MODEL_TYPE)
    if model_type != MODEL_KNN_MEDIAN:
        w_new, p_new, _residual = online_update_diag(
            cfg=cfg,
            w=st.w,
            p=st.p,
            x=x,
            y=float(y_pct),
            example_weight=_example_weight(now=now, y_pct=float(y_pct)),
        )
        st.w = w_new
        st.p = p_new

    st.n += 1

    await store.async_save()

