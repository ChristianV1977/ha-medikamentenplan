"""Pflege der Medikamente ohne Options-Flow (Services fuer Nutzer ohne Admin): reine Logik ohne HA-Importe, gleiche Regeln wie der Options-Flow."""
from __future__ import annotations

from datetime import date

from . import calc, gs1

SLOTS = ("morgens", "mittags", "abends", "nachts")


def clean(inp: dict, today: date) -> dict:
    """Leere Optionalfelder entfernen, Zahlen normalisieren, Absetzen anwenden (frueher config_flow._clean)."""
    med = {k: v for k, v in inp.items() if v not in (None, "")}
    for k in SLOTS:
        if not float(med.get(k, 0) or 0):
            med.pop(k, None)  # 0/leer = nicht gesetzt
    if med.get("abgesetzt"):
        med = calc.set_stopped(med, True, calc.parse_date(med.get("abgesetzt_am")), today)
    else:
        med = calc.set_stopped(med, False)
    for k in ("intervall_tage", "vorlauf_tage"):
        if k in med:
            med[k] = int(med[k])
    return med


def validate(med: dict) -> dict:
    """Fehlerschluessel wie im Options-Flow (frueher config_flow._validate)."""
    mode = med.get("modus", "taeglich")
    if mode == "taeglich" and not med.get("pro_tag") and not calc.schema_sum(med):
        return {"pro_tag": "pflicht"}
    if mode == "bedarf" and not med.get("bedarf_pro_woche"):
        return {"bedarf_pro_woche": "pflicht"}
    return {}


def normalize_pzn(pzn: str) -> str:
    p = str(pzn).strip().zfill(8)
    if not gs1.pzn8_ok(p):
        raise ValueError("PZN ungueltig (7 bis 8 Ziffern mit korrekter Pruefziffer).")
    return p


def build_new(data: dict, today: date) -> dict:
    """Neues Medikament aus Service-Daten; Standardwerte wie im Options-Flow-Formular."""
    base = {"darreichungsform": "tablette", "dosis": 1, "einheit": "Stück", "modus": "taeglich", "pro_tag": 1,
            "intervall_tage": 7, "bedarf_pro_woche": 0, "rezeptpflichtig": False, "vorlauf_tage": 7,
            "anbruch": today.isoformat()}
    return clean({**base, **{k: v for k, v in data.items() if k not in ("plan", "pzn")}}, today)


def build_edit(old: dict, data: dict, today: date) -> dict:
    """Nur die gelieferten Felder aendern; Leerstring loescht ein optionales Feld. Vorrat bleibt erhalten."""
    changes = {k: v for k, v in data.items() if k not in ("plan", "entity_id", "pzn")}
    med = clean({**old, **changes}, today)
    med["vorrat"] = old.get("vorrat", [])
    return med
