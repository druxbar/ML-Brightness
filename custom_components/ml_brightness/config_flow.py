from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
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
    CONF_CT_MAX,
    CONF_CT_MIN,
    CONF_CT_BOUNDS_BY_AREA,
    CONF_CT_BOUNDS_BY_LIGHT,
    CONF_WEATHER_ENTITY,
    CONF_WORKDAY_ENTITY,
    CONF_TRANSITION_SECONDS,
    CONF_DONT_TURN_ON,
    CONF_MODEL_TYPE,
    MODEL_KNN_MEDIAN,
    MODEL_RIDGE,
    DOMAIN,
)


DEFAULTS = {
    CONF_ENABLE_AUTO: True,
    CONF_COOLDOWN_SECONDS: 180,
    CONF_HYSTERESIS: 3.0,  # pct
    CONF_MAX_DELTA_PER_MIN: 25.0,  # pct/min
    CONF_TRANSITION_SECONDS: 2,
    CONF_DONT_TURN_ON: True,
    CONF_MODEL_TYPE: MODEL_KNN_MEDIAN,
}


async def _has_entries(hass: HomeAssistant) -> bool:
    return hass.config_entries.async_entries(DOMAIN) != []


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if await _has_entries(self.hass):
            return self.async_abort(reason="single_instance_allowed")

        if user_input is None:
            schema = vol.Schema(
                {
                    vol.Optional(CONF_AREAS): selector.AreaSelector(
                        selector.AreaSelectorConfig(multiple=True)
                    ),
                    vol.Optional(CONF_LIGHTS): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="light", multiple=True)
                    ),
                    vol.Optional(CONF_PRESENCE_ENTITIES): selector.EntitySelector(
                        selector.EntitySelectorConfig(multiple=True)
                    ),
                    vol.Optional(CONF_LUX_ENTITIES): selector.EntitySelector(
                        selector.EntitySelectorConfig(multiple=True)
                    ),
                    vol.Optional(CONF_CONTEXT_ENTITIES): selector.EntitySelector(
                        selector.EntitySelectorConfig(multiple=True)
                    ),
                    vol.Optional(CONF_WEATHER_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="weather", multiple=False)
                    ),
                    vol.Optional(CONF_WORKDAY_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(multiple=False)
                    ),
                    vol.Optional(CONF_ENABLE_AUTO, default=DEFAULTS[CONF_ENABLE_AUTO]): bool,
                    vol.Optional(
                        CONF_COOLDOWN_SECONDS, default=DEFAULTS[CONF_COOLDOWN_SECONDS]
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=0, max=3600, step=10, mode="box")
                    ),
                    vol.Optional(CONF_HYSTERESIS, default=DEFAULTS[CONF_HYSTERESIS]): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=0, max=50, step=0.5, mode="box")
                    ),
                    vol.Optional(
                        CONF_MAX_DELTA_PER_MIN, default=DEFAULTS[CONF_MAX_DELTA_PER_MIN]
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=1, max=100, step=1, mode="box")
                    ),
                    vol.Optional(
                        CONF_TRANSITION_SECONDS, default=DEFAULTS[CONF_TRANSITION_SECONDS]
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=0, max=30, step=1, mode="box")
                    ),
                    vol.Optional(CONF_DONT_TURN_ON, default=DEFAULTS[CONF_DONT_TURN_ON]): bool,
                    vol.Optional(CONF_MODEL_TYPE, default=DEFAULTS[CONF_MODEL_TYPE]): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"label": "kNN weighted median (robust)", "value": MODEL_KNN_MEDIAN},
                                {"label": "Online ridge (linear)", "value": MODEL_RIDGE},
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(CONF_CT_MIN): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=100, max=500, step=1, mode="box")
                    ),
                    vol.Optional(CONF_CT_MAX): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=100, max=500, step=1, mode="box")
                    ),
                    vol.Optional(CONF_CT_BOUNDS_BY_AREA): selector.ObjectSelector(),
                    vol.Optional(CONF_CT_BOUNDS_BY_LIGHT): selector.ObjectSelector(),
                }
            )
            return self.async_show_form(step_id="user", data_schema=schema)

        title = "ML Brightness"
        return self.async_create_entry(title=title, data=user_input)

