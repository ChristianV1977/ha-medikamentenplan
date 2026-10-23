# ha-medikamentenplan
HA-Custom-Integration: Medikamentenübersicht je Plan (Reichweite, Nachbestelldatum, Status, Button "Neue Packung angefangen"). Nur Übersicht, keine Erinnerungen. Daten lokal in `.storage/medikamentenplan.<entry_id>`.
Installation: `custom_components/medikamentenplan` nach `<config>/custom_components/`, HA neu starten, Integration "Medikamentenplan" hinzufügen (ein Eintrag je Plan), Medikamente über "Konfigurieren".
Tests: `pytest tests` (reine Berechnungsfunktionen in `calc.py`).
