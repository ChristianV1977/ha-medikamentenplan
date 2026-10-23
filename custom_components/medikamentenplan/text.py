from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, SIGNAL_NEW
from .entity import MedEntity


async def async_setup_entry(hass, entry, async_add_entities):
    plan = hass.data[DOMAIN][entry.entry_id]

    @callback
    def add(med_id):
        async_add_entities([Hersteller(plan, med_id)])

    for med_id in list(plan.meds):
        add(med_id)
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_NEW.format(entry.entry_id), add))


class Hersteller(MedEntity, TextEntity):
    """Gespeicherter Hersteller; Aenderung wird sofort im Store gesichert (leer = Angabe entfernen)."""
    _lock_when_stopped = True
    _attr_native_max = 255

    def __init__(self, plan, med_id):
        super().__init__(plan, med_id, "hersteller")

    @property
    def native_value(self):
        return self.plan.meds[self.med_id].get("hersteller", "")

    async def async_set_value(self, value: str) -> None:
        await self.plan.async_set_field(self.med_id, "hersteller", value.strip() or None)
