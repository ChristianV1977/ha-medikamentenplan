"""Reine Berechnungsfunktionen (ohne HA-Laufzeit, per pytest testbar)."""
from __future__ import annotations

from datetime import date, timedelta

MODE_DAILY = "taeglich"
MODE_INTERVAL = "intervall"
MODE_PRN = "bedarf"

STATUS_OK = "ok"
STATUS_REORDER = "nachbestellen"
STATUS_EMPTY = "aufgebraucht"


def parse_date(value) -> date | None:
    if isinstance(value, date):
        return value
    if not value:
        return None
    return date.fromisoformat(str(value)[:10])


def daily_use(med: dict) -> float:
    """Verbrauch pro Tag in Einheiten (Dosis x Einnahmen/Tag, / Intervall, / Bedarf pro Woche)."""
    dose = float(med.get("dosis", 0) or 0)
    mode = med.get("modus", MODE_DAILY)
    if mode == MODE_INTERVAL:
        return dose / max(1, int(med.get("intervall_tage", 1) or 1))
    if mode == MODE_PRN:
        return dose * float(med.get("bedarf_pro_woche", 0) or 0) / 7
    return dose * float(med.get("pro_tag", 1) or 0)


def stock_at_start(med: dict) -> float:
    rest = med.get("restbestand")
    if rest in (None, ""):
        rest = med.get("packungsgroesse", 0)
    return float(rest or 0)


def compute(med: dict, today: date) -> dict:
    """Reichweite, Aufbrauch-/Nachbestelldatum, verbleibende Tage und Status."""
    use = daily_use(med)
    out = {
        "tagesverbrauch": round(use, 4),
        "reichweite_tage": None,
        "aufbrauchdatum": None,
        "nachbestelldatum": None,
        "verbleibende_tage": None,
        "status": STATUS_OK,
    }
    if use <= 0:
        return out
    start = parse_date(med.get("anbruch")) or today
    range_days = stock_at_start(med) / use
    runout = start + timedelta(days=int(range_days))  # ganze Tage, abgerundet
    reorder = runout - timedelta(days=int(med.get("vorlauf_tage", 7) or 0))
    out.update(
        reichweite_tage=round(range_days, 2),
        aufbrauchdatum=runout,
        nachbestelldatum=reorder,
        verbleibende_tage=max(0, (runout - today).days),
    )
    if today >= runout:
        out["status"] = STATUS_EMPTY
    elif today >= reorder:
        out["status"] = STATUS_REORDER
    return out


def new_pack(med: dict, start: date, packs: int = 1) -> dict:
    """Neue Packung angefangen: Anbruch = start, Bestand = Packungen x Packungsgroesse."""
    med = dict(med)
    med["anbruch"] = start.isoformat()
    med["restbestand"] = float(med.get("packungsgroesse", 0)) * max(1, int(packs))
    return med
