from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ENABLE_AUTO, DOMAIN
from .coordinator import MLBrightnessCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MLBrightnessCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AutoEnabledSwitch(coordinator, entry)])


class AutoEnabledSwitch(SwitchEntity):
    _attr_has_entity_name = True
    _attr_name = "Auto brightness enabled"

    def __init__(self, coordinator: MLBrightnessCoordinator, entry: ConfigEntry) -> None:
        self.coordinator = coordinator
        self.entry = entry

    @property
    def unique_id(self) -> str:
        return f"{self.entry.entry_id}_auto_enabled"

    @property
    def is_on(self) -> bool:
        return bool(self.entry.data.get(CONF_ENABLE_AUTO, True))

    async def async_turn_on(self, **kwargs) -> None:
        self.hass.config_entries.async_update_entry(
            self.entry, data={**self.entry.data, CONF_ENABLE_AUTO: True}
        )
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self.hass.config_entries.async_update_entry(
            self.entry, data={**self.entry.data, CONF_ENABLE_AUTO: False}
        )
        self.async_write_ha_state()

