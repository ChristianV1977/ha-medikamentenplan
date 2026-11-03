"""Personensicht: _plans/find_pzn filtern nach Plan-Titel (HA-Importe gestubbt)."""
import importlib.util, pathlib, sys, types
from unittest.mock import MagicMock

for n in ["homeassistant", "homeassistant.core", "homeassistant.exceptions", "homeassistant.helpers",
          "homeassistant.helpers.config_validation", "homeassistant.helpers.entity_registry",
          "homeassistant.helpers.dispatcher", "homeassistant.util", "homeassistant.util.dt", "voluptuous"]:
    sys.modules.setdefault(n, MagicMock())
pkg = types.ModuleType("mp"); pkg.__path__ = [str(pathlib.Path(__file__).parent.parent / "custom_components/medikamentenplan")]
sys.modules["mp"] = pkg
sv = importlib.import_module("mp.services")


class P:
    def __init__(self, name, pzn):
        self.name, self.meds, self.pzn = name, {"m": {}}, {pzn: {"med": "m"}}


def hass():
    h = MagicMock(); h.data = {sv.DOMAIN: {"a": P("A", "1"), "b": P("B", "1"), "x": "kein plan"}}
    return h


def test_filter_by_plan():
    h = hass()
    assert len(sv.find_pzn(h, "1")) == 2           # ohne plan: wie bisher
    assert [p.name for p, _ in sv.find_pzn(h, "1", "B")] == ["B"]
    assert sv.find_pzn(h, "1", "C") == []
    assert [p.name for p in sv._plans(h, "A")] == ["A"]
