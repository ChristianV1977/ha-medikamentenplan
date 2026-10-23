from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.helpers import selector as sel
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from . import calc
from .catalog import fmt, hersteller, startliste
from .const import CATALOG_FIELDS, DOMAIN, FORMS, MODES


def _select(options, key):
    return sel.SelectSelector(sel.SelectSelectorConfig(
        options=options, translation_key=key, mode=sel.SelectSelectorMode.DROPDOWN))


def _num(**kw):
    return sel.NumberSelector(sel.NumberSelectorConfig(mode=sel.NumberSelectorMode.BOX, step="any", **kw))


def _combo(options):
    return sel.SelectSelector(sel.SelectSelectorConfig(
        options=list(options), mode=sel.SelectSelectorMode.DROPDOWN, custom_value=True))


def med_schema(hersteller_liste=()) -> vol.Schema:
    return vol.Schema({
        vol.Required("name"): str,
        vol.Optional("hersteller"): _combo(hersteller_liste),
        vol.Optional("wirkstoff"): str,
        vol.Required("darreichungsform", default="tablette"): _select(FORMS, "darreichungsform"),
        vol.Required("dosis", default=1): _num(min=0.01),
        vol.Required("einheit", default="Stück"): str,
        vol.Required("modus", default="taeglich"): _select(MODES, "modus"),
        vol.Optional("morgens"): _num(min=0),
        vol.Optional("mittags"): _num(min=0),
        vol.Optional("abends"): _num(min=0),
        vol.Optional("nachts"): _num(min=0),
        vol.Optional("pro_tag", default=1): _num(min=0),
        vol.Optional("intervall_tage", default=7): _num(min=1),
        vol.Optional("bedarf_pro_woche", default=0): _num(min=0),
        vol.Required("packungsgroesse"): _num(min=0.01),
        vol.Optional("verordnet"): sel.DateSelector(),
        vol.Required("anbruch"): sel.DateSelector(),
        vol.Optional("restbestand"): _num(min=0),
        vol.Optional("zweck"): str,
        vol.Required("rezeptpflichtig", default=False): bool,
        vol.Required("vorlauf_tage", default=7): _num(min=0),
        vol.Optional("notiz"): sel.TextSelector(sel.TextSelectorConfig(multiline=True)),
        vol.Optional("abgesetzt", default=False): bool,
        vol.Optional("abgesetzt_am"): sel.DateSelector(),
    })


def _clean(inp: dict) -> dict:
    """Leere Optionalfelder entfernen, Zahlen normalisieren."""
    med = {k: v for k, v in inp.items() if v not in (None, "")}
    for k in ("morgens", "mittags", "abends", "nachts"):
        if not float(med.get(k, 0) or 0):
            med.pop(k, None)  # 0/leer = nicht gesetzt (Migration: alte Eintraege ohne Schema bleiben gueltig)
    if med.get("abgesetzt"):
        med = calc.set_stopped(med, True, calc.parse_date(med.get("abgesetzt_am")), dt_util.now().date())
    else:
        med = calc.set_stopped(med, False)
    for k in ("intervall_tage", "vorlauf_tage"):
        if k in med:
            med[k] = int(med[k])
    return med


class MedConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            name = user_input["name"].strip()
            await self.async_set_unique_id(slugify(name))
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=name, data={})
        return self.async_show_form(step_id="user", data_schema=vol.Schema({vol.Required("name"): str}))

    @staticmethod
    def async_get_options_flow(config_entry):
        return MedOptionsFlow()


