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


VERFALL_WARN_TAGE = 60


def pack_units(med: dict, pack: dict) -> float:
    return float(pack.get("groesse") or med.get("packungsgroesse") or 0)


def stock_units(med: dict) -> float:
    return sum(pack_units(med, p) for p in med.get("vorrat", []))


def earliest_expiry(med: dict) -> date | None:
    ds = [parse_date(p.get("verfall")) for p in med.get("vorrat", [])]
    ds = [d for d in ds if d]
    return min(ds) if ds else None


def compute(med: dict, today: date) -> dict:
    """Reichweite, Aufbrauch-/Nachbestelldatum, verbleibende Tage und Status.
    reichweite_tage/verbleibende_tage/aufbrauchdatum gelten fuer die angebrochene Packung (kompatibel);
    nachbestelldatum und status rechnen den Vorrat (ungeoeffnete Packungen) mit, *_inkl_vorrat getrennt."""
    use = daily_use(med)
    exp = earliest_expiry(med)
    out = {
        "tagesverbrauch": round(use, 4),
        "einnahmeschema": schema_text(med) if med.get("modus", MODE_DAILY) != MODE_PRN else "",
        "reichweite_tage": None,
        "aufbrauchdatum": None,
        "nachbestelldatum": None,
        "verbleibende_tage": None,
        "status": STATUS_OK,
        "vorrat_packungen": len(med.get("vorrat", [])),
        "vorrat_einheiten": round(stock_units(med), 2),
        "reichweite_inkl_vorrat_tage": None,
        "aufbrauchdatum_inkl_vorrat": None,
        "naechster_verfall": exp,
        "verfall_warnung": bool(exp and (exp - today).days <= VERFALL_WARN_TAGE),
    }
    if med.get("abgesetzt"):  # keine Reichweite/Ampel, kein Nachbestelldatum
        out.update(einnahmeschema="", status=STATUS_STOPPED)
        return out
    if use <= 0:
        return out
    start = parse_date(med.get("anbruch")) or today
    range_days = stock_at_start(med) / use
    runout = start + timedelta(days=int(range_days))  # ganze Tage, abgerundet
    total_days = range_days + stock_units(med) / use
    total_runout = start + timedelta(days=int(total_days))
    reorder = total_runout - timedelta(days=int(med.get("vorlauf_tage", 7) or 0))
    out.update(
        reichweite_tage=round(range_days, 2),
        aufbrauchdatum=runout,
        nachbestelldatum=reorder,
        verbleibende_tage=max(0, (runout - today).days),
        reichweite_inkl_vorrat_tage=max(0, (total_runout - today).days),
        aufbrauchdatum_inkl_vorrat=total_runout,
    )
    if today >= total_runout:
        out["status"] = STATUS_EMPTY
    elif today >= reorder:
        out["status"] = STATUS_REORDER
    return out


def add_stock(med: dict, groesse: float | None, verfall=None, charge=None, anzahl: int = 1) -> dict:
    """Ungeoeffnete Packung(en) auf Vorrat legen."""
    med = dict(med)
    pack = {k: v for k, v in (("groesse", groesse), ("verfall", verfall.isoformat() if hasattr(verfall, "isoformat") else verfall),
                              ("charge", charge)) if v}
    med["vorrat"] = [*med.get("vorrat", []), *[dict(pack) for _ in range(max(1, int(anzahl)))]]
    return med


def take_stock(med: dict) -> tuple[dict, dict]:
    """Eine Packung aus dem Vorrat nehmen: die mit dem fruehesten Verfall zuerst (ohne Verfall zuletzt)."""
    vor = list(med.get("vorrat", []))
    if not vor:
        raise ValueError("Kein Vorrat vorhanden.")
    i = min(range(len(vor)), key=lambda k: (parse_date(vor[k].get("verfall")) or date.max, k))
    pack = vor.pop(i)
    return {**med, "vorrat": vor}, pack


def remove_last_stock(med: dict) -> dict:
    if not med.get("vorrat"):
        raise ValueError("Kein Vorrat vorhanden.")
    return {**med, "vorrat": med["vorrat"][:-1]}


MAX_SERIALS = 5000


def migrate_store(data: dict | None) -> dict:
    """Store-Schema 2: Vorrat je Medikament, PZN-Zuordnung, gebuchte Seriennummern. Idempotent, verliert nichts."""
    data = dict(data or {})
    data["meds"] = {k: {**m, "vorrat": m.get("vorrat", [])} for k, m in (data.get("meds") or {}).items()}
    data.setdefault("pzn", {})
    data.setdefault("serials", {})
    data["schema"] = 2
    return data


def remember_serial(serials: dict, key: str, today: date) -> dict:
    serials = {**serials, key: today.isoformat()}
    while len(serials) > MAX_SERIALS:
        serials.pop(next(iter(serials)))
    return serials


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


def set_field(med: dict, key: str, value) -> dict:
    """Einzelnes Feld setzen; None entfernt es (Hersteller/Packungsgroesse-Entities)."""
    med = dict(med)
    if value is None:
        med.pop(key, None)
    else:
        med[key] = value
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
