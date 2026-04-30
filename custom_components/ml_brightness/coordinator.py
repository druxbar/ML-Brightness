from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import CALLBACK_TYPE, Context, HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_AREAS,
    CONF_LEARN_NON_USER_CHANGES,
    CONF_LIGHTS,
    CONF_PRESENCE_BY_AREA,
    CONF_PRESENCE_CLEAR_DIM_PCT,
    CONF_PRESENCE_CLEAR_DIM_TRANSITION_SEC,
    CONF_PRESENCE_CLEAR_OFF_AFTER_DIM_SEC,
    CONF_PRESENCE_CLEAR_TWO_STAGE,
    CONF_PRESENCE_ENTITIES,
    DOMAIN,
    entry_cfg,
)
from .bootstrap import maybe_bootstrap_history
from .light_control import (
    _brightness_from_pct,
    _light_supports_brightness,
    apply_recommendations,
    presence_ok_for_light,
)
from .storage import MLBrightnessStore


@dataclass(frozen=True)
class MLBrightnessData:
    recommended_brightness_pct: float | None
    confidence: float | None


def _tracked_lights(hass: HomeAssistant, cfg: dict) -> set[str]:
    lights: set[str] = set(cfg.get(CONF_LIGHTS) or [])
    area_ids = set(cfg.get(CONF_AREAS) or [])
    if area_ids:
        ent_reg = er.async_get(hass)
        for ent in ent_reg.entities.values():
            if ent.domain == "light" and ent.area_id in area_ids:
                lights.add(ent.entity_id)
    return lights


