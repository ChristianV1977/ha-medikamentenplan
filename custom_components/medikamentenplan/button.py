from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, SIGNAL_NEW
from .entity import MedEntity


async def async_setup_entry(hass, entry, async_add_entities):
    plan = hass.data[DOMAIN][entry.entry_id]
    @callback
    def add(med_id):
        async_add_entities([NeuePackung(plan, med_id), AusVorrat(plan, med_id)])

    for med_id in list(plan.meds):
        add(med_id)
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_NEW.format(entry.entry_id), add))


class NeuePackung(MedEntity, ButtonEntity):
    def __init__(self, plan, med_id):
        super().__init__(plan, med_id, "neue_packung")

    async def async_press(self) -> None:
        await self.plan.async_new_pack(self.med_id, packs=self.plan.packs.get(self.med_id, 1))


class AusVorrat(MedEntity, ButtonEntity):
    """Packung mit fruehestem Verfall aus dem Vorrat anbrechen."""
    def __init__(self, plan, med_id):
        super().__init__(plan, med_id, "aus_vorrat_anbrechen")

    @property
    def available(self) -> bool:
        return super().available and bool(self.plan.meds[self.med_id].get("vorrat"))

    async def async_press(self) -> None:
        await self.plan.async_from_stock(self.med_id)
