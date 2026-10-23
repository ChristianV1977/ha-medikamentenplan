import importlib.util, pathlib
from datetime import date

spec = importlib.util.spec_from_file_location(
    "calc", pathlib.Path(__file__).parent.parent / "custom_components/medikamentenplan/calc.py")
calc = importlib.util.module_from_spec(spec); spec.loader.exec_module(calc)

BASE = {"dosis": 1, "modus": "taeglich", "pro_tag": 1, "packungsgroesse": 20,
        "anbruch": "2026-10-23", "vorlauf_tage": 7}
T = date(2026, 10, 23)


def test_daily():
    c = calc.compute(BASE, T)
    assert c["reichweite_tage"] == 20 and c["verbleibende_tage"] == 20
    assert c["aufbrauchdatum"] == date(2026, 11, 12) and c["nachbestelldatum"] == date(2026, 11, 5)
    assert c["status"] == "ok"


def test_dose_times_per_day():
    assert calc.daily_use({**BASE, "dosis": 2, "pro_tag": 3}) == 6


def test_interval_and_prn():
    assert calc.daily_use({**BASE, "modus": "intervall", "intervall_tage": 7}) == 1 / 7
    assert abs(calc.daily_use({**BASE, "modus": "bedarf", "bedarf_pro_woche": 7, "dosis": 2}) - 2) < 1e-9
    assert calc.compute({**BASE, "modus": "bedarf", "bedarf_pro_woche": 0}, T)["status"] == "ok"


def test_status_transitions():
    assert calc.compute(BASE, date(2026, 11, 4))["status"] == "ok"
    assert calc.compute(BASE, date(2026, 11, 5))["status"] == "nachbestellen"
    c = calc.compute(BASE, date(2026, 11, 12))
    assert c["status"] == "aufgebraucht" and c["verbleibende_tage"] == 0
    assert calc.compute(BASE, date(2027, 1, 1))["verbleibende_tage"] == 0


def test_restbestand_and_new_pack():
    assert calc.compute({**BASE, "restbestand": 10}, T)["reichweite_tage"] == 10
    m = calc.new_pack({**BASE, "restbestand": 1}, date(2026, 11, 1), packs=2)
    assert m["anbruch"] == "2026-11-01" and m["restbestand"] == 40
    assert calc.compute(m, date(2026, 11, 1))["reichweite_tage"] == 40
