from __future__ import annotations

import voluptuous as vol

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import UnitOfTime
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .calc import parse_date
from .const import DOMAIN, SIGNAL_NEW
from .entity import MedEntity


async def async_setup_entry(hass, entry, async_add_entities):
    plan = hass.data[DOMAIN][entry.entry_id]

    @callback
    def add(med_id):
        async_add_entities([Reichweite(plan, med_id), Nachbestelldatum(plan, med_id), Status(plan, med_id)])

    for med_id in list(plan.meds):
        add(med_id)
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_NEW.format(entry.entry_id), add))

    entity_platform.async_get_current_platform().async_register_entity_service(
        "neue_packung",
        {vol.Optional("anbruchdatum"): cv.date, vol.Optional("anzahl_packungen", default=1): vol.All(vol.Coerce(int), vol.Range(min=1))},
        "async_neue_packung",
    )


# Allowlist: Wirkstoff, Hersteller, Notiz, Verschreibungsdatum bleiben bewusst draussen (nur im Options-Flow sichtbar)
ATTR_KEYS = ("name", "zweck", "dosis", "einheit", "modus", "morgens", "mittags", "abends", "nachts", "pro_tag", "intervall_tage", "bedarf_pro_woche",
             "packungsgroesse", "anbruch", "restbestand", "rezeptpflichtig", "vorlauf_tage")
COMPUTED_KEYS = ("tagesverbrauch", "einnahmeschema", "reichweite_tage", "aufbrauchdatum", "nachbestelldatum", "verbleibende_tage", "status")


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

    async def async_neue_packung(self, anbruchdatum=None, anzahl_packungen=1):
        await self.plan.async_new_pack(self.med_id, anbruchdatum, anzahl_packungen)


class Nachbestelldatum(MedEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, plan, med_id):
        super().__init__(plan, med_id, "nachbestelldatum")

    @property
    def native_value(self):
        return self.plan.compute(self.med_id)["nachbestelldatum"]


class Status(MedEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["ok", "nachbestellen", "aufgebraucht"]

    def __init__(self, plan, med_id):
        super().__init__(plan, med_id, "status")

    @property
    def native_value(self):
        return self.plan.compute(self.med_id)["status"]
