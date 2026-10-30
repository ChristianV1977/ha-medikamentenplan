"""Parser fuer Packungscodes (rein, ohne HA): securPharm-DataMatrix (IFA/PPN oder GS1/NTIN) und PZN-Strichcode."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

GS = "\x1d"
_FIXED = {"01": 14, "11": 6, "15": 6, "17": 6}  # GS1-AIs fester Laenge
_VAR = ("10", "21", "240", "712")  # variable Laenge, enden an GS bzw. am Ende
_IFA_DI = ("9N", "1T", "D", "S", "10D", "20D", "30D")  # IFA-Format 06: Data Identifier


@dataclass
class Scan:
    pzn: str | None = None
    gtin: str | None = None
    charge: str | None = None
    verfall: date | None = None
    seriennummer: str | None = None
    art: str = ""  # ppn | gs1 | pzn_strichcode
    fehler: str | None = None

    @property
    def key(self) -> str | None:
        """Zuordnungsschluessel: PZN, sonst (auslaendische) GTIN."""
        return self.pzn or self.gtin

    @property
    def serial_key(self) -> str | None:
        """Identitaet einer einzelnen Packung (Produkt + Seriennummer); None ohne Seriennummer."""
        return f"{self.key}|{self.seriennummer}" if self.seriennummer and self.key else None


def pzn8_ok(p: str) -> bool:
    """PZN-8: Pruefziffer = (Summe Ziffer_i * i, i=1..7) mod 11, Rest 10 ungueltig."""
    if not re.fullmatch(r"\d{8}", p):
        return False
    c = sum(int(d) * i for i, d in enumerate(p[:7], 1)) % 11
    return c != 10 and c == int(p[7])


def gtin_ok(g: str) -> bool:
    if not re.fullmatch(r"\d{14}", g):
        return False
    s = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(g[:13]))
    return (10 - s % 10) % 10 == int(g[13])


def _date(yymmdd: str) -> date | None:
    """YYMMDD; Tag 00 = Monatsende (GS1-Konvention); Jahr 20YY."""
    if not re.fullmatch(r"\d{6}", yymmdd):
        return None
    y, m, d = 2000 + int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:])
    try:
        if d == 0:
            return (date(y + (m == 12), m % 12 + 1, 1)) - timedelta(days=1)
        return date(y, m, d)
    except ValueError:
        return None


def _fields_gs1(s: str) -> dict[str, str]:
    out, i = {}, 0
    while i < len(s):
        if s[i] == GS:
            i += 1
            continue
        for ai in (s[i:i + 2], s[i:i + 3]):
            if ai in _FIXED:
                out[ai] = s[i + 2:i + 2 + _FIXED[ai]]
                i += 2 + _FIXED[ai]
                break
            if ai in _VAR:
                j = s.find(GS, i)
                j = len(s) if j < 0 else j
                out[ai] = s[i + len(ai):j]
                i = j
                break
        else:
            raise ValueError(f"unbekannter Bezeichner an Position {i}")
    return out


def _fields_ifa(s: str) -> dict[str, str]:
    out = {}
    for part in s.split(GS):
        for di in ("9N", "1T", "D", "S"):  # DI sind Praefixe der Gruppen
            if part.startswith(di):
                out[di] = part[len(di):]
                break
    return out


def parse(raw: str) -> Scan:
    s = (raw or "").strip().replace("<GS>", GS).replace("\x1e", "").replace("\x04", "")
    s = re.sub(r"^\]d2|^\]C1|^\]d1", "", s)  # Symbology-Identifier
    s = s.lstrip(GS)
    if not s:
        return Scan(fehler="leerer Code")
    # 1) einfacher PZN-Strichcode (Code 39): "-12345678" oder "-1234567"; reine 8 Ziffern nur bei gueltiger Pruefziffer
    m = re.fullmatch(r"-?(\d{7,8})", s)
    if m and (s.startswith("-") or pzn8_ok(m.group(1))):
        p = m.group(1)
        if len(p) == 7:  # alte PZN-7 = PZN-8 mit fuehrender 0
            p = "0" + p
        if pzn8_ok(p):
            return Scan(pzn=p, art="pzn_strichcode")
        return Scan(fehler="PZN-Pruefziffer ungueltig")
    try:
        if s.startswith("[)>"):  # IFA Format 06 (ISO/IEC 15434)
            f = _fields_ifa(s[3:].removeprefix("06"))
            art = "ppn"
            ppn = f.get("9N", "")
            pzn = None
            if re.fullmatch(r"11\d{8,10}", ppn):  # PRA-Code 11 + PZN-8 (+ 2 Pruefziffern mod 97)
                pzn = ppn[2:10]
            charge, verf, ser = f.get("1T"), _date(f.get("D", "")), f.get("S")
            rawd = f.get("D")
            gtin = None
        elif re.match(r"^(01|9N|10|17|21)", s):
            if s.startswith("9N"):  # PPN ohne Envelope (nur 9N...)
                f = _fields_ifa(s)
                ppn = f.get("9N", "")
                pzn = ppn[2:10] if re.fullmatch(r"11\d{8,10}", ppn) else None
                return _finish(Scan(pzn=pzn, charge=f.get("1T"), verfall=_date(f.get("D", "")), seriennummer=f.get("S"), art="ppn"), f.get("D"))
            f = _fields_gs1(s)
            gtin = f.get("01")
            pzn = None
            if gtin and gtin_ok(gtin) and gtin.startswith("04150"):  # NTIN: 0 + 4150 + PZN-8 + GS1-Pruefziffer
                pzn = gtin[5:13]
            charge, verf, ser = f.get("10"), _date(f.get("17", "")), f.get("21")
            rawd = f.get("17")
            art = "gs1"
        else:
            return Scan(fehler="Code nicht erkannt")
    except ValueError as e:
        return Scan(fehler=str(e))
    return _finish(Scan(pzn=pzn, gtin=gtin, charge=charge or None, verfall=verf, seriennummer=ser or None, art=art), rawd)


_SAFE = re.compile(r"[A-Za-z0-9!#%()*+,\-./:;=?_ ]{1,20}")  # GS1-Zeichen ohne < > " ' &, max. 20


def _finish(sc: Scan, raw_date: str | None = None) -> Scan:
    for v in (sc.charge, sc.seriennummer):
        if v is not None and not _SAFE.fullmatch(v):
            return Scan(fehler="Charge/Seriennummer enthaelt unzulaessige Zeichen")
    if raw_date and sc.verfall is None:
        return Scan(fehler="Verfallsdatum ungueltig")
    if sc.pzn and not pzn8_ok(sc.pzn):
        sc.fehler = "PZN-Pruefziffer ungueltig"
        sc.pzn = None
    elif not sc.pzn and not sc.gtin:
        sc.fehler = "keine PZN im Code"
    return sc
