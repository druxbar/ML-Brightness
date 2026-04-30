from __future__ import annotations

import time
from collections import deque
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
    CONF_LEARN_NON_USER_CHANGES,
    CONF_LIGHTS,
    DOMAIN,
    entry_cfg,
)
from .light_control import apply_recommendations
from .storage import MLBrightnessStore
from .bootstrap import maybe_bootstrap_history


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
        self._override_until: datetime | None = None
        self._ml_context_ids: deque[tuple[str, float]] = deque(maxlen=64)
        self._unsub = None

    def _recent_ml_context(self, context_id: str | None) -> bool:
        if not context_id:
            return False
        now_m = time.monotonic()
        while self._ml_context_ids and now_m - self._ml_context_ids[0][1] > 45.0:
            self._ml_context_ids.popleft()
        return any(cid == context_id for cid, _ts in self._ml_context_ids)

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
        self.hass.async_create_task(maybe_bootstrap_history(self.hass, self.entry, self.store))
        await super().async_config_entry_first_refresh()

    def set_override_until(self, until: datetime | None) -> None:
        self._override_until = until

    def _setup_listeners(self) -> None:
        if self._unsub is not None:
            return

        cfg = entry_cfg(self.entry)
        lights = set(cfg.get(CONF_LIGHTS) or [])
        area_ids = set(cfg.get(CONF_AREAS) or [])
        if area_ids:
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

        self._unsub = async_track_state_change_event(self.hass, list(lights), _on_state_change)
