# ha-medikamentenplan
HA-Custom-Integration: Medikamentenübersicht je Plan (Reichweite, Nachbestelldatum, Status, Button "Neue Packung angefangen"). Nur Übersicht, keine Erinnerungen. Daten lokal in `.storage/medikamentenplan.<entry_id>`.
Installation: `custom_components/medikamentenplan` nach `<config>/custom_components/`, HA neu starten, Integration "Medikamentenplan" hinzufügen (ein Eintrag je Plan), Medikamente über "Konfigurieren".
Tests: `pytest tests` (reine Berechnungsfunktionen in `calc.py`).

## Dashboard
`tools/gen_dashboard.py` erzeugt die Dashboard-Config (Übersicht dynamisch, je Plan ein View mit Karten je Medikament) aus der Entity-Registry; Ausgabe per `ha_config_set_dashboard(url_path="dashboard-medikamente")` einspielen. Ohne auto-entities sind die Medikamentenkarten statisch.
