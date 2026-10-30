"""Plan = ein Config-Entry mit seinen Medikamenten, persistiert im HA Store."""
from __future__ import annotations

import uuid

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import calc
from .const import DOMAIN, SIGNAL_NEW, SIGNAL_UPDATE, STORAGE_VERSION


class Plan:
    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.parent_device_id: str | None = None
        self.hass = hass
        self.entry = entry
        self.store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self.meds: dict[str, dict] = {}
        self.packs: dict[str, int] = {}  # Vorgabe Anzahl Packungen je Medikament, nur im Speicher
        self.pzn: dict[str, dict] = {}  # PZN -> {"med": med_id, "groesse": float|None}
        self.serials: dict[str, str] = {}  # gebuchte Seriennummern "pzn|serial" -> Datum

    @property
    def name(self) -> str:
        return self.entry.title

    async def async_load(self) -> None:
        raw = await self.store.async_load()
        data = calc.migrate_store(raw)
        self.meds, self.pzn, self.serials = data["meds"], data["pzn"], data["serials"]
        if raw is not None and raw.get("schema") != 2:
            await self._save()  # Migration auf Schema 2 persistieren (Backup liegt vorher)

    async def _save(self) -> None:
        await self.store.async_save({"schema": 2, "meds": self.meds, "pzn": self.pzn, "serials": self.serials})

    def compute(self, med_id: str) -> dict:
        return calc.compute(self.meds[med_id], dt_util.now().date())

    def device_name(self, med_id: str) -> str:
        # Praefix "Medikament" -> entity_ids sensor.medikament_*, gezielt aus Recorder/InfluxDB ausschliessbar
        return f"Medikament {self.meds[med_id]['name']} ({self.name})"

    async def async_add(self, med: dict) -> str:
        med_id = uuid.uuid4().hex[:12]  # stabile Unique-ID-Basis
        self.meds[med_id] = med
        await self._save()
        async_dispatcher_send(self.hass, SIGNAL_NEW.format(self.entry.entry_id), med_id)
        return med_id

    async def async_update(self, med_id: str, med: dict) -> None:
        self.meds[med_id] = med
        await self._save()
        dev = dr.async_get(self.hass).async_get_device_by_identifier((DOMAIN, f"{self.entry.entry_id}_{med_id}"), self.entry.entry_id)
        if dev:
            dr.async_get(self.hass).async_update_device(dev.id, name=self.device_name(med_id))
        self.notify()

    async def async_set_field(self, med_id: str, key: str, value) -> None:
        await self.async_update(med_id, calc.set_field(self.meds[med_id], key, value))

    async def async_delete(self, med_id: str) -> None:
        self.meds.pop(med_id, None)
        self.pzn = {k: v for k, v in self.pzn.items() if v.get("med") != med_id}
        await self._save()
        reg = dr.async_get(self.hass)
        if dev := reg.async_get_device_by_identifier((DOMAIN, f"{self.entry.entry_id}_{med_id}"), self.entry.entry_id):
            reg.async_remove_device(dev.id)

    async def async_new_pack(self, med_id: str, start=None, packs: int = 1, hersteller=None, packungsgroesse=None) -> None:
        if self.meds[med_id].get("abgesetzt"):
            raise ServiceValidationError("Medikament ist abgesetzt - zuerst reaktivieren.")
        start = start or dt_util.now().date()
        await self.async_update(med_id, calc.new_pack(self.meds[med_id], start, packs, hersteller, packungsgroesse))
        self.packs.pop(med_id, None)

    async def async_add_stock(self, med_id: str, groesse=None, verfall=None, charge=None, anzahl: int = 1) -> None:
        await self.async_update(med_id, calc.add_stock(self.meds[med_id], groesse, verfall, charge, anzahl))

    async def async_from_stock(self, med_id: str, start=None) -> None:
        """Aelteste (Verfall) Packung aus dem Vorrat anbrechen."""
        if self.meds[med_id].get("abgesetzt"):
            raise ServiceValidationError("Medikament ist abgesetzt - zuerst reaktivieren.")
        try:
            med, pack = calc.take_stock(self.meds[med_id])
        except ValueError as e:
            raise ServiceValidationError(str(e)) from e
        groesse = pack.get("groesse")
        await self.async_update(med_id, calc.new_pack(med, start or dt_util.now().date(), 1, None, groesse))
        self.packs.pop(med_id, None)

    async def async_remove_last_stock(self, med_id: str) -> None:
        try:
            await self.async_update(med_id, calc.remove_last_stock(self.meds[med_id]))
        except ValueError as e:
            raise ServiceValidationError(str(e)) from e

    async def async_learn_pzn(self, pzn: str, med_id: str, groesse=None) -> None:
        old = self.pzn.get(pzn, {})
        self.pzn[pzn] = {"med": med_id, "groesse": groesse if groesse is not None else old.get("groesse")}
        await self._save()

    async def async_book_serial(self, key: str) -> None:
        self.serials = calc.remember_serial(self.serials, key, dt_util.now().date())
        await self._save()

    def notify(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_UPDATE.format(self.entry.entry_id))