class MedOptionsFlow(OptionsFlow):
    def __init__(self) -> None:
        self._med_id: str | None = None
        self._prefill: dict = {}
        self._wirkstoff: str | None = None
        self._hersteller: list[str] = []

    @property
    def plan(self):
        return self.hass.data[DOMAIN][self.config_entry.entry_id]

    async def async_step_init(self, user_input=None):
        self._hersteller = await self.hass.async_add_executor_job(hersteller)
        await self.hass.async_add_executor_job(startliste)
        return self.async_show_menu(step_id="init", menu_options=["add", "startliste", "catalog", "neue_packung", "edit", "absetzen", "delete"])

    def _med_options(self, plans=None) -> dict[str, str]:
        return {mid: m["name"] + (" (abgesetzt)" if m.get("abgesetzt") else "") for mid, m in self.plan.meds.items()}

    async def _form(self, step, errors=None):
        schema = self.add_suggested_values_to_schema(med_schema(self._hersteller), self._prefill)
        return self.async_show_form(step_id=step, data_schema=schema, errors=errors)

    def _validate(self, med):
        mode = med["modus"]
        if mode == "taeglich" and not med.get("pro_tag") and not calc.schema_sum(med):
            return {"pro_tag": "pflicht"}
        if mode == "bedarf" and not med.get("bedarf_pro_woche"):
            return {"bedarf_pro_woche": "pflicht"}
        return {}

    # --- hinzufuegen (optional vorbefuellt aus Katalog) ---
    async def async_step_add(self, user_input=None):
        if user_input is not None:
            med = _clean(user_input)
            if errors := self._validate(med):
                self._prefill = user_input
                return await self._form("add", errors)
            await self.plan.async_add(med)
            return self.async_create_entry(data={})
        self._prefill = {"anbruch": dt_util.now().date().isoformat(), **self._prefill}
        return await self._form("add")

    # --- Startliste: Wirkstoff -> Staerke/Packung/Hersteller -> normales Formular ---
    async def async_step_startliste(self, user_input=None):
        if user_input is not None:
            self._wirkstoff = user_input["wirkstoff"]
            return await self.async_step_startliste_details()
        return self.async_show_form(step_id="startliste", data_schema=vol.Schema({
            vol.Required("wirkstoff"): sel.SelectSelector(sel.SelectSelectorConfig(
                options=sorted(startliste(), key=str.lower), mode=sel.SelectSelectorMode.DROPDOWN))}))

    async def async_step_startliste_details(self, user_input=None):
        e = startliste()[self._wirkstoff]
        errors = {}
        if user_input is not None:
            try:
                pack = float(str(user_input["packungsgroesse"]).replace(",", "."))
                if pack <= 0:
                    raise ValueError
            except ValueError:
                errors["packungsgroesse"] = "pflicht"
            else:
                staerke = user_input["staerke"].strip()
                name = f"{self._wirkstoff} {staerke}".strip()
                self._prefill = {
                    "name": name, "wirkstoff": name, "darreichungsform": e["darreichungsform"],
                    "einheit": e["einheit"], "packungsgroesse": pack,
                    "rezeptpflichtig": e["rezeptpflichtig"], "zweck": e["zweck_vorschlag"],
                    "hersteller": user_input.get("hersteller", ""),
                }
                return await self.async_step_add()
        return self.async_show_form(step_id="startliste_details", errors=errors,
            description_placeholders={"wirkstoff": self._wirkstoff, "zweck": e["zweck_vorschlag"]},
            data_schema=vol.Schema({
                vol.Required("staerke", default=e["staerken"][0]): _combo(e["staerken"]),
                vol.Required("packungsgroesse", default=fmt(e["packungsgroessen"][0])):
                    _combo([fmt(p) for p in e["packungsgroessen"]]),
                vol.Optional("hersteller"): _combo(self._hersteller),
            }))

    async def async_step_catalog(self, user_input=None):
        # Hauskatalog: alle Medikamente aller Plaene als Vorlage (nur Stammdaten, keine Daten/Bestand)
        catalog = {}
        for plan in self.hass.data[DOMAIN].values():
            for mid, m in plan.meds.items():
                catalog[f"{plan.entry.entry_id}|{mid}"] = f"{m['name']} ({plan.name})"
        if user_input is not None:
            eid, mid = user_input["vorlage"].split("|")
            src = self.hass.data[DOMAIN][eid].meds[mid]
            self._prefill = {k: src[k] for k in CATALOG_FIELDS if k in src}
            return await self.async_step_add()
        if not catalog:
            return self.async_abort(reason="katalog_leer")
        return self.async_show_form(step_id="catalog", data_schema=vol.Schema({
            vol.Required("vorlage"): sel.SelectSelector(sel.SelectSelectorConfig(
                options=[sel.SelectOptionDict(value=k, label=v) for k, v in catalog.items()]))}))

    # --- bearbeiten ---
    async def async_step_edit(self, user_input=None):
        if user_input is not None:
            self._med_id = user_input["medikament"]
            self._prefill = dict(self.plan.meds[self._med_id])
            return await self._form("edit_form")
        return self._pick("edit")

    async def async_step_edit_form(self, user_input=None):
        med = _clean(user_input)
        if errors := self._validate(med):
            self._prefill = user_input
            return await self._form("edit_form", errors)
        await self.plan.async_update(self._med_id, med)
        return self.async_create_entry(data={})

    # --- neue Packung mit Rueckfrage (Hersteller/Groesse vorbelegt) ---
    async def async_step_neue_packung(self, user_input=None):
        if user_input is not None:
            self._med_id = user_input["medikament"]
            return await self.async_step_neue_packung_form()
        return self._pick("neue_packung", active_only=True)

    async def async_step_neue_packung_form(self, user_input=None):
        med = self.plan.meds[self._med_id]
        if user_input is not None:
            await self.plan.async_new_pack(
                self._med_id, calc.parse_date(user_input["anbruch"]), int(user_input["anzahl_packungen"]),
                user_input.get("hersteller", ""), float(user_input["packungsgroesse"]))
            return self.async_create_entry(data={})
        schema = vol.Schema({
            vol.Optional("hersteller"): _combo(self._hersteller),
            vol.Required("packungsgroesse"): _num(min=0.01),
            vol.Required("anzahl_packungen", default=1): _num(min=1, max=20),
            vol.Required("anbruch"): sel.DateSelector(),
        })
        sug = {"hersteller": med.get("hersteller", ""), "packungsgroesse": med.get("packungsgroesse"),
               "anbruch": dt_util.now().date().isoformat()}
        return self.async_show_form(step_id="neue_packung_form",
            data_schema=self.add_suggested_values_to_schema(schema, sug),
            description_placeholders={"name": med["name"]})

    # --- absetzen / reaktivieren ---
    async def async_step_absetzen(self, user_input=None):
        if user_input is not None:
            self._med_id = user_input["medikament"]
            return await self.async_step_absetzen_form()
        return self._pick("absetzen")

    async def async_step_absetzen_form(self, user_input=None):
        med = self.plan.meds[self._med_id]
        if user_input is not None:
            since = calc.parse_date(user_input.get("abgesetzt_am"))
            await self.plan.async_update(self._med_id, calc.set_stopped(
                med, user_input["abgesetzt"], since, dt_util.now().date()))
            return self.async_create_entry(data={})
        schema = vol.Schema({vol.Required("abgesetzt"): bool, vol.Optional("abgesetzt_am"): sel.DateSelector()})
        sug = {"abgesetzt": bool(med.get("abgesetzt")), "abgesetzt_am": med.get("abgesetzt_am") or dt_util.now().date().isoformat()}
        return self.async_show_form(step_id="absetzen_form",
            data_schema=self.add_suggested_values_to_schema(schema, sug),
            description_placeholders={"name": med["name"]})

    # --- loeschen ---
    async def async_step_delete(self, user_input=None):
        if user_input is not None:
            if user_input["bestaetigen"]:
                await self.plan.async_delete(user_input["medikament"])
            return self.async_create_entry(data={})
        return self._pick("delete", confirm=True)

    def _pick(self, step, confirm=False, active_only=False):
        opts = {k: v for k, v in self._med_options().items() if not (active_only and self.plan.meds[k].get("abgesetzt"))}
        if not opts:
            return self.async_abort(reason="keine_medikamente")
        schema = {vol.Required("medikament"): sel.SelectSelector(sel.SelectSelectorConfig(
            options=[sel.SelectOptionDict(value=k, label=v) for k, v in opts.items()]))}
        if confirm:
            schema[vol.Required("bestaetigen", default=False)] = bool
        return self.async_show_form(step_id=step, data_schema=vol.Schema(schema))
