# ha-medikamentenplan
HA-Custom-Integration: Medikamentenübersicht je Plan (Reichweite, Nachbestelldatum, Status, Button "Neue Packung angefangen"). Nur Übersicht, keine Erinnerungen. Daten lokal in `.storage/medikamentenplan.<entry_id>`.
Installation: `custom_components/medikamentenplan` nach `<config>/custom_components/`, HA neu starten, Integration "Medikamentenplan" hinzufügen (ein Eintrag je Plan), Medikamente über "Konfigurieren".
Tests: `python3 -m venv .venv && .venv/bin/pip install pytest && .venv/bin/python -m pytest tests` (reine Berechnungsfunktionen in `calc.py`).

## Dashboard
Dashboard: auto-entities-Karte (HACS) mit Jinja-Filter, dringendste zuerst; `tools/gen_dashboard.py` ist überholt.
