from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, SIGNAL_UPDATE
from .plan import Plan


class MedEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, plan: Plan, med_id: str, key: str) -> None:
        self.plan = plan
        self.med_id = med_id
        self._attr_translation_key = key
        self._attr_unique_id = f"{plan.entry.entry_id}_{med_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{plan.entry.entry_id}_{med_id}")},
            name=plan.device_name(med_id),
            manufacturer="Medikamentenplan",  # bewusst kein Hersteller/Medikamentendetails im Geraeteregister
            via_device_id=plan.parent_device_id,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(
            self.hass, SIGNAL_UPDATE.format(self.plan.entry.entry_id), self._refresh))

    @callback
    def _refresh(self) -> None:
        if self.med_id in self.plan.meds:
            self.async_write_ha_state()
