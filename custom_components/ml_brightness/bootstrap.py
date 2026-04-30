from __future__ import annotations

from datetime import datetime, timedelta, timezone

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import CONF_AREAS, CONF_LIGHTS
from .storage import MLBrightnessStore, LightModelState
from .trainer import train_from_history_state


async def maybe_bootstrap_history(hass: HomeAssistant, entry: ConfigEntry, store: MLBrightnessStore) -> None:
    # do once: if no examples anywhere, try bootstrap from recorder last 14d
    if any(st.examples for st in store.data.by_light.values()):
        return

    try:
        from homeassistant.components.recorder import history  # type: ignore
        from homeassistant.components.recorder import get_instance  # type: ignore
    except Exception:
        return

    instance = get_instance(hass)
    if instance is None:
        return

    lights: set[str] = set(entry.data.get(CONF_LIGHTS) or [])
    area_ids = set(entry.data.get(CONF_AREAS) or [])
    if area_ids:
        ent_reg = er.async_get(hass)
        for ent in ent_reg.entities.values():
            if ent.domain == "light" and ent.area_id in area_ids:
                lights.add(ent.entity_id)
    if not lights:
        return

    start = datetime.now(timezone.utc) - timedelta(days=14)
    end = datetime.now(timezone.utc)

    def _query():
        return history.get_significant_states(
            hass,
            start,
            end_time=end,
            entity_ids=list(lights),
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

    # feed as weak examples (history has no manual context)
    for ent_id, states in (states_by_ent or {}).items():
        if ent_id not in store.data.by_light:
            store.data.by_light[ent_id] = LightModelState()
        for st in states:
            # can be dict if minimal response; we requested State
            if not hasattr(st, "attributes"):
                continue
            await train_from_history_state(hass=hass, entry=entry, store=store, entity_id=ent_id, state=st)

    await store.async_save()

