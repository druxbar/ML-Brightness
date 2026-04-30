from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import MLBrightnessCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MLBrightnessCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            RecommendedBrightnessSensor(coordinator, entry),
            ConfidenceSensor(coordinator, entry),
        ]
    )


class _BaseCoordSensor(SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: MLBrightnessCoordinator, entry: ConfigEntry) -> None:
        self.coordinator = coordinator
        self.entry = entry

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))


class RecommendedBrightnessSensor(_BaseCoordSensor):
    _attr_name = "Recommended brightness"
    _attr_native_unit_of_measurement = "%"

    @property
    def unique_id(self) -> str:
        return f"{self.entry.entry_id}_recommended_brightness"

    @property
    def native_value(self):
        return self.coordinator.data.recommended_brightness_pct


class ConfidenceSensor(_BaseCoordSensor):
    _attr_name = "Model confidence"

    @property
    def unique_id(self) -> str:
        return f"{self.entry.entry_id}_confidence"

    @property
    def native_value(self):
        return self.coordinator.data.confidence

