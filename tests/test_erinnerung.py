import importlib, pathlib, sys, types
from datetime import datetime

pkg = types.ModuleType("mp2"); pkg.__path__ = [str(pathlib.Path(__file__).parent.parent / "custom_components/medikamentenplan")]
sys.modules["mp2"] = pkg
er = importlib.import_module("mp2.erinnerung")

MEDS = {
    "a": {"name": "A", "modus": "taeglich", "morgens": 1, "abends": 1, "packungsgroesse": 10, "anbruch": "2026-11-01", "vorlauf_tage": 7, "dosis": 1, "pro_tag": 2, "vorrat": []},
    "b": {"name": "B", "modus": "taeglich", "morgens": 2, "packungsgroesse": 100, "anbruch": "2026-11-01", "vorlauf_tage": 7, "dosis": 1, "pro_tag": 2, "vorrat": []},
    "c": {"name": "C", "modus": "bedarf", "morgens": 1, "packungsgroesse": 10, "anbruch": "2026-11-01", "vorrat": []},
    "d": {"name": "D", "modus": "taeglich", "morgens": 1, "abgesetzt": True, "packungsgroesse": 10, "anbruch": "2026-11-01", "vorrat": []},
}
at = lambda hm: datetime.fromisoformat(f"2026-11-03T{hm}:00")


def on(**kw):
    s = er.merge_settings({"aktiv": True, "ziel": "mobile_app_x", **kw}); return s


def test_default_is_off():
    s = er.merge_settings(None)
    assert s["aktiv"] is False and s["ziel"] is None
    assert er.due(s, MEDS, at("08:00")) == []


def test_off_or_no_target_sends_nothing():
    assert er.due(er.merge_settings({"aktiv": True}), MEDS, at("08:00")) == []
    assert er.due(er.merge_settings({"ziel": "x"}), MEDS, at("08:00")) == []


def test_slot_counts_only_active_daily_meds_without_names():
    r = er.due(on(), MEDS, at("08:00"))
    assert [x["key"] for x in r] == ["morgens"] and "2 Medikamente" in r[0]["message"]
    assert not any(m["name"] in r[0]["message"] for m in MEDS.values())
    assert [x["key"] for x in er.due(on(), MEDS, at("18:00"))] == ["abends"]
    assert er.due(on(), MEDS, at("12:00")) == []  # mittags: niemand hat eine Dosis


def test_once_per_day_and_custom_time():
    assert er.due(on(gesendet={"morgens": "2026-11-03"}), MEDS, at("08:00")) == []
    assert er.due(on(zeiten={"morgens": "07:30"}), MEDS, at("08:00")) == []
    assert len(er.due(on(zeiten={"morgens": "07:30"}), MEDS, at("07:30"))) == 1


def test_refill_threshold():
    # A: 10 Stueck, 2/Tag ab 01.11. -> am 03.11. noch 6 Tage; B: 100 Stueck -> viele
    r = er.due(on(schwelle_tage=7), MEDS, at("09:00"))
    assert [x["key"] for x in r] == ["nachkauf"] and r[0]["message"].startswith("Nachkaufen: 1 Medikament ")
    assert er.due(on(schwelle_tage=2), MEDS, at("09:00")) == []
    assert er.due(on(gesendet={"nachkauf": "2026-11-03"}), MEDS, at("09:00")) == []
