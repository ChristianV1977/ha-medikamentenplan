from __future__ import annotations

import voluptuous as vol

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import UnitOfTime
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .calc import parse_date
from .const import DOMAIN, SIGNAL_NEW, SIGNAL_SCAN
from .entity import MedEntity


async def async_setup_entry(hass, entry, async_add_entities):
    plan = hass.data[DOMAIN][entry.entry_id]

    @callback
    def add(med_id):
        async_add_entities([Reichweite(plan, med_id), Nachbestelldatum(plan, med_id), Status(plan, med_id),
                            VorratPackungen(plan, med_id), ReichweiteInklVorrat(plan, med_id), VorratVerfall(plan, med_id)])

    for med_id in list(plan.meds):
        add(med_id)
    async_add_entities([ScanZustand(plan)])
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_NEW.format(entry.entry_id), add))

    entity_platform.async_get_current_platform().async_register_entity_service(
        "neue_packung",
        {vol.Optional("anbruchdatum"): cv.date, vol.Optional("anzahl_packungen", default=1): vol.All(vol.Coerce(int), vol.Range(min=1)),
         vol.Optional("hersteller"): cv.string,
         vol.Optional("packungsgroesse"): vol.All(vol.Coerce(float), vol.Range(min=0.01))},
        "async_neue_packung",
    )


# Allowlist: Wirkstoff, Hersteller, Notiz, Verschreibungsdatum bleiben bewusst draussen (nur im Options-Flow sichtbar)
ATTR_KEYS = ("name", "zweck", "dosis", "einheit", "modus", "morgens", "mittags", "abends", "nachts", "pro_tag", "intervall_tage", "bedarf_pro_woche",
             "packungsgroesse", "anbruch", "restbestand", "rezeptpflichtig", "vorlauf_tage", "abgesetzt", "abgesetzt_am")
COMPUTED_KEYS = ("tagesverbrauch", "einnahmeschema", "reichweite_tage", "aufbrauchdatum", "nachbestelldatum", "verbleibende_tage", "status",
                 "vorrat_packungen", "vorrat_einheiten", "reichweite_inkl_vorrat_tage", "aufbrauchdatum_inkl_vorrat", "naechster_verfall", "verfall_warnung")


class Reichweite(MedEntity, SensorEntity):
    # Gesundheitsdaten nie in Recorder/InfluxDB-Verlauf: alle Attribute unrecorded
    _unrecorded_attributes = frozenset(("plan", *ATTR_KEYS, *COMPUTED_KEYS))
    _attr_native_unit_of_measurement = UnitOfTime.DAYS
    _attr_device_class = SensorDeviceClass.DURATION

    def __init__(self, plan, med_id):
        super().__init__(plan, med_id, "reichweite")

    @property
    def native_value(self):
        return self.plan.compute(self.med_id)["verbleibende_tage"]

    @property
    def extra_state_attributes(self):
        c = self.plan.compute(self.med_id)
        med = self.plan.meds[self.med_id]
        attrs = {"plan": self.plan.name, **{k: med[k] for k in ATTR_KEYS if k in med}, **c}
        return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in attrs.items()}

    async def async_neue_packung(self, anbruchdatum=None, anzahl_packungen=1, hersteller=None, packungsgroesse=None):
        await self.plan.async_new_pack(self.med_id, anbruchdatum, anzahl_packungen, hersteller, packungsgroesse)


class Nachbestelldatum(MedEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, plan, med_id):
        super().__init__(plan, med_id, "nachbestelldatum")

    @property
    def native_value(self):
        return self.plan.compute(self.med_id)["nachbestelldatum"]


class Status(MedEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["ok", "nachbestellen", "aufgebraucht", "abgesetzt"]

    def __init__(self, plan, med_id):
        super().__init__(plan, med_id, "status")

    @property
    def native_value(self):
        return self.plan.compute(self.med_id)["status"]


class VorratPackungen(MedEntity, SensorEntity):
    """Ungeoeffnete Packungen auf Vorrat."""
    _unrecorded_attributes = frozenset(("packungen", "einheiten", "naechster_verfall", "verfall_warnung"))
    _attr_native_unit_of_measurement = "Packungen"

    def __init__(self, plan, med_id):
        super().__init__(plan, med_id, "vorrat_packungen")

    @property
    def native_value(self):
        return len(self.plan.meds[self.med_id].get("vorrat", []))

    @property
    def extra_state_attributes(self):
        med, c = self.plan.meds[self.med_id], self.plan.compute(self.med_id)
        return {**(super().extra_state_attributes or {}), "packungen": med.get("vorrat", []), "einheiten": c["vorrat_einheiten"],
                "naechster_verfall": c["naechster_verfall"].isoformat() if c["naechster_verfall"] else None,
                "verfall_warnung": c["verfall_warnung"]}


class ReichweiteInklVorrat(MedEntity, SensorEntity):
    _attr_native_unit_of_measurement = UnitOfTime.DAYS
    _attr_device_class = SensorDeviceClass.DURATION

    def __init__(self, plan, med_id):
        super().__init__(plan, med_id, "reichweite_inkl_vorrat")

    @property
    def native_value(self):
        return self.plan.compute(self.med_id)["reichweite_inkl_vorrat_tage"]


class VorratVerfall(MedEntity, SensorEntity):
    """Fruehester Verfall im Vorrat; Warnung (Attribut an VorratPackungen) ab 60 Tagen davor."""
    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, plan, med_id):
        super().__init__(plan, med_id, "vorrat_verfall")

    @property
    def native_value(self):
        return self.plan.compute(self.med_id)["naechster_verfall"]


class ScanZustand(SensorEntity):
    """Zustand des letzten Scans (domainweit): bereit | zuordnung_noetig."""
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "scan_zustand"
    _unrecorded_attributes = frozenset(("pzn",))
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["bereit", "zuordnung_noetig"]

    def __init__(self, plan):
        self.plan = plan
        self._attr_unique_id = f"{plan.entry.entry_id}_scan"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, plan.entry.entry_id)})

    async def async_added_to_hass(self):
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_SCAN, self._refresh))

    @callback
    def _refresh(self):
        self.async_write_ha_state()

    def _pending(self):
        return self.hass.data.get(DOMAIN + "_scan") or {"status": "bereit"}

    @property
    def native_value(self):
        return self._pending()["status"]

    @property
    def extra_state_attributes(self):
        p = self._pending()
        return {"pzn": p.get("pzn")} if p.get("pzn") else None
