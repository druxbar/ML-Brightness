from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION


@dataclass
class LightModelState:
    # online ridge weights (including bias at index 0)
    w: list[float] = field(default_factory=list)
    # inverse covariance diagonal approximation for RLS-like update
    p: list[float] = field(default_factory=list)
    # counters
    n: int = 0
    # recent examples for kNN: list of {"x":[...], "y":float, "t":int}
    examples: list[dict] = field(default_factory=list)


@dataclass
class MLBrightnessStoreData:
    by_light: dict[str, LightModelState] = field(default_factory=dict)
    by_area: dict[str, LightModelState] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)


class MLBrightnessStore:
    def __init__(self, hass: HomeAssistant) -> None:
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.hass = hass
        self.data = MLBrightnessStoreData()
        self._save_debounce: CALLBACK_TYPE | None = None

    async def async_load(self) -> None:
        raw = await self._store.async_load()
        if not raw:
            return

        by_light: dict[str, LightModelState] = {}
        for ent_id, payload in (raw.get("by_light") or {}).items():
            by_light[ent_id] = LightModelState(
                w=list(payload.get("w") or []),
                p=list(payload.get("p") or []),
                n=int(payload.get("n") or 0),
                examples=list(payload.get("examples") or []),
            )
        by_area: dict[str, LightModelState] = {}
        for area_id, payload in (raw.get("by_area") or {}).items():
            by_area[area_id] = LightModelState(
                w=list(payload.get("w") or []),
                p=list(payload.get("p") or []),
                n=int(payload.get("n") or 0),
                examples=list(payload.get("examples") or []),
            )
        meta = dict(raw.get("meta") or {})
        self.data = MLBrightnessStoreData(by_light=by_light, by_area=by_area, meta=meta)

    async def async_save(self) -> None:
        raw = {
            "by_light": {
                ent_id: {"w": st.w, "p": st.p, "n": st.n, "examples": st.examples}
                for ent_id, st in self.data.by_light.items()
            },
            "by_area": {
                area_id: {"w": st.w, "p": st.p, "n": st.n, "examples": st.examples}
                for area_id, st in self.data.by_area.items()
            },
            "meta": dict(self.data.meta),
        }
        await self._store.async_save(raw)

    def async_schedule_save(self, delay_sec: float = 2.0) -> None:
        """Debounce disk writes; coalesce rapid trainer updates."""

        if self._save_debounce is not None:
            self._save_debounce()
            self._save_debounce = None

        async def _do_save() -> None:
            await self.async_save()

        def _fire(_now: Any) -> None:
            self.hass.async_create_task(_do_save())

        self._save_debounce = async_call_later(self.hass, delay_sec, _fire)
