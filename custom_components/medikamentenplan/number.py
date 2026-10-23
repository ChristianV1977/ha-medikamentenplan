from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, SIGNAL_NEW
from .entity import MedEntity


async def async_setup_entry(hass, entry, async_add_entities):
    plan = hass.data[DOMAIN][entry.entry_id]

    @callback
    def add(med_id):
        async_add_entities([Packungsgroesse(plan, med_id), AnzahlPackungen(plan, med_id)])

    for med_id in list(plan.meds):
        add(med_id)
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_NEW.format(entry.entry_id), add))


class Packungsgroesse(MedEntity, NumberEntity):
    """Packungsgroesse; Aenderung wird sofort im Store gesichert."""
    _lock_when_stopped = True
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 1
    _attr_native_max_value = 10000
    _attr_native_step = 1

    def __init__(self, plan, med_id):
        super().__init__(plan, med_id, "packungsgroesse")

    @property
    def native_value(self):
        v = self.plan.meds[self.med_id].get("packungsgroesse")
        return float(v) if v is not None else None

    async def async_set_native_value(self, value: float) -> None:
        await self.plan.async_set_field(self.med_id, "packungsgroesse", float(value))


class AnzahlPackungen(MedEntity, NumberEntity):
    """Vorgabe fuer die naechste neue Packung (nur im Speicher, nach dem Button wieder 1)."""
    _lock_when_stopped = True
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 1
    _attr_native_max_value = 20
    _attr_native_step = 1

    def __init__(self, plan, med_id):
        super().__init__(plan, med_id, "anzahl_packungen")

    @property
    def native_value(self):
        return float(self.plan.packs.get(self.med_id, 1))

    async def async_set_native_value(self, value: float) -> None:
        self.plan.packs[self.med_id] = int(value)
        self.plan.notify()
