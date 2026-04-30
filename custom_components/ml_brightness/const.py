from __future__ import annotations

from homeassistant.config_entries import ConfigEntry

DOMAIN = "ml_brightness"

PLATFORMS: list[str] = ["sensor", "switch", "button"]

CONF_AREAS = "areas"
CONF_LIGHTS = "lights"
CONF_PRESENCE_ENTITIES = "presence_entities"
CONF_PRESENCE_BY_AREA = "presence_by_area"
CONF_LUX_ENTITIES = "lux_entities"
CONF_CONTEXT_ENTITIES = "context_entities"
CONF_AUTODISCOVER_CONTEXT = "autodiscover_context"
CONF_CONTEXT_BLACKLIST = "context_blacklist"
CONF_CONTEXT_BLACKLIST_DOMAINS = "context_blacklist_domains"
CONF_WEATHER_ENTITY = "weather_entity"
CONF_WORKDAY_ENTITY = "workday_entity"

CONF_ENABLE_AUTO = "enable_auto"
CONF_COOLDOWN_SECONDS = "cooldown_seconds"
CONF_HYSTERESIS = "hysteresis"
CONF_MAX_DELTA_PER_MIN = "max_delta_per_min"
CONF_TRANSITION_SECONDS = "transition_seconds"
CONF_DONT_TURN_ON = "dont_turn_on_if_off"
CONF_TURN_ON_ON_PRESENCE = "turn_on_on_presence"
CONF_PRESENCE_CLEAR_TWO_STAGE = "presence_clear_two_stage"
CONF_PRESENCE_CLEAR_DIM_PCT = "presence_clear_dim_pct"
CONF_PRESENCE_CLEAR_DIM_TRANSITION_SEC = "presence_clear_dim_transition_sec"
CONF_PRESENCE_CLEAR_OFF_AFTER_DIM_SEC = "presence_clear_off_after_dim_sec"
CONF_NIGHT_SLOW_FACTOR = "night_slow_factor"
CONF_NIGHT_TRANSITION_SECONDS = "night_transition_seconds"

CONF_SLEEP_START = "sleep_start"
CONF_SLEEP_END = "sleep_end"
CONF_SLEEP_MAX_BRIGHTNESS_PCT = "sleep_max_brightness_pct"
CONF_SLEEP_SLOW_FACTOR = "sleep_slow_factor"

CONF_OVERRIDE_MINUTES = "override_minutes"
CONF_LEARN_NON_USER_CHANGES = "learn_non_user_changes"

CONF_MODEL_TYPE = "model_type"
MODEL_RIDGE = "ridge"
MODEL_KNN_MEDIAN = "knn_median"

CONF_CT_DEFAULT_MIN = "ct_default_min"
CONF_CT_DEFAULT_MAX = "ct_default_max"
CONF_CT_MIN = "ct_min"
CONF_CT_MAX = "ct_max"

CONF_CT_BOUNDS_BY_AREA = "ct_bounds_by_area"
CONF_CT_BOUNDS_BY_LIGHT = "ct_bounds_by_light"

STORAGE_VERSION = 2
STORAGE_KEY = f"{DOMAIN}_store"

META_HISTORY_BOOTSTRAP_DONE = "history_bootstrap_done"

DEFAULT_CONFIG: dict = {
    CONF_AREAS: [],
    CONF_LIGHTS: [],
    CONF_PRESENCE_ENTITIES: [],
    CONF_PRESENCE_BY_AREA: {},
    CONF_LUX_ENTITIES: [],
    CONF_CONTEXT_ENTITIES: [],
    CONF_CONTEXT_BLACKLIST: [],
    CONF_CONTEXT_BLACKLIST_DOMAINS: [],
    CONF_CT_BOUNDS_BY_AREA: {},
    CONF_CT_BOUNDS_BY_LIGHT: {},
    CONF_ENABLE_AUTO: True,
    CONF_COOLDOWN_SECONDS: 180,
    CONF_HYSTERESIS: 3.0,
    CONF_MAX_DELTA_PER_MIN: 25.0,
    CONF_TRANSITION_SECONDS: 2,
    CONF_DONT_TURN_ON: True,
    CONF_TURN_ON_ON_PRESENCE: True,
    CONF_PRESENCE_CLEAR_TWO_STAGE: False,
    CONF_PRESENCE_CLEAR_DIM_PCT: 10.0,
    CONF_PRESENCE_CLEAR_DIM_TRANSITION_SEC: 12.0,
    CONF_PRESENCE_CLEAR_OFF_AFTER_DIM_SEC: 15.0,
    CONF_NIGHT_SLOW_FACTOR: 0.25,
    CONF_NIGHT_TRANSITION_SECONDS: 8,
    CONF_AUTODISCOVER_CONTEXT: True,
    CONF_MODEL_TYPE: MODEL_KNN_MEDIAN,
    CONF_SLEEP_START: "23:00",
    CONF_SLEEP_END: "06:00",
    CONF_SLEEP_MAX_BRIGHTNESS_PCT: 35.0,
    CONF_SLEEP_SLOW_FACTOR: 0.20,
    CONF_OVERRIDE_MINUTES: 30,
    CONF_LEARN_NON_USER_CHANGES: False,
}


def entry_cfg(entry: ConfigEntry) -> dict:
    """Merge defaults + config entry data + options (options override data)."""
    out = dict(DEFAULT_CONFIG)
    out.update(entry.data)
    out.update(entry.options)
    return out
