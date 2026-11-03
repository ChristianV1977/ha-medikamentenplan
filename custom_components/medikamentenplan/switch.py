from __future__ import annotations

from homeassistant.components.switch import SwitchEntity

from .const import DOMAIN
from .entity import PlanEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ErinnerungenAktiv(hass.data[DOMAIN][entry.entry_id])])


class ErinnerungenAktiv(PlanEntity, SwitchEntity):
    def __init__(self, plan):
        super().__init__(plan, "erinnerungen_aktiv")

    @property
    def is_on(self) -> bool:
        return bool(self.plan.settings["aktiv"])

    async def async_turn_on(self, **kwargs) -> None:
        await self.plan.async_set_setting("aktiv", True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.plan.async_set_setting("aktiv", False)
