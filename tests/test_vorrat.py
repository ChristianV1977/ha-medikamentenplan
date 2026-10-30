import importlib.util, pathlib
from datetime import date

spec = importlib.util.spec_from_file_location(
    "calc", pathlib.Path(__file__).parent.parent / "custom_components/medikamentenplan/calc.py")
calc = importlib.util.module_from_spec(spec); spec.loader.exec_module(calc)

BASE = {"dosis": 1, "modus": "taeglich", "pro_tag": 1, "packungsgroesse": 20, "anbruch": "2026-10-23", "vorlauf_tage": 7}
T = date(2026, 10, 23)


def test_without_stock_unchanged():
    c = calc.compute(BASE, T)
    assert c["verbleibende_tage"] == 20 and c["nachbestelldatum"] == date(2026, 11, 5)
    assert c["vorrat_packungen"] == 0 and c["reichweite_inkl_vorrat_tage"] == 20 and c["naechster_verfall"] is None


def test_stock_extends_reorder_and_range():
    med = calc.add_stock(BASE, 20, date(2027, 6, 30), "C1", anzahl=2)
    c = calc.compute(med, T)
    assert c["verbleibende_tage"] == 20 and c["aufbrauchdatum"] == date(2026, 11, 12)  # Entity-Werte kompatibel
    assert c["reichweite_inkl_vorrat_tage"] == 60 and c["vorrat_packungen"] == 2 and c["vorrat_einheiten"] == 40
    assert c["nachbestelldatum"] == date(2026, 12, 15)  # 23.10. + 60 Tage = 22.12., minus 7 Vorlauf
    assert calc.compute(med, date(2026, 11, 20))["status"] == "ok"  # Packung leer, Vorrat da
    assert calc.compute(med, date(2026, 12, 15))["status"] == "nachbestellen"
    assert calc.compute(med, date(2026, 12, 22))["status"] == "aufgebraucht"


def test_default_groesse_from_med():
    med = calc.add_stock(BASE, None)
    assert calc.compute(med, T)["vorrat_einheiten"] == 20


def test_take_stock_earliest_expiry_first():
    med = calc.add_stock(calc.add_stock(BASE, 10, date(2027, 5, 1)), 20, date(2026, 12, 1))
    med = calc.add_stock(med, 30)  # ohne Verfall zuletzt
    med, p = calc.take_stock(med)
    assert p["groesse"] == 20 and len(med["vorrat"]) == 2
    med, p = calc.take_stock(med)
    assert p["groesse"] == 10
    med, p = calc.take_stock(med)
    assert p["groesse"] == 30
    try:
        calc.take_stock(med); assert False
    except ValueError:
        pass


def test_expiry_warning():
    soon = calc.compute(calc.add_stock(BASE, 20, date(2026, 12, 1)), T)  # 39 Tage <= 60
    assert soon["verfall_warnung"] is True and soon["naechster_verfall"] == date(2026, 12, 1)
    assert calc.compute(calc.add_stock(BASE, 20, date(2027, 6, 30)), T)["verfall_warnung"] is False


def test_stopped_med_keeps_stock_info_no_status():
    med = calc.set_stopped(calc.add_stock(BASE, 20), True, T)
    c = calc.compute(med, T)
    assert c["status"] == "abgesetzt" and c["vorrat_packungen"] == 1


def test_remove_last():
    med = calc.add_stock(calc.add_stock(BASE, 10, "2027-01-01"), 20, "2027-02-01")
    assert calc.remove_last_stock(med)["vorrat"][-1]["groesse"] == 10


def test_migration_idempotent_lossless():
    old = {"meds": {"a": {"name": "X", "packungsgroesse": 10, "restbestand": 3}, "b": {"name": "Y"}}}
    new = calc.migrate_store(old)
    assert new["schema"] == 2 and new["pzn"] == {} and new["serials"] == {}
    assert new["meds"]["a"] == {"name": "X", "packungsgroesse": 10, "restbestand": 3, "vorrat": []}
    assert calc.migrate_store(new) == new
    assert calc.migrate_store(None) == {"meds": {}, "pzn": {}, "serials": {}, "schema": 2}
    assert "vorrat" not in old["meds"]["a"]  # Eingabe unveraendert


def test_serial_cap():
    s = {}
    for i in range(calc.MAX_SERIALS + 5):
        s = calc.remember_serial(s, f"k|{i}", T)
    assert len(s) == calc.MAX_SERIALS and "k|0" not in s and f"k|{calc.MAX_SERIALS + 4}" in s
