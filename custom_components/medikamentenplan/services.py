"""Scan-/Vorrat-Services (domainweit, mit Antwort fuer die Scanner-Karte)."""
from __future__ import annotations

from datetime import date

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from . import calc, gs1, pflege
from .const import DOMAIN, FORMS, MODES, SIGNAL_SCAN

CODE = {vol.Required("code"): cv.string}
ENT = {vol.Optional("entity_id"): cv.entity_id}
PLAN = {vol.Optional("plan"): cv.string}  # Personensicht: nur Plaene mit diesem Titel (Scan-Karte Option plan)
GROESSE = {vol.Optional("packungsgroesse"): vol.All(vol.Coerce(float), vol.Range(min=0.01))}


def _n(**kw):
    return vol.All(vol.Coerce(float), vol.Range(**kw))


# Pflege-Felder: gleiche Grenzen wie das Formular im Options-Flow
PFLEGE = {
    vol.Optional("name"): vol.All(cv.string, vol.Length(min=1, max=80)), vol.Optional("pzn"): cv.string,
    vol.Optional("darreichungsform"): vol.In(FORMS), vol.Optional("dosis"): _n(min=0.01), vol.Optional("einheit"): cv.string,
    vol.Optional("modus"): vol.In(MODES),
    **{vol.Optional(k): _n(min=0) for k in ("morgens", "mittags", "abends", "nachts", "pro_tag", "bedarf_pro_woche", "restbestand", "vorlauf_tage")},
    vol.Optional("intervall_tage"): _n(min=1), vol.Optional("packungsgroesse"): _n(min=0.01), vol.Optional("anbruch"): cv.date,
    vol.Optional("hersteller"): cv.string, vol.Optional("wirkstoff"): cv.string, vol.Optional("zweck"): cv.string,
    vol.Optional("notiz"): cv.string, vol.Optional("rezeptpflichtig"): cv.boolean,
}
PLAN_REQ = {vol.Required("plan"): cv.string}


def _plan(hass, name):
    plans = _plans(hass, name)
    if not plans:
        raise ServiceValidationError(f"Plan {name} unbekannt.")
    return plans[0]


def _fields(call) -> dict:
    return {k: (v.isoformat() if isinstance(v, date) else v) for k, v in call.data.items() if k not in ("plan", "entity_id", "bestaetigen", "abgesetzt", "abgesetzt_am")}


def _check(med):
    if errs := pflege.validate(med):
        raise ServiceValidationError(f"Angabe fehlt oder ungueltig: {', '.join(errs)}")


async def _learn(plan, med_id, pzn, groesse):
    try:
        key = pflege.normalize_pzn(pzn)
    except ValueError as e:
        raise ServiceValidationError(str(e)) from e
    await plan.async_learn_pzn(key, med_id, groesse)


def _plans(hass, name=None):
    return [p for p in hass.data.get(DOMAIN, {}).values() if hasattr(p, "meds") and (not name or p.name == name)]


def _entity(hass, plan, med_id) -> str | None:
    return er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{plan.entry.entry_id}_{med_id}_reichweite")


def _info(hass, plan, med_id) -> dict:
    m = plan.meds[med_id]
    return {"entity_id": _entity(hass, plan, med_id), "name": m["name"], "plan": plan.name,
            "packungsgroesse": m.get("packungsgroesse"), "vorrat_packungen": len(m.get("vorrat", []))}


def resolve_entity(hass, entity_id: str, name=None):
    ent = er.async_get(hass).async_get(entity_id)
    if ent and ent.platform == DOMAIN:
        for plan in _plans(hass, name):
            pre = plan.entry.entry_id + "_"
            if ent.unique_id.startswith(pre) and (med_id := ent.unique_id[len(pre):].split("_")[0]) in plan.meds:
                return plan, med_id
    raise ServiceValidationError(f"{entity_id} gehoert zu keinem Medikament dieser Integration.")


def find_pzn(hass, pzn, name=None) -> list:
    """Alle Medikamente (plan, med_id) mit dieser PZN - zwei Personen koennen dasselbe Praeparat haben."""
    return [(p, m["med"]) for p in _plans(hass, name) if (m := p.pzn.get(pzn)) and m.get("med") in p.meds]


def _key(sc: gs1.Scan) -> str | None:
    return sc.key


def _serial_key(sc: gs1.Scan) -> str | None:
    return sc.serial_key


def _dup(hass, sc) -> bool:  # Seriennummer-Sperre bewusst planuebergreifend (dieselbe Packung nie zweimal)
    k = _serial_key(sc)
    return bool(k and any(k in p.serials for p in _plans(hass)))


def _parse(code: str) -> gs1.Scan:
    sc = gs1.parse(code)
    if sc.fehler:
        raise ServiceValidationError(f"Code nicht lesbar: {sc.fehler}")
    return sc