def _presence_sensor_entity_ids(cfg: dict) -> list[str]:
    out: list[str] = list(cfg.get(CONF_PRESENCE_ENTITIES) or [])
    by_area = cfg.get(CONF_PRESENCE_BY_AREA) or {}
    if isinstance(by_area, dict):
        for ents in by_area.values():
            if isinstance(ents, list):
                out.extend(ents)
    return list(dict.fromkeys(out))


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
        self._override_until: datetime | None = None
        self._ml_context_ids: deque[tuple[str, float]] = deque(maxlen=64)
        self._unsub_lights: CALLBACK_TYPE | None = None
        self._unsub_presence: CALLBACK_TYPE | None = None
        self._prev_presence_by_light: dict[str, bool] = {}
        self._presence_clear_handles: dict[str, tuple[CALLBACK_TYPE | None, CALLBACK_TYPE | None]] = {}

    def _recent_ml_context(self, context_id: str | None) -> bool:
        if not context_id:
            return False
        now_m = time.monotonic()
        while self._ml_context_ids and now_m - self._ml_context_ids[0][1] > 45.0:
            self._ml_context_ids.popleft()
        return any(cid == context_id for cid, _ts in self._ml_context_ids)

    def _record_ml_context(self, ctx: Context) -> None:
        if ctx.id:
            self._ml_context_ids.append((ctx.id, time.monotonic()))

    def _override_active(self) -> bool:
        if self._override_until is None:
            return False
        return datetime.now(timezone.utc) < self._override_until

    async def async_shutdown(self) -> None:
        if self._unsub_lights is not None:
            self._unsub_lights()
            self._unsub_lights = None
        if self._unsub_presence is not None:
            self._unsub_presence()
            self._unsub_presence = None
        for light_id in list(self._presence_clear_handles.keys()):
            self._cancel_presence_clear(light_id)
        self._prev_presence_by_light.clear()

    def _cancel_presence_clear(self, light_id: str) -> None:
        pair = self._presence_clear_handles.pop(light_id, None)
        if not pair:
            return
        for h in pair:
            if h is not None:
                h()

    async def _async_dim_staging(self, light_id: str, dim_pct: float, dim_trans: float) -> None:
        cfg = entry_cfg(self.entry)
        if not cfg.get(CONF_PRESENCE_CLEAR_TWO_STAGE) or self._override_active():
            return
        ok = presence_ok_for_light(self.hass, cfg, light_id)
        if ok is not False:
            return
        st = self.hass.states.get(light_id)
        if not st or st.state == "off" or not _light_supports_brightness(st):
            return
        ctx = Context()
        await self.hass.services.async_call(
            "light",
            "turn_on",
            {
                "entity_id": light_id,
                "brightness": _brightness_from_pct(dim_pct),
                "transition": max(1.0, dim_trans),
            },
            blocking=False,
            context=ctx,
        )
        self._record_ml_context(ctx)
        now = datetime.now(timezone.utc)
        self._last_set[light_id] = (now, st.attributes.get("brightness"))

    async def _async_try_full_off(self, light_id: str) -> None:
        cfg = entry_cfg(self.entry)
        if not cfg.get(CONF_PRESENCE_CLEAR_TWO_STAGE) or self._override_active():
            return
        ok = presence_ok_for_light(self.hass, cfg, light_id)
        if ok is not False:
            return
        st = self.hass.states.get(light_id)
        if not st or st.state == "off":
            return
        trans = max(1, int(cfg.get(CONF_TRANSITION_SECONDS, 2)))
        ctx = Context()
        await self.hass.services.async_call(
            "light",
            "turn_off",
            {"entity_id": light_id, "transition": trans},
            blocking=False,
            context=ctx,
        )
        self._record_ml_context(ctx)
        now = datetime.now(timezone.utc)
        self._last_set[light_id] = (now, None)

    def _schedule_presence_clear(self, light_id: str) -> None:
        self._cancel_presence_clear(light_id)
        cfg = entry_cfg(self.entry)
        dim_pct = float(cfg.get(CONF_PRESENCE_CLEAR_DIM_PCT, 10.0))
        dim_trans = float(cfg.get(CONF_PRESENCE_CLEAR_DIM_TRANSITION_SEC, 8.0))
        off_after = float(cfg.get(CONF_PRESENCE_CLEAR_OFF_AFTER_DIM_SEC, 12.0))

        def dim_cb(_now: datetime | None = None) -> None:
            self.hass.async_create_task(self._async_dim_staging(light_id, dim_pct, dim_trans))

        def off_cb(_now: datetime | None = None) -> None:
            self.hass.async_create_task(self._async_try_full_off(light_id))

        h1 = async_call_later(self.hass, 0, dim_cb)
        h2 = async_call_later(self.hass, max(5.0, off_after), off_cb)
        self._presence_clear_handles[light_id] = (h1, h2)

    async def _on_presence_change(self) -> None:
        cfg = entry_cfg(self.entry)
        if not cfg.get(CONF_PRESENCE_CLEAR_TWO_STAGE):
            return
        lights = _tracked_lights(self.hass, cfg)
        for light_id in sorted(lights):
            if self.hass.states.get(light_id) is None:
                continue
            now_ok = presence_ok_for_light(self.hass, cfg, light_id)
            if now_ok is None:
                continue
            active = bool(now_ok)
            prev = self._prev_presence_by_light.get(light_id)
            self._prev_presence_by_light[light_id] = active
            if prev is None:
                continue
            if prev and not active:
                self._schedule_presence_clear(light_id)
            elif not prev and active:
                self._cancel_presence_clear(light_id)

    def _setup_presence_clear_listener(self) -> None:
        if self._unsub_presence is not None:
            return
        cfg = entry_cfg(self.entry)
        if not cfg.get(CONF_PRESENCE_CLEAR_TWO_STAGE):
            return
        ids = _presence_sensor_entity_ids(cfg)
        if not ids:
            return

        def _cb(_event: Any) -> None:
            self.hass.async_create_task(self._on_presence_change())

        self._unsub_presence = async_track_state_change_event(self.hass, ids, _cb)

    async def _async_update_data(self) -> MLBrightnessData:
        ml_ctx: list[str] = []
        rec = await apply_recommendations(
            self.hass,
            self.entry,
            self.store,
            self._last_set,
            self._last_manual,
            pred_hold=self._pred_hold,
            override_until=self._override_until,
            ml_context_ids=ml_ctx,
        )
        now_m = time.monotonic()
        for cid in ml_ctx:
            self._ml_context_ids.append((cid, now_m))
        return MLBrightnessData(
            recommended_brightness_pct=rec.recommended_brightness_pct,
            confidence=rec.confidence,
        )

    async def async_config_entry_first_refresh(self) -> None:
        await self.store.async_load()
        self._setup_listeners()
        self._setup_presence_clear_listener()
        self.hass.async_create_task(maybe_bootstrap_history(self.hass, self.entry, self.store))
        await super().async_config_entry_first_refresh()

    def set_override_until(self, until: datetime | None) -> None:
        self._override_until = until

    def _setup_listeners(self) -> None:
        if self._unsub_lights is not None:
            return

        cfg = entry_cfg(self.entry)
        lights = _tracked_lights(self.hass, cfg)
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

            nb = new_state.attributes.get("brightness")
            ob = old_state.attributes.get("brightness")
            if nb is None or nb == ob:
                return

            now = datetime.now(timezone.utc)
            last = self._last_set.get(entity_id)
            if last and (now - last[0]).total_seconds() < 5:
                return

            ctx_id = getattr(new_state.context, "id", None)
            if self._recent_ml_context(ctx_id):
                self.hass.async_create_task(self.async_request_refresh())
                return

            cfg2 = entry_cfg(self.entry)
            learn_any = bool(cfg2.get(CONF_LEARN_NON_USER_CHANGES, False))
            user_id = getattr(new_state.context, "user_id", None)

            should_train = False
            if learn_any:
                should_train = True
            elif user_id:
                should_train = True

            if should_train:
                self._last_manual[entity_id] = now
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

            self.hass.async_create_task(self.async_request_refresh())

        self._unsub_lights = async_track_state_change_event(self.hass, list(lights), _on_state_change)
