from __future__ import annotations

from dataclasses import dataclass, field

from homeassistant.core import HomeAssistant
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


class MLBrightnessStore:
    def __init__(self, hass: HomeAssistant) -> None:
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.data = MLBrightnessStoreData()

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
        self.data = MLBrightnessStoreData(by_light=by_light)

    async def async_save(self) -> None:
        raw = {
            "by_light": {
                ent_id: {"w": st.w, "p": st.p, "n": st.n, "examples": st.examples}
                for ent_id, st in self.data.by_light.items()
            }
        }
        await self._store.async_save(raw)