def _target(hass, sc, entity_id, name=None):
    """Medikament aus entity_id (lernt dabei die PZN) oder aus der PZN-Zuordnung."""
    if entity_id:
        return resolve_entity(hass, entity_id, name), True
    hits = find_pzn(hass, _key(sc), name) if _key(sc) else []
    if len(hits) == 1:
        return hits[0], False
    raise ServiceValidationError("PZN mehreren Medikamenten zugeordnet - entity_id angeben." if hits
                                 else "PZN unbekannt - Medikament zuordnen (entity_id angeben).")


async def _prepare(hass, call):
    sc = _parse(call.data["code"])
    (plan, med_id), explicit = _target(hass, sc, call.data.get("entity_id"), call.data.get("plan"))
    if _dup(hass, sc):
        raise ServiceValidationError("Diese Packung (Seriennummer) wurde bereits gebucht.")
    groesse = call.data.get("packungsgroesse")
    if explicit and _key(sc):  # erste Zuordnung / bewusste Umbuchung lernt die PZN
        await plan.async_learn_pzn(_key(sc), med_id, groesse)
    if groesse is None:
        groesse = (plan.pzn.get(_key(sc)) or {}).get("groesse") if _key(sc) else None
    return sc, plan, med_id, groesse


def _done(hass):
    hass.data[DOMAIN + "_scan"] = {"status": "bereit"}
    async_dispatcher_send(hass, SIGNAL_SCAN)


