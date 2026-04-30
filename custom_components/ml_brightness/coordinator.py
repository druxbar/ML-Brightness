from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

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
    DOMAIN,
)
from .light_control import apply_recommendations
from .storage import MLBrightnessStore


@dataclass(frozen=True)
class MLBrightnessData:
    recommended_brightness_pct: float | None
    confidence: float | None


class MLBrightnessCoordinator(DataUpdateCoordinator[MLBrightnessData]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            logger=None,
            name=DOMAIN,
            update_interval=timedelta(seconds=30),
        )
        self.entry = entry
        self.store = MLBrightnessStore(hass)

        self._last_set: dict[str, tuple[datetime, int | None]] = {}
        self._last_manual: dict[str, datetime] = {}
        self._pred_hold: dict[str, tuple[float, int]] = {}
        self._unsub = None

    async def _async_update_data(self) -> MLBrightnessData:
        # compute + maybe apply (auto)
        rec = await apply_recommendations(
            self.hass,
            self.entry,
            self.store,
            self._last_set,
            self._last_manual,
            pred_hold=self._pred_hold,
        )
        return MLBrightnessData(
            recommended_brightness_pct=rec.recommended_brightness_pct,
            confidence=rec.confidence,
        )

    async def async_config_entry_first_refresh(self) -> None:
        await self.store.async_load()
        self._setup_listeners()
        await super().async_config_entry_first_refresh()

    def _setup_listeners(self) -> None:
        if self._unsub is not None:
            return

        lights = set(self.entry.data.get(CONF_LIGHTS) or [])
        area_ids = set(self.entry.data.get(CONF_AREAS) or [])
        if area_ids:
            # include lights from areas too
            ent_reg = er.async_get(self.hass)
            for ent in ent_reg.entities.values():
                if ent.domain == "light" and ent.area_id in area_ids:
                    lights.add(ent.entity_id)

        if not lights:
            return

        async def _on_state_change(event) -> None:
            entity_id = event.data.get(ATTR_ENTITY_ID)
            if entity_id not in lights:
                return

            new_state = event.data.get("new_state")
            old_state = event.data.get("old_state")
            if new_state is None or old_state is None:
                return

            # ignore if no brightness change
            nb = new_state.attributes.get("brightness")
            ob = old_state.attributes.get("brightness")
            if nb is None or nb == ob:
                return

            # ignore our own recent set
            now = datetime.now(timezone.utc)
            last = self._last_set.get(entity_id)
            if last and (now - last[0]).total_seconds() < 5:
                return

            # treat as manual if user_id present
            if getattr(new_state.context, "user_id", None):
                self._last_manual[entity_id] = now
                # train from this manual target
                from .trainer import train_from_manual_change

                self.hass.async_create_task(
                    train_from_manual_change(
                        hass=self.hass,
                        entry=self.entry,
                        store=self.store,
                        entity_id=entity_id,
                        new_state=new_state,
                    )
                )

            # schedule coordinator refresh soon
            self.hass.async_create_task(self.async_request_refresh())

        self._unsub = async_track_state_change_event(self.hass, list(lights), _on_state_change)


