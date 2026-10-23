"""Reine Berechnungsfunktionen (ohne HA-Laufzeit, per pytest testbar)."""
from __future__ import annotations

from datetime import date, timedelta

MODE_DAILY = "taeglich"
MODE_INTERVAL = "intervall"
MODE_PRN = "bedarf"

STATUS_OK = "ok"
STATUS_REORDER = "nachbestellen"
STATUS_EMPTY = "aufgebraucht"
STATUS_STOPPED = "abgesetzt"


def parse_date(value) -> date | None:
    if isinstance(value, date):
        return value
    if not value:
        return None
    return date.fromisoformat(str(value)[:10])


SCHEMA_KEYS = ("morgens", "mittags", "abends", "nachts")


def schema_sum(med: dict) -> float:
    return sum(float(med.get(k, 0) or 0) for k in SCHEMA_KEYS)


def fmt_num(x) -> str:
    """Deutsch formatiert: 0,5 statt 0.5, ganze Zahlen ohne Nachkomma."""
    x = round(float(x), 2)
    return str(int(x)) if x == int(x) else str(x).replace(".", ",")


def schema_text(med: dict) -> str:
    """Lesbar, z. B. 'morgens 0,5 · abends 1'; leer ohne Schema."""
    return " · ".join(f"{k} {fmt_num(med[k])}" for k in SCHEMA_KEYS if float(med.get(k, 0) or 0) > 0)


def daily_use(med: dict) -> float:
    """Verbrauch pro Tag in Einheiten. Mit Tageszeit-Schema (Summe > 0) gilt dessen Summe statt Dosis x pro_tag;
    bei Intervall ist das Schema die Menge am Einnahmetag; bei Bedarf wird es ignoriert."""
    dose = float(med.get("dosis", 0) or 0)
    mode = med.get("modus", MODE_DAILY)
    sch = schema_sum(med)
    if sch > 0 and mode == MODE_DAILY:
        return sch
    if sch > 0 and mode == MODE_INTERVAL:
        return sch / max(1, int(med.get("intervall_tage", 1) or 1))
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
        "einnahmeschema": schema_text(med) if med.get("modus", MODE_DAILY) != MODE_PRN else "",
        "reichweite_tage": None,
        "aufbrauchdatum": None,
        "nachbestelldatum": None,
        "verbleibende_tage": None,
        "status": STATUS_OK,
    }
    if med.get("abgesetzt"):  # keine Reichweite/Ampel, kein Nachbestelldatum
        out.update(einnahmeschema="", status=STATUS_STOPPED)
        return out
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


def new_pack(med: dict, start: date, packs: int = 1, hersteller: str | None = None,
             packungsgroesse: float | None = None) -> dict:
    """Neue Packung angefangen: Anbruch = start, Bestand = Packungen x Packungsgroesse.
    hersteller/packungsgroesse None = unveraendert; hersteller "" = Angabe entfernen."""
    med = dict(med)
    if hersteller is not None:
        if hersteller.strip():
            med["hersteller"] = hersteller.strip()
        else:
            med.pop("hersteller", None)
    if packungsgroesse is not None:
        med["packungsgroesse"] = float(packungsgroesse)
    med["anbruch"] = start.isoformat()
    med["restbestand"] = float(med.get("packungsgroesse", 0)) * max(1, int(packs))
    return med


def set_stopped(med: dict, stopped: bool, since: date | None = None, today: date | None = None) -> dict:
    """Absetzen (Datum optional, Standard heute) bzw. Reaktivieren (Felder entfernen)."""
    med = dict(med)
    if stopped:
        med["abgesetzt"] = True
        med["abgesetzt_am"] = (since or today or date.today()).isoformat()
    else:
        med.pop("abgesetzt", None)
        med.pop("abgesetzt_am", None)
    return med