async def async_setup_services(hass: HomeAssistant) -> None:
    async def scan_code(call: ServiceCall):
        sc = gs1.parse(call.data["code"])
        base = {"pzn": sc.pzn, "gtin": sc.gtin, "charge": sc.charge,
                "verfall": sc.verfall.isoformat() if sc.verfall else None, "seriennummer_vorhanden": bool(sc.seriennummer)}
        if sc.fehler:
            return {"status": "ungueltig", "fehler": sc.fehler, **base}
        hits = find_pzn(hass, _key(sc), call.data.get("plan")) if _key(sc) else []
        dup = _dup(hass, sc)
        if hits:
            hass.data[DOMAIN + "_scan"] = {"status": "bereit"}
            res = {"status": "doppelt" if dup else "bekannt", "medikamente": [_info(hass, p, i) for p, i in hits]}
        else:
            hass.data[DOMAIN + "_scan"] = {"status": "zuordnung_noetig", "pzn": _key(sc)}
            cands = [_info(hass, p, i) for p in _plans(hass, call.data.get("plan")) for i, m in p.meds.items() if not m.get("abgesetzt")]
            res = {"status": "doppelt" if dup else "zuordnung_noetig", "kandidaten": cands}
        async_dispatcher_send(hass, SIGNAL_SCAN)
        return {**res, **base}

    async def scan_abbrechen(call: ServiceCall):
        _done(hass)

    async def vorrat_hinzufuegen(call: ServiceCall):
        sc, plan, med_id, groesse = await _prepare(hass, call)
        await plan.async_add_stock(med_id, groesse, sc.verfall, sc.charge, call.data["anzahl_packungen"])
        if k := _serial_key(sc):
            await plan.async_book_serial(k)
        _done(hass)
        return {"medikament": _info(hass, plan, med_id)}

    async def packung_anfangen(call: ServiceCall):
        sc, plan, med_id, groesse = await _prepare(hass, call)
        await plan.async_new_pack(med_id, call.data.get("anbruchdatum"), 1, None, groesse)
        if k := _serial_key(sc):
            await plan.async_book_serial(k)
        _done(hass)
        return {"medikament": _info(hass, plan, med_id)}

    async def pzn_zuordnen(call: ServiceCall):
        sc = _parse(call.data["code"])
        if not _key(sc):
            raise ServiceValidationError("Im Code steckt keine PZN.")
        plan, med_id = resolve_entity(hass, call.data["entity_id"], call.data.get("plan"))
        await plan.async_learn_pzn(_key(sc), med_id, call.data.get("packungsgroesse"))
        _done(hass)
        return {"medikament": _info(hass, plan, med_id)}

    async def aus_vorrat_anbrechen(call: ServiceCall):
        plan, med_id = resolve_entity(hass, call.data["entity_id"])
        await plan.async_from_stock(med_id, call.data.get("anbruchdatum"))

    async def vorrat_entfernen(call: ServiceCall):
        plan, med_id = resolve_entity(hass, call.data["entity_id"])
        await plan.async_remove_last_stock(med_id)

    async def erinnerung_testen(call: ServiceCall):
        """Testnachricht (als TEST markiert) an das Ziel des Plans, unabhaengig vom Schalter Erinnerungen aktiv."""
        plans = _plans(hass, call.data["plan"])
        if not plans:
            raise ServiceValidationError(f"Plan {call.data['plan']} unbekannt.")
        await plans[0].async_send("[TEST] Testnachricht des Medikamentenplans, keine echte Erinnerung.", "Medikamentenplan TEST")

    async def medikament_hinzufuegen(call: ServiceCall):
        plan, today = _plan(hass, call.data["plan"]), dt_util.now().date()
        if not call.data.get("name") or "packungsgroesse" not in call.data:
            raise ServiceValidationError("name und packungsgroesse sind Pflicht.")
        pzn = call.data.get("pzn")
        if pzn:
            # PZN vor dem Anlegen pruefen, damit kein halbes Medikament entsteht
            try:
                pflege.normalize_pzn(pzn)
            except ValueError as e:
                raise ServiceValidationError(str(e)) from e
        med = pflege.build_new(_fields(call), today)
        _check(med)
        med_id = await plan.async_add(med)
        if pzn:
            await _learn(plan, med_id, pzn, med.get("packungsgroesse"))
        return {"med_id": med_id, "name": med["name"], "plan": plan.name}

    async def medikament_bearbeiten(call: ServiceCall):
        plan, med_id = resolve_entity(hass, call.data["entity_id"], call.data["plan"])
        if pzn := call.data.get("pzn"):
            try:
                pflege.normalize_pzn(pzn)
            except ValueError as e:
                raise ServiceValidationError(str(e)) from e
        med = pflege.build_edit(plan.meds[med_id], _fields(call), dt_util.now().date())
        _check(med)
        await plan.async_update(med_id, med)
        if pzn:
            await _learn(plan, med_id, pzn, med.get("packungsgroesse"))
        return {"med_id": med_id, "name": med["name"], "plan": plan.name}

    async def medikament_absetzen(call: ServiceCall):
        plan, med_id = resolve_entity(hass, call.data["entity_id"], call.data["plan"])
        await plan.async_update(med_id, calc.set_stopped(plan.meds[med_id], call.data["abgesetzt"], call.data.get("abgesetzt_am"), dt_util.now().date()))

    async def medikament_entfernen(call: ServiceCall):
        plan, med_id = resolve_entity(hass, call.data["entity_id"], call.data["plan"])
        if not call.data["bestaetigen"]:
            raise ServiceValidationError("Zum Entfernen bestaetigen=true setzen.")
        await plan.async_delete(med_id)

    reg = hass.services.async_register
    reg(DOMAIN, "scan_code", scan_code, vol.Schema({**CODE, **PLAN}), supports_response=SupportsResponse.ONLY)
    reg(DOMAIN, "scan_abbrechen", scan_abbrechen, vol.Schema({}))
    reg(DOMAIN, "vorrat_hinzufuegen", vorrat_hinzufuegen, vol.Schema({**CODE, **ENT, **PLAN, **GROESSE,
        vol.Optional("anzahl_packungen", default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=20))}),
        supports_response=SupportsResponse.OPTIONAL)
    reg(DOMAIN, "packung_anfangen", packung_anfangen, vol.Schema({**CODE, **ENT, **PLAN, **GROESSE, vol.Optional("anbruchdatum"): cv.date}),
        supports_response=SupportsResponse.OPTIONAL)
    reg(DOMAIN, "pzn_zuordnen", pzn_zuordnen, vol.Schema({**CODE, **PLAN, vol.Required("entity_id"): cv.entity_id, **GROESSE}),
        supports_response=SupportsResponse.OPTIONAL)
    reg(DOMAIN, "aus_vorrat_anbrechen", aus_vorrat_anbrechen,
        vol.Schema({vol.Required("entity_id"): cv.entity_id, vol.Optional("anbruchdatum"): cv.date}))
    reg(DOMAIN, "vorrat_entfernen", vorrat_entfernen, vol.Schema({vol.Required("entity_id"): cv.entity_id}))
    reg(DOMAIN, "erinnerung_testen", erinnerung_testen, vol.Schema({vol.Required("plan"): cv.string}))
    reg(DOMAIN, "medikament_hinzufuegen", medikament_hinzufuegen, vol.Schema({**PLAN_REQ, **PFLEGE}), supports_response=SupportsResponse.OPTIONAL)
    reg(DOMAIN, "medikament_bearbeiten", medikament_bearbeiten, vol.Schema({**PLAN_REQ, vol.Required("entity_id"): cv.entity_id, **PFLEGE}),
        supports_response=SupportsResponse.OPTIONAL)
    reg(DOMAIN, "medikament_absetzen", medikament_absetzen, vol.Schema({**PLAN_REQ, vol.Required("entity_id"): cv.entity_id,
        vol.Optional("abgesetzt", default=True): cv.boolean, vol.Optional("abgesetzt_am"): cv.date}))
    reg(DOMAIN, "medikament_entfernen", medikament_entfernen, vol.Schema({**PLAN_REQ, vol.Required("entity_id"): cv.entity_id,
        vol.Optional("bestaetigen", default=False): cv.boolean}))
