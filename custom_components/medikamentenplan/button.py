from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, SIGNAL_NEW
from .entity import MedEntity


async def async_setup_entry(hass, entry, async_add_entities):
    plan = hass.data[DOMAIN][entry.entry_id]
    add = lambda med_id: async_add_entities([NeuePackung(plan, med_id)])  # noqa: E731
    for med_id in list(plan.meds):
        add(med_id)
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_NEW.format(entry.entry_id), add))


class NeuePackung(MedEntity, ButtonEntity):
    def __init__(self, plan, med_id):
        super().__init__(plan, med_id, "neue_packung")

    async def async_press(self) -> None:
        await self.plan.async_new_pack(self.med_id)
