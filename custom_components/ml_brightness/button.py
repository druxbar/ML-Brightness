from __future__ import annotations

from datetime import datetime, timedelta, timezone

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_OVERRIDE_MINUTES, DOMAIN, entry_cfg
from .coordinator import MLBrightnessCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MLBrightnessCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([OverrideButton(coordinator, entry)])


class OverrideButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_name = "Override (pause auto)"

    def __init__(self, coordinator: MLBrightnessCoordinator, entry: ConfigEntry) -> None:
        self.coordinator = coordinator
        self.entry = entry

    @property
    def unique_id(self) -> str:
        return f"{self.entry.entry_id}_override_button"

    async def async_press(self) -> None:
        mins = int(entry_cfg(self.entry).get(CONF_OVERRIDE_MINUTES, 30))
        until = datetime.now(timezone.utc) + timedelta(minutes=max(1, mins))
        self.coordinator.set_override_until(until)
        await self.coordinator.async_request_refresh()

