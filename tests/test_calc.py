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


def test_schema():
    s = {**BASE, "morgens": 1, "abends": 1}
    assert calc.daily_use(s) == 2 and calc.schema_text(s) == "morgens 1 · abends 1"
    h = {**BASE, "morgens": 0.5}
    assert calc.daily_use(h) == 0.5 and calc.schema_text(h) == "morgens 0,5"
    assert calc.compute(h, T)["reichweite_tage"] == 40
    assert calc.daily_use({**BASE, "dosis": 3, "pro_tag": 2, "morgens": 1}) == 1  # Schema ersetzt Dosis x pro_tag
    assert calc.daily_use({**BASE, "modus": "intervall", "intervall_tage": 2, "morgens": 1, "abends": 1}) == 1
    assert calc.daily_use({**BASE, "modus": "bedarf", "bedarf_pro_woche": 7, "morgens": 5}) == 1


def test_old_entries_without_schema():
    assert calc.daily_use({**BASE, "dosis": 2, "pro_tag": 3}) == 6 and calc.schema_text(BASE) == ""
    assert calc.fmt_num(1.0) == "1" and calc.fmt_num(0.5) == "0,5"


def test_new_pack_changes():
    m = calc.new_pack({**BASE, "hersteller": "A"}, T, packs=2, hersteller="B", packungsgroesse=30)
    assert m["hersteller"] == "B" and m["packungsgroesse"] == 30 and m["restbestand"] == 60
    assert calc.new_pack({**BASE, "hersteller": "A"}, T, hersteller="")["anbruch"] == "2026-10-23"
    assert "hersteller" not in calc.new_pack({**BASE, "hersteller": "A"}, T, hersteller="  ")
    u = calc.new_pack({**BASE, "hersteller": "A"}, T)  # None = unveraendert
    assert u["hersteller"] == "A" and u["packungsgroesse"] == 20 and u["restbestand"] == 20


def test_stopped():
    s = calc.set_stopped({**BASE, "restbestand": 5}, True, today=T)
    assert s["abgesetzt"] is True and s["abgesetzt_am"] == "2026-10-23"
    c = calc.compute(s, T)
    assert c["status"] == "abgesetzt" and c["verbleibende_tage"] is None and c["nachbestelldatum"] is None
    assert calc.set_stopped(s, True, date(2026, 10, 1))["abgesetzt_am"] == "2026-10-01"
    r = calc.set_stopped(s, False)
    assert "abgesetzt" not in r and "abgesetzt_am" not in r
    assert calc.compute(r, T)["status"] == "nachbestellen"  # 5 Stueck Rest, Ampel wieder aktiv
