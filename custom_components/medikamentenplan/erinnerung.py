"""Erinnerungen je Plan: reine Logik ohne HA-Importe (testbar). Nachrichten enthalten bewusst keine Medikamentennamen (Sperrbildschirm)."""
from __future__ import annotations

from datetime import date, datetime

from . import calc

SLOTS = ("morgens", "mittags", "abends", "nachts")
LABEL = {"morgens": "morgens", "mittags": "mittags", "abends": "abends", "nachts": "nachts"}
TITLE = "Medikamentenplan"


def default_settings() -> dict:
    return {"aktiv": False,  # Standard AUS: niemand bekommt ungefragt Nachrichten
            "zeiten": {"morgens": "08:00", "mittags": "12:00", "abends": "18:00", "nachts": "22:00"},
            "nachkauf_zeit": "09:00", "schwelle_tage": 7, "ziel": None, "gesendet": {}}


def merge_settings(saved: dict | None) -> dict:
    s = default_settings()
    saved = saved or {}
    for k in ("aktiv", "nachkauf_zeit", "schwelle_tage", "ziel", "gesendet"):
        if k in saved:
            s[k] = saved[k]
    s["zeiten"].update(saved.get("zeiten") or {})
    return s


def _aktiv(m: dict) -> bool:
    return not m.get("abgesetzt") and m.get("modus") != "bedarf"


def slot_count(meds: dict, slot: str) -> int:
    # shortcut: nur Modus "taeglich"; Intervall-Medikamente loesen keine Zeit-Erinnerung aus, bei Bedarf nachziehen
    return sum(1 for m in meds.values() if _aktiv(m) and m.get("modus", "taeglich") == "taeglich" and float(m.get(slot) or 0) > 0)


def refill_count(meds: dict, today: date, schwelle: int) -> int:
    n = 0
    for m in meds.values():
        if not _aktiv(m):
            continue
        r = calc.compute(m, today).get("reichweite_inkl_vorrat_tage")
        if r is not None and r <= schwelle:
            n += 1
    return n


def due(settings: dict, meds: dict, now: datetime) -> list[dict]:
    """Faellige Erinnerungen fuer genau diese Minute; jede Art hoechstens einmal pro Tag."""
    if not settings.get("aktiv") or not settings.get("ziel"):
        return []
    hhmm, today = now.strftime("%H:%M"), now.date().isoformat()
    sent, out = settings.get("gesendet", {}), []
    for slot in SLOTS:
        if settings["zeiten"].get(slot) == hhmm and sent.get(slot) != today and (n := slot_count(meds, slot)):
            out.append({"key": slot, "title": TITLE,
                        "message": f"Einnahme {LABEL[slot]}: {n} Medikament{'e' if n != 1 else ''} fällig."})
    if settings.get("nachkauf_zeit") == hhmm and sent.get("nachkauf") != today:
        if n := refill_count(meds, now.date(), int(settings.get("schwelle_tage", 7))):
            out.append({"key": "nachkauf", "title": TITLE,
                        "message": f"Nachkaufen: {n} Medikament{'e' if n != 1 else ''} reichen höchstens noch {int(settings['schwelle_tage'])} Tage."})
    return out
