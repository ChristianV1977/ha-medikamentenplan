import importlib, pathlib, sys, types
from datetime import date

import pytest

pkg = types.ModuleType("mp3"); pkg.__path__ = [str(pathlib.Path(__file__).parent.parent / "custom_components/medikamentenplan")]
sys.modules["mp3"] = pkg
pf = importlib.import_module("mp3.pflege")
T = date(2026, 11, 3)


def test_build_new_defaults_and_validation():
    med = pf.build_new({"plan": "X", "name": "A", "packungsgroesse": 20.0, "morgens": 1.0, "abends": 0.0, "notiz": ""}, T)
    assert med["name"] == "A" and med["anbruch"] == "2026-11-03" and med["modus"] == "taeglich" and med["vorlauf_tage"] == 7
    assert "abends" not in med and "notiz" not in med and "plan" not in med and pf.validate(med) == {}


def test_validate_modes():
    assert pf.validate({"modus": "bedarf"}) == {"bedarf_pro_woche": "pflicht"}
    assert pf.validate({"modus": "bedarf", "bedarf_pro_woche": 2}) == {}
    assert pf.validate({"modus": "taeglich", "pro_tag": 0}) == {"pro_tag": "pflicht"}
    assert pf.validate({"modus": "taeglich", "morgens": 1}) == {}


def test_edit_changes_only_given_fields_keeps_stock():
    old = {"name": "A", "modus": "taeglich", "morgens": 1, "abends": 1, "packungsgroesse": 20, "anbruch": "2026-10-01", "vorrat": [{"groesse": 20}], "notiz": "x", "intervall_tage": 7}
    med = pf.build_edit(old, {"plan": "X", "entity_id": "sensor.a", "morgens": 2.0, "notiz": "", "abends": 0.0}, T)
    assert med["morgens"] == 2 and "abends" not in med and "notiz" not in med  # leer loescht
    assert med["packungsgroesse"] == 20 and med["anbruch"] == "2026-10-01" and med["vorrat"] == [{"groesse": 20}] and "entity_id" not in med


def test_pzn_check():
    ok = next(p for p in (f"{i:07d}" + str(sum(int(d) * k for k, d in enumerate(f"{i:07d}", 1)) % 11) for i in range(1000, 1200)) if len(p) == 8)
    assert pf.normalize_pzn(ok) == ok
    with pytest.raises(ValueError):
        pf.normalize_pzn("1234567X")


def test_stopped_via_clean():
    med = pf.clean({"name": "A", "abgesetzt": True, "abgesetzt_am": "2026-11-01"}, T)
    assert med["abgesetzt"] is True and med["abgesetzt_am"] == "2026-11-01"


def test_pzn_wrong_check_digit_rejected():
    ok = next(p for p in (f"{i:07d}" + str(sum(int(d) * k for k, d in enumerate(f"{i:07d}", 1)) % 11) for i in range(1000, 1200)) if len(p) == 8)
    bad = ok[:-1] + str((int(ok[-1]) + 1) % 10)
    with pytest.raises(ValueError):
        pf.normalize_pzn(bad)
    assert ok[0] == "0" and pf.normalize_pzn(ok[1:]) == ok  # 7-stellige PZN wird aufgefuellt
