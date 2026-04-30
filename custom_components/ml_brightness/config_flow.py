from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
    CONF_COOLDOWN_SECONDS,
    CONF_CONTEXT_ENTITIES,
    CONF_AREAS,
    CONF_LIGHTS,
    CONF_LUX_ENTITIES,
    CONF_ENABLE_AUTO,
    CONF_HYSTERESIS,
    CONF_MAX_DELTA_PER_MIN,
    CONF_PRESENCE_ENTITIES,
    CONF_PRESENCE_BY_AREA,
    CONF_CT_MAX,
    CONF_CT_MIN,
    CONF_CT_BOUNDS_BY_AREA,
    CONF_CT_BOUNDS_BY_LIGHT,
    CONF_WEATHER_ENTITY,
    CONF_WORKDAY_ENTITY,
    CONF_TRANSITION_SECONDS,
    CONF_DONT_TURN_ON,
    CONF_TURN_ON_ON_PRESENCE,
    CONF_PRESENCE_CLEAR_TWO_STAGE,
    CONF_PRESENCE_CLEAR_DIM_PCT,
    CONF_PRESENCE_CLEAR_DIM_TRANSITION_SEC,
    CONF_PRESENCE_CLEAR_OFF_AFTER_DIM_SEC,
    CONF_NIGHT_SLOW_FACTOR,
    CONF_NIGHT_TRANSITION_SECONDS,
    CONF_AUTODISCOVER_CONTEXT,
    CONF_CONTEXT_BLACKLIST,
    CONF_CONTEXT_BLACKLIST_DOMAINS,
    CONF_MODEL_TYPE,
    MODEL_KNN_MEDIAN,
    MODEL_RIDGE,
    CONF_SLEEP_START,
    CONF_SLEEP_END,
    CONF_SLEEP_MAX_BRIGHTNESS_PCT,
    CONF_SLEEP_SLOW_FACTOR,
    CONF_OVERRIDE_MINUTES,
    CONF_LEARN_NON_USER_CHANGES,
    DEFAULT_CONFIG,
    DOMAIN,
    entry_cfg,
)


