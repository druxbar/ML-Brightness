from __future__ import annotations

from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
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

_ROOM_PRESENCE_ENTITIES = "room_presence_entities"
_ROOM_CT_MIN = "room_ct_min"
_ROOM_CT_MAX = "room_ct_max"
_ROOM_ID = "room_id"


def _schema_fields(d: dict) -> dict:
    return {
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


def _schema_for_defaults(defaults: dict) -> vol.Schema:
    d = {**DEFAULT_CONFIG, **defaults}
    return vol.Schema(_schema_fields(d))


def _schema_for_keys(*, defaults: dict, keys: set[str]) -> vol.Schema:
    fields = _schema_fields({**DEFAULT_CONFIG, **defaults})
    return vol.Schema({k: v for k, v in fields.items() if str(k.schema) in keys})


def _entities_in_area(hass: HomeAssistant, area_id: str, *, domains: set[str] | None = None) -> list[str]:
    ent_reg = er.async_get(hass)
    out: list[str] = []
    for ent in ent_reg.entities.values():
        if ent.area_id != area_id:
            continue
        if domains is not None and ent.domain not in domains:
            continue
        out.append(ent.entity_id)
    out.sort()
    return out


async def _has_entries(hass: HomeAssistant) -> bool:
    return hass.config_entries.async_entries(DOMAIN) != []


class MLBrightnessOptionsFlow(config_entries.OptionsFlow):
    """Reconfigure integration via menu-driven options flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry
        self._room_area_id: str | None = None

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "rooms",
                "signals",
                "smoothing",
                "presence",
                "color_temp",
                "sleep",
                "learning",
                "advanced",
            ],
        )

    def _save_options(self, user_input: dict[str, Any]) -> None:
        merged = dict(self.config_entry.options or {})
        merged.update(user_input or {})
        self.hass.config_entries.async_update_entry(self.config_entry, options=merged)

    async def async_step_signals(self, user_input=None):
        if user_input is not None:
            self._save_options(user_input)
            return self.async_create_entry(title="", data={})
        defaults = entry_cfg(self.config_entry)
        return self.async_show_form(
            step_id="signals",
            data_schema=_schema_for_keys(defaults=defaults, keys={CONF_WEATHER_ENTITY, CONF_WORKDAY_ENTITY}),
        )

    async def async_step_smoothing(self, user_input=None):
        if user_input is not None:
            self._save_options(user_input)
            return self.async_create_entry(title="", data={})
        defaults = entry_cfg(self.config_entry)
        return self.async_show_form(
            step_id="smoothing",
            data_schema=_schema_for_keys(
                defaults=defaults,
                keys={
                    CONF_COOLDOWN_SECONDS,
                    CONF_HYSTERESIS,
                    CONF_MAX_DELTA_PER_MIN,
                    CONF_TRANSITION_SECONDS,
                    CONF_NIGHT_SLOW_FACTOR,
                    CONF_NIGHT_TRANSITION_SECONDS,
                },
            ),
        )

    async def async_step_presence(self, user_input=None):
        if user_input is not None:
            self._save_options(user_input)
            return self.async_create_entry(title="", data={})
        defaults = entry_cfg(self.config_entry)
        return self.async_show_form(
            step_id="presence",
            data_schema=_schema_for_keys(
                defaults=defaults,
                keys={
                    CONF_PRESENCE_ENTITIES,
                    CONF_PRESENCE_BY_AREA,
                    CONF_DONT_TURN_ON,
                    CONF_TURN_ON_ON_PRESENCE,
                    CONF_PRESENCE_CLEAR_TWO_STAGE,
                    CONF_PRESENCE_CLEAR_DIM_PCT,
                    CONF_PRESENCE_CLEAR_DIM_TRANSITION_SEC,
                    CONF_PRESENCE_CLEAR_OFF_AFTER_DIM_SEC,
                },
            ),
        )

    async def async_step_color_temp(self, user_input=None):
        if user_input is not None:
            self._save_options(user_input)
            return self.async_create_entry(title="", data={})
        defaults = entry_cfg(self.config_entry)
        return self.async_show_form(
            step_id="color_temp",
            data_schema=_schema_for_keys(
                defaults=defaults,
                keys={CONF_CT_MIN, CONF_CT_MAX, CONF_CT_BOUNDS_BY_AREA, CONF_CT_BOUNDS_BY_LIGHT},
            ),
        )

    async def async_step_sleep(self, user_input=None):
        if user_input is not None:
            self._save_options(user_input)
            return self.async_create_entry(title="", data={})
        defaults = entry_cfg(self.config_entry)
        return self.async_show_form(
            step_id="sleep",
            data_schema=_schema_for_keys(
                defaults=defaults,
                keys={CONF_SLEEP_START, CONF_SLEEP_END, CONF_SLEEP_MAX_BRIGHTNESS_PCT, CONF_SLEEP_SLOW_FACTOR},
            ),
        )

    async def async_step_learning(self, user_input=None):
        if user_input is not None:
            self._save_options(user_input)
            return self.async_create_entry(title="", data={})
        defaults = entry_cfg(self.config_entry)
        return self.async_show_form(
            step_id="learning",
            data_schema=_schema_for_keys(
                defaults=defaults,
                keys={CONF_ENABLE_AUTO, CONF_MODEL_TYPE, CONF_OVERRIDE_MINUTES, CONF_LEARN_NON_USER_CHANGES},
            ),
        )

    async def async_step_advanced(self, user_input=None):
        if user_input is not None:
            self._save_options(user_input)
            return self.async_create_entry(title="", data={})
        defaults = entry_cfg(self.config_entry)
        return self.async_show_form(
            step_id="advanced",
            data_schema=_schema_for_keys(
                defaults=defaults,
                keys={
                    CONF_AUTODISCOVER_CONTEXT,
                    CONF_CONTEXT_ENTITIES,
                    CONF_CONTEXT_BLACKLIST,
                    CONF_CONTEXT_BLACKLIST_DOMAINS,
                    CONF_LUX_ENTITIES,
                },
            ),
        )

    async def async_step_rooms(self, user_input=None):
        return self.async_show_menu(step_id="rooms", menu_options=["rooms_add", "rooms_configure", "rooms_remove"])

    async def async_step_rooms_add(self, user_input=None):
        cfg = entry_cfg(self.config_entry)
        if user_input is not None:
            self._save_options({CONF_AREAS: user_input.get(CONF_AREAS) or []})
            return self.async_create_entry(title="", data={})
        return self.async_show_form(
            step_id="rooms_add",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_AREAS, default=cfg.get(CONF_AREAS) or []): selector.AreaSelector(
                        selector.AreaSelectorConfig(multiple=True)
                    )
                }
            ),
        )

    async def async_step_rooms_remove(self, user_input=None):
        cfg = entry_cfg(self.config_entry)
        if user_input is not None:
            remove_ids = set(user_input.get(CONF_AREAS) or [])
            new_areas = [a for a in (cfg.get(CONF_AREAS) or []) if a not in remove_ids]
            pba = dict(cfg.get(CONF_PRESENCE_BY_AREA) or {})
            for aid in remove_ids:
                pba.pop(aid, None)
            cta = dict(cfg.get(CONF_CT_BOUNDS_BY_AREA) or {})
            for aid in remove_ids:
                cta.pop(aid, None)
            self._save_options({CONF_AREAS: new_areas, CONF_PRESENCE_BY_AREA: pba, CONF_CT_BOUNDS_BY_AREA: cta})
            return self.async_create_entry(title="", data={})
        return self.async_show_form(
            step_id="rooms_remove",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_AREAS, default=[]): selector.AreaSelector(
                        selector.AreaSelectorConfig(multiple=True)
                    )
                }
            ),
        )

    async def async_step_rooms_configure(self, user_input=None):
        cfg = entry_cfg(self.config_entry)
        area_ids = list(cfg.get(CONF_AREAS) or [])
        if not area_ids:
            return self.async_abort(reason="no_rooms_configured")
        if user_input is not None:
            self._room_area_id = user_input.get(_ROOM_ID)
            return await self.async_step_room_config()
        area_reg = ar.async_get(self.hass)
        opts = []
        for aid in sorted(area_ids):
            a = area_reg.async_get_area(aid)
            label = a.name if a else aid
            opts.append({"label": label, "value": aid})
        return self.async_show_form(
            step_id="rooms_configure",
            data_schema=vol.Schema(
                {
                    vol.Required(_ROOM_ID): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=opts, mode=selector.SelectSelectorMode.DROPDOWN)
                    )
                }
            ),
        )

    async def async_step_room_config(self, user_input=None):
        cfg = entry_cfg(self.config_entry)
        area_id = self._room_area_id
        if not area_id:
            return await self.async_step_rooms_configure()

        if user_input is not None:
            pba = dict(cfg.get(CONF_PRESENCE_BY_AREA) or {})
            pba[area_id] = list(user_input.get(_ROOM_PRESENCE_ENTITIES) or [])

            cta = dict(cfg.get(CONF_CT_BOUNDS_BY_AREA) or {})
            ct_min = user_input.get(_ROOM_CT_MIN)
            ct_max = user_input.get(_ROOM_CT_MAX)
            room_ct: dict[str, Any] = dict(cta.get(area_id) or {})
            if ct_min is not None:
                room_ct["ct_min"] = float(ct_min)
            if ct_max is not None:
                room_ct["ct_max"] = float(ct_max)
            if room_ct:
                cta[area_id] = room_ct
            else:
                cta.pop(area_id, None)

            self._save_options({CONF_PRESENCE_BY_AREA: pba, CONF_CT_BOUNDS_BY_AREA: cta})
            return self.async_create_entry(title="", data={})

        allowed_presence_domains = {"binary_sensor", "sensor", "person", "device_tracker"}
        include = _entities_in_area(self.hass, area_id, domains=allowed_presence_domains)

        pba = cfg.get(CONF_PRESENCE_BY_AREA) or {}
        cur_presence = list(pba.get(area_id) or []) if isinstance(pba, dict) else []
        cta = cfg.get(CONF_CT_BOUNDS_BY_AREA) or {}
        cur_ct = cta.get(area_id) if isinstance(cta, dict) else None
        cur_ct_min = cur_ct.get("ct_min") if isinstance(cur_ct, dict) else None
        cur_ct_max = cur_ct.get("ct_max") if isinstance(cur_ct, dict) else None

        schema = vol.Schema(
            {
                vol.Optional(_ROOM_PRESENCE_ENTITIES, default=cur_presence): selector.EntitySelector(
                    selector.EntitySelectorConfig(include_entities=include, multiple=True)
                ),
                vol.Optional(_ROOM_CT_MIN, default=cur_ct_min): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=100, max=500, step=1, mode="box")
                ),
                vol.Optional(_ROOM_CT_MAX, default=cur_ct_max): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=100, max=500, step=1, mode="box")
                ),
            }
        )
        return self.async_show_form(step_id="room_config", data_schema=schema)


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
