from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .catalog import hersteller
from .const import DOMAIN, SIGNAL_NEW
from .entity import MedEntity

NONE = "– (kein Hersteller)"


async def async_setup_entry(hass, entry, async_add_entities):
    plan = hass.data[DOMAIN][entry.entry_id]
    katalog = sorted(await hass.async_add_executor_job(hersteller), key=str.casefold)

    @callback
    def add(med_id):
        async_add_entities([Hersteller(plan, med_id, katalog)])

    for med_id in list(plan.meds):
        add(med_id)
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_NEW.format(entry.entry_id), add))


class Hersteller(MedEntity, SelectEntity):
    """Hersteller als Pulldown (Katalog + aktuell gespeicherter Wert); freie Werte weiter ueber den Options-Dialog."""
    _lock_when_stopped = True

    def __init__(self, plan, med_id, katalog):
        super().__init__(plan, med_id, "hersteller")
        self._katalog = katalog

    @property
    def current_option(self):
        return self.plan.meds[self.med_id].get("hersteller") or NONE

    @property
    def options(self):
        cur = self.plan.meds[self.med_id].get("hersteller")
        extra = [cur] if cur and cur not in self._katalog else []  # shortcut: freier Wert nur aus Options-Dialog
        return [NONE, *sorted([*self._katalog, *extra], key=str.casefold)]

    async def async_select_option(self, option: str) -> None:
        await self.plan.async_set_field(self.med_id, "hersteller", None if option == NONE else option)
