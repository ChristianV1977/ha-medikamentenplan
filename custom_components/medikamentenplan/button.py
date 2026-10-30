from __future__ import annotations

from homeassistant.components import persistent_notification
from homeassistant.components.button import ButtonEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, SIGNAL_NEW
from .entity import MedEntity


async def async_setup_entry(hass, entry, async_add_entities):
    plan = hass.data[DOMAIN][entry.entry_id]
    @callback
    def add(med_id):
        async_add_entities([NeuePackung(plan, med_id), AufVorrat(plan, med_id)])

    for med_id in list(plan.meds):
        add(med_id)
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_NEW.format(entry.entry_id), add))


class NeuePackung(MedEntity, ButtonEntity):
    def __init__(self, plan, med_id):
        super().__init__(plan, med_id, "neue_packung")

    async def async_press(self) -> None:
        fall = await self.plan.async_open_pack(self.med_id)
        name = self.plan.meds[self.med_id].get("name", self.med_id)
        persistent_notification.async_create(
            self.hass,
            f"{name}: Packung aus dem Vorrat angebrochen." if fall == "vorrat"
            else f"{name}: neu gekaufte Packung angefangen (kein Vorrat vorhanden).",
            title="Neue Packung angefangen", notification_id=f"medikamentenplan_{self.med_id}_packung")



class AufVorrat(MedEntity, ButtonEntity):
    """Ungeoeffnete Packung(en) ohne Scan auf Vorrat legen (Groesse/Anzahl aus den Popup-Feldern, Verfall unbekannt)."""
    _lock_when_stopped = True

    def __init__(self, plan, med_id):
        super().__init__(plan, med_id, "auf_vorrat_legen")

    async def async_press(self) -> None:
        anzahl = self.plan.packs.get(self.med_id, 1)
        await self.plan.async_add_stock(self.med_id, self.plan.meds[self.med_id].get("packungsgroesse"), None, None, anzahl)
        self.plan.packs.pop(self.med_id, None)
        self.plan.notify()
        name = self.plan.meds[self.med_id].get("name", self.med_id)
        persistent_notification.async_create(
            self.hass, f"{name}: {anzahl} Packung(en) auf Vorrat gelegt.",
            title="Auf Vorrat gelegt", notification_id=f"medikamentenplan_{self.med_id}_vorrat")
