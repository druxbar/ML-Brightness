DOMAIN = "ml_brightness"

PLATFORMS: list[str] = ["sensor", "switch"]

CONF_AREAS = "areas"
CONF_LIGHTS = "lights"
CONF_PRESENCE_ENTITIES = "presence_entities"
CONF_LUX_ENTITIES = "lux_entities"
CONF_CONTEXT_ENTITIES = "context_entities"
CONF_WEATHER_ENTITY = "weather_entity"
CONF_WORKDAY_ENTITY = "workday_entity"

CONF_ENABLE_AUTO = "enable_auto"
CONF_COOLDOWN_SECONDS = "cooldown_seconds"
CONF_HYSTERESIS = "hysteresis"
CONF_MAX_DELTA_PER_MIN = "max_delta_per_min"
CONF_TRANSITION_SECONDS = "transition_seconds"
CONF_DONT_TURN_ON = "dont_turn_on_if_off"

CONF_MODEL_TYPE = "model_type"
MODEL_RIDGE = "ridge"
MODEL_KNN_MEDIAN = "knn_median"

CONF_CT_DEFAULT_MIN = "ct_default_min"
CONF_CT_DEFAULT_MAX = "ct_default_max"
CONF_CT_MIN = "ct_min"
CONF_CT_MAX = "ct_max"

CONF_CT_BOUNDS_BY_AREA = "ct_bounds_by_area"
CONF_CT_BOUNDS_BY_LIGHT = "ct_bounds_by_light"

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_store"

