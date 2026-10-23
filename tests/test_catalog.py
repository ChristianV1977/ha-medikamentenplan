import json
from pathlib import Path

D = Path(__file__).parent.parent / "custom_components/medikamentenplan/catalog"
import ast, re
_src = (D.parent / "const.py").read_text()
FORMS = set(ast.literal_eval(re.search(r"^FORMS = (\[.*?\])", _src, re.M).group(1)))
assert {"retardtablette", "magensaftresistente_hartkapsel", "tablette"} <= FORMS


def test_startliste():
    es = json.loads((D / "startliste.json").read_text(encoding="utf-8"))["eintraege"]
    assert len(es) >= 50
    names = [e["wirkstoff"] for e in es]
    assert len(names) == len(set(names))
    for e in es:
        assert set(e) == {"wirkstoff", "staerken", "darreichungsform", "packungsgroessen", "rezeptpflichtig", "zweck_vorschlag", "einheit"}
        assert e["darreichungsform"] in FORMS
        assert e["staerken"] and len(e["staerken"]) == len(set(e["staerken"]))
        assert e["packungsgroessen"] and all(isinstance(p, (int, float)) and p > 0 for p in e["packungsgroessen"])
        assert isinstance(e["rezeptpflichtig"], bool) and e["zweck_vorschlag"] and e["einheit"]


def test_hersteller():
    h = json.loads((D / "hersteller.json").read_text(encoding="utf-8"))["hersteller"]
    assert h and len(h) == len({x.lower() for x in h})
