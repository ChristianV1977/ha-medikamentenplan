from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity

from .const import DOMAIN
from .entity import PlanEntity
from .erinnerung import SLOTS


async def async_setup_entry(hass, entry, async_add_entities):
    plan = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([*(ErinnerungsZeit(plan, s) for s in SLOTS), NachkaufZeit(plan)])


def _t(txt: str) -> time:
    h, m = txt.split(":")[:2]
    return time(int(h), int(m))


class ErinnerungsZeit(PlanEntity, TimeEntity):
    def __init__(self, plan, slot):
        super().__init__(plan, f"zeit_{slot}")
        self._slot = slot

    @property
    def native_value(self) -> time:
        return _t(self.plan.settings["zeiten"][self._slot])

    async def async_set_value(self, value: time) -> None:
        await self.plan.async_set_setting("zeiten", value.strftime("%H:%M"), slot=self._slot)


class NachkaufZeit(PlanEntity, TimeEntity):
    def __init__(self, plan):
        super().__init__(plan, "zeit_nachkauf")

    @property
    def native_value(self) -> time:
        return _t(self.plan.settings["nachkauf_zeit"])

    async def async_set_value(self, value: time) -> None:
        await self.plan.async_set_setting("nachkauf_zeit", value.strftime("%H:%M"))
