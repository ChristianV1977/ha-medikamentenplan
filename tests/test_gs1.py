import importlib.util, pathlib, sys
from datetime import date

P = pathlib.Path(__file__).parent.parent / "custom_components/medikamentenplan"


def load(name):
    spec = importlib.util.spec_from_file_location(name, P / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


gs1 = load("gs1")
GS = "\x1d"
# PZN 03752864: Pruefziffer 4 (Gewichte 1..7 mod 11); NTIN 04150037528643 (GS1-Pruefziffer 3)
GS1_CODE = GS + "01041500375286431727123110CH12345" + GS + "21ABC987654321"
PPN_CODE = "[)>\x1e06" + GS + "9N110375286401" + GS + "1TCH12345" + GS + "D271231" + GS + "S1234567890"


def test_pzn_check():
    assert gs1.pzn8_ok("03752864") and gs1.pzn8_ok("12345678")
    assert not gs1.pzn8_ok("03752865") and not gs1.pzn8_ok("0375286")


def test_gs1_ntin():
    s = gs1.parse(GS1_CODE)
    assert (s.pzn, s.charge, s.verfall, s.seriennummer, s.art) == ("03752864", "CH12345", date(2027, 12, 31), "ABC987654321", "gs1")
    assert s.fehler is None and s.gtin == "04150037528643"


def test_gs1_without_leading_gs_and_symbology_id():
    assert gs1.parse(GS1_CODE.lstrip(GS)).pzn == "03752864"
    assert gs1.parse("]d2" + GS1_CODE.lstrip(GS)).charge == "CH12345"


def test_ppn_ifa():
    s = gs1.parse(PPN_CODE)
    assert (s.pzn, s.charge, s.verfall, s.seriennummer, s.art) == ("03752864", "CH12345", date(2027, 12, 31), "1234567890", "ppn")


def test_expiry_day_zero_is_month_end():
    assert gs1.parse(GS1_CODE.replace("271231", "280200")).verfall == date(2028, 2, 29)


def test_code39_pzn():
    assert gs1.parse("-03752864").pzn == "03752864"
    assert gs1.parse("-3752864").pzn == "03752864"  # alte PZN-7
    assert gs1.parse("-03752865").fehler


def test_invalid():
    assert gs1.parse("").fehler and gs1.parse("hallo welt").fehler
    assert gs1.parse(GS1_CODE.replace("04150037528643", "04150037528644")).pzn is None  # GS1-Pruefziffer falsch


def test_foreign_gtin_keeps_key():
    s = gs1.parse("01" + "04012345678901"[:13] + "1" + "17271231")  # kein 4150-Praefix
    assert s.pzn is None


def test_duplicate_serial_detection():
    calc = load("calc")
    a, b = gs1.parse(GS1_CODE), gs1.parse(GS1_CODE.replace("ABC987654321", "XYZ"))
    serials = calc.remember_serial({}, a.serial_key, date(2026, 10, 30))
    assert a.serial_key in serials and b.serial_key not in serials
    assert gs1.parse(GS1_CODE).serial_key == a.serial_key  # derselbe Scan = doppelt
    assert gs1.parse("-03752864").serial_key is None  # Strichcode hat keine Seriennummer