def _schema_for_defaults(defaults: dict) -> vol.Schema:
    d = {**DEFAULT_CONFIG, **defaults}
    return vol.Schema(
        {
            vol.Optional(CONF_AREAS, default=d.get(CONF_AREAS) or []): selector.AreaSelector(
                selector.AreaSelectorConfig(multiple=True)
            ),
            vol.Optional(CONF_LIGHTS, default=d.get(CONF_LIGHTS) or []): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="light", multiple=True)
            ),
            vol.Optional(CONF_PRESENCE_ENTITIES, default=d.get(CONF_PRESENCE_ENTITIES) or []): selector.EntitySelector(
                selector.EntitySelectorConfig(multiple=True)
            ),
            vol.Optional(CONF_PRESENCE_BY_AREA, default=d.get(CONF_PRESENCE_BY_AREA) or {}): selector.ObjectSelector(),
            vol.Optional(CONF_LUX_ENTITIES, default=d.get(CONF_LUX_ENTITIES) or []): selector.EntitySelector(
                selector.EntitySelectorConfig(multiple=True)
            ),
            vol.Optional(CONF_CONTEXT_ENTITIES, default=d.get(CONF_CONTEXT_ENTITIES) or []): selector.EntitySelector(
                selector.EntitySelectorConfig(multiple=True)
            ),
            vol.Optional(CONF_AUTODISCOVER_CONTEXT, default=d.get(CONF_AUTODISCOVER_CONTEXT)): bool,
            vol.Optional(CONF_CONTEXT_BLACKLIST, default=d.get(CONF_CONTEXT_BLACKLIST) or []): selector.EntitySelector(
                selector.EntitySelectorConfig(multiple=True)
            ),
            vol.Optional(CONF_CONTEXT_BLACKLIST_DOMAINS, default=d.get(CONF_CONTEXT_BLACKLIST_DOMAINS) or []): selector.ObjectSelector(),
            vol.Optional(CONF_WEATHER_ENTITY, default=d.get(CONF_WEATHER_ENTITY)): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="weather", multiple=False)
            ),
            vol.Optional(CONF_WORKDAY_ENTITY, default=d.get(CONF_WORKDAY_ENTITY)): selector.EntitySelector(
                selector.EntitySelectorConfig(multiple=False)
            ),
            vol.Optional(CONF_ENABLE_AUTO, default=d.get(CONF_ENABLE_AUTO)): bool,
            vol.Optional(CONF_COOLDOWN_SECONDS, default=d.get(CONF_COOLDOWN_SECONDS)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=3600, step=10, mode="box")
            ),
            vol.Optional(CONF_HYSTERESIS, default=d.get(CONF_HYSTERESIS)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=50, step=0.5, mode="box")
            ),
            vol.Optional(CONF_MAX_DELTA_PER_MIN, default=d.get(CONF_MAX_DELTA_PER_MIN)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=100, step=1, mode="box")
            ),
            vol.Optional(CONF_TRANSITION_SECONDS, default=d.get(CONF_TRANSITION_SECONDS)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=30, step=1, mode="box")
            ),
            vol.Optional(CONF_DONT_TURN_ON, default=d.get(CONF_DONT_TURN_ON)): bool,
            vol.Optional(CONF_TURN_ON_ON_PRESENCE, default=d.get(CONF_TURN_ON_ON_PRESENCE)): bool,
            vol.Optional(CONF_PRESENCE_CLEAR_TWO_STAGE, default=d.get(CONF_PRESENCE_CLEAR_TWO_STAGE)): bool,
            vol.Optional(CONF_PRESENCE_CLEAR_DIM_PCT, default=d.get(CONF_PRESENCE_CLEAR_DIM_PCT)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=50, step=1, mode="box")
            ),
            vol.Optional(
                CONF_PRESENCE_CLEAR_DIM_TRANSITION_SEC, default=d.get(CONF_PRESENCE_CLEAR_DIM_TRANSITION_SEC)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=60, step=1, mode="box")
            ),
            vol.Optional(
                CONF_PRESENCE_CLEAR_OFF_AFTER_DIM_SEC, default=d.get(CONF_PRESENCE_CLEAR_OFF_AFTER_DIM_SEC)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=5, max=600, step=5, mode="box")
            ),
            vol.Optional(CONF_NIGHT_SLOW_FACTOR, default=d.get(CONF_NIGHT_SLOW_FACTOR)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0.05, max=1.0, step=0.05, mode="box")
            ),
            vol.Optional(CONF_NIGHT_TRANSITION_SECONDS, default=d.get(CONF_NIGHT_TRANSITION_SECONDS)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=60, step=1, mode="box")
            ),
            vol.Optional(CONF_SLEEP_START, default=d.get(CONF_SLEEP_START)): selector.TextSelector(),
            vol.Optional(CONF_SLEEP_END, default=d.get(CONF_SLEEP_END)): selector.TextSelector(),
            vol.Optional(CONF_SLEEP_MAX_BRIGHTNESS_PCT, default=d.get(CONF_SLEEP_MAX_BRIGHTNESS_PCT)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=100, step=1, mode="box")
            ),
            vol.Optional(CONF_SLEEP_SLOW_FACTOR, default=d.get(CONF_SLEEP_SLOW_FACTOR)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0.05, max=1.0, step=0.05, mode="box")
            ),
            vol.Optional(CONF_OVERRIDE_MINUTES, default=d.get(CONF_OVERRIDE_MINUTES)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=360, step=1, mode="box")
            ),
            vol.Optional(CONF_LEARN_NON_USER_CHANGES, default=d.get(CONF_LEARN_NON_USER_CHANGES)): bool,
            vol.Optional(CONF_MODEL_TYPE, default=d.get(CONF_MODEL_TYPE)): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"label": "kNN weighted median (robust)", "value": MODEL_KNN_MEDIAN},
                        {"label": "Online ridge (linear)", "value": MODEL_RIDGE},
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(CONF_CT_MIN, default=d.get(CONF_CT_MIN)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=100, max=500, step=1, mode="box")
            ),
            vol.Optional(CONF_CT_MAX, default=d.get(CONF_CT_MAX)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=100, max=500, step=1, mode="box")
            ),
            vol.Optional(CONF_CT_BOUNDS_BY_AREA, default=d.get(CONF_CT_BOUNDS_BY_AREA) or {}): selector.ObjectSelector(),
            vol.Optional(CONF_CT_BOUNDS_BY_LIGHT, default=d.get(CONF_CT_BOUNDS_BY_LIGHT) or {}): selector.ObjectSelector(),
        }
    )


async def _has_entries(hass: HomeAssistant) -> bool:
    return hass.config_entries.async_entries(DOMAIN) != []


class MLBrightnessOptionsFlow(config_entries.OptionsFlow):
    """Reconfigure integration (writes merged dict to `config_entry.data`)."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            merged = {**self.config_entry.data, **user_input}
            self.hass.config_entries.async_update_entry(self.config_entry, data=merged, options={})
            return self.async_create_entry(title="", data={})

        defaults = entry_cfg(self.config_entry)
        return self.async_show_form(
            step_id="init",
            data_schema=_schema_for_defaults(defaults),
        )


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> MLBrightnessOptionsFlow:
        return MLBrightnessOptionsFlow(config_entry)

    async def async_step_user(self, user_input=None):
        if await _has_entries(self.hass):
            return self.async_abort(reason="single_instance_allowed")

        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=_schema_for_defaults({}),
            )

        title = "ML Brightness"
        merged = {**DEFAULT_CONFIG, **user_input}
        return self.async_create_entry(title=title, data=merged)
