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
    entry_cfg,
)
from .light_control import _extract_features, _pct_from_brightness, presence_union_for_features
from .model import ModelConfig, online_update_diag
from .storage import MLBrightnessStore, LightModelState


def _example_weight(*, now: datetime, y_pct: float) -> float:
    edge = 1.0
    if y_pct >= 95.0:
        edge *= 0.35
    if y_pct <= 5.0:
        edge *= 0.6
    return edge


async def train_from_history_state(
    *,
    hass: HomeAssistant,
    entry: ConfigEntry,
    store: MLBrightnessStore,
    entity_id: str,
    state: State,
) -> None:
    await _train_common(
        hass=hass,
        entry=entry,
        store=store,
        entity_id=entity_id,
        new_state=state,
        base_weight=0.15,
    )


async def train_from_manual_change(
    *,
    hass: HomeAssistant,
    entry: ConfigEntry,
    store: MLBrightnessStore,
    entity_id: str,
    new_state: State,
) -> None:
    await _train_common(
        hass=hass,
        entry=entry,
        store=store,
        entity_id=entity_id,
        new_state=new_state,
        base_weight=1.0,
    )


async def _train_common(
    *,
    hass: HomeAssistant,
    entry: ConfigEntry,
    store: MLBrightnessStore,
    entity_id: str,
    new_state: State,
    base_weight: float,
) -> None:
    now = datetime.now(timezone.utc)
    cfg = entry_cfg(entry)

    lights: set[str] = set(cfg.get(CONF_LIGHTS) or [])
    area_ids = set(cfg.get(CONF_AREAS) or [])
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

    ent_reg = er.async_get(hass)
    ent = ent_reg.async_get(entity_id)
    area_id = ent.area_id if ent else None

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

    context_entities = list(cfg.get(CONF_CONTEXT_ENTITIES) or [])
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
    cfg_model = ModelConfig(dim=len(x), ridge=1.0, huber_k=12.0)

    st = store.data.by_light.get(entity_id)
    if st is None:
        st = LightModelState(w=[], p=[], n=0)
        store.data.by_light[entity_id] = st

    st.examples.append({"x": x, "y": float(y_pct), "t": int(now.timestamp())})
    if len(st.examples) > 250:
        st.examples = st.examples[-250:]

    model_type = cfg.get(CONF_MODEL_TYPE)
    if model_type != MODEL_KNN_MEDIAN:
        w_new, p_new, _residual = online_update_diag(
            cfg=cfg_model,
            w=st.w,
            p=st.p,
            x=x,
            y=float(y_pct),
            example_weight=base_weight * _example_weight(now=now, y_pct=float(y_pct)),
        )
        st.w = w_new
        st.p = p_new

    st.n += 1

    if area_id:
        ast = store.data.by_area.get(area_id)
        if ast is None:
            ast = LightModelState(w=[], p=[], n=0)
            store.data.by_area[area_id] = ast
        ast.examples.append({"x": x, "y": float(y_pct), "t": int(now.timestamp())})
        if len(ast.examples) > 400:
            ast.examples = ast.examples[-400:]
        if model_type != MODEL_KNN_MEDIAN:
            w_new, p_new, _residual = online_update_diag(
                cfg=cfg_model,
                w=ast.w,
                p=ast.p,
                x=x,
                y=float(y_pct),
                example_weight=base_weight * 0.7 * _example_weight(now=now, y_pct=float(y_pct)),
            )
            ast.w = w_new
            ast.p = p_new
        ast.n += 1

    store.async_schedule_save(2.0)
