from __future__ import annotations

from datetime import datetime, timedelta, timezone

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import CONF_AREAS, CONF_LIGHTS, META_HISTORY_BOOTSTRAP_DONE, entry_cfg
from .storage import MLBrightnessStore, LightModelState
from .trainer import train_from_history_state

_BOOTSTRAP_MAX_LIGHTS = 40
_BOOTSTRAP_MAX_DAYS = 7


async def maybe_bootstrap_history(hass: HomeAssistant, entry: ConfigEntry, store: MLBrightnessStore) -> None:
    if store.data.meta.get(META_HISTORY_BOOTSTRAP_DONE):
        return

    if any(st.examples for st in store.data.by_light.values()):
        store.data.meta[META_HISTORY_BOOTSTRAP_DONE] = True
        await store.async_save()
        return

    try:
        from homeassistant.components.recorder import history  # type: ignore
        from homeassistant.components.recorder import get_instance  # type: ignore
    except Exception:
        return

    instance = get_instance(hass)
    if instance is None:
        return

    cfg = entry_cfg(entry)
    lights: set[str] = set(cfg.get(CONF_LIGHTS) or [])
    area_ids = set(cfg.get(CONF_AREAS) or [])
    if area_ids:
        ent_reg = er.async_get(hass)
        for ent in ent_reg.entities.values():
            if ent.domain == "light" and ent.area_id in area_ids:
                lights.add(ent.entity_id)
    if not lights:
        store.data.meta[META_HISTORY_BOOTSTRAP_DONE] = True
        await store.async_save()
        return

    light_list = sorted(lights)[:_BOOTSTRAP_MAX_LIGHTS]

    start = datetime.now(timezone.utc) - timedelta(days=_BOOTSTRAP_MAX_DAYS)
    end = datetime.now(timezone.utc)

    def _query():
        return history.get_significant_states(
            hass,
            start,
            end_time=end,
            entity_ids=light_list,
            include_start_time_state=False,
            significant_changes_only=True,
            minimal_response=False,
            no_attributes=False,
            compressed_state_format=False,
        )

    try:
        states_by_ent = await instance.async_add_executor_job(_query)
    except Exception:
        return

    for ent_id, states in (states_by_ent or {}).items():
        if ent_id not in store.data.by_light:
            store.data.by_light[ent_id] = LightModelState()
        for st in states:
            if not hasattr(st, "attributes"):
                continue
            await train_from_history_state(hass=hass, entry=entry, store=store, entity_id=ent_id, state=st)

    store.data.meta[META_HISTORY_BOOTSTRAP_DONE] = True
    await store.async_save()
