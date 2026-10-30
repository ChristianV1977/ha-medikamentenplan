# Changelog

## 1.6.0 (2026-10-30) - Packungs-Scan und Vorrat
- **Scan:** DataMatrix (securPharm, IFA/PPN `9N11…` oder GS1/NTIN `01 04150…`) und PZN-Strichcode (Code 39 `-12345678`) werden lokal geparst: PZN (mit Prüfziffer), Charge, Verfall, Seriennummer. Reiner Parser `gs1.py`, kein Internet.
- **Scanner-Karte** `custom:medikamentenplan-scan-card`: Kamera im Browser/der Companion-App (getUserMedia, Dekodierung mit mitgeliefertem ZXing, kein CDN), danach Dialog "Auf Vorrat legen" / "Jetzt anfangen" bzw. Zuordnung bei unbekannter PZN. Eingabe von Hand als Rückfall.
- **Vorrat:** je Medikament Liste ungeöffneter Packungen (Größe, Verfall, Charge). Neue Entities: `sensor.*_vorrat_packungen`, `sensor.*_reichweite_inkl_vorrat_tage`, `sensor.*_vorrat_verfall`, `button.*_aus_vorrat_anbrechen`, je Plan `sensor.*_scan_zustand` (bereit / zuordnung_noetig). Bestehende Entity-IDs und Werte bleiben kompatibel; `nachbestelldatum` und `status` rechnen den Vorrat mit, neue Attribute `reichweite_inkl_vorrat_tage`, `vorrat_*`, `naechster_verfall`, `verfall_warnung` (60 Tage vor Verfall).
- **Services** (mit Antwort): `scan_code`, `vorrat_hinzufuegen`, `packung_anfangen`, `pzn_zuordnen`, `aus_vorrat_anbrechen`, `vorrat_entfernen`, `scan_abbrechen`.
- **Doppelscan-Schutz:** dieselbe Seriennummer (Produkt + Seriennummer) wird nur einmal gebucht.
- **Store-Migration:** Schema 2 (`vorrat`, `pzn`, `serials`), verlustfrei und idempotent beim Laden. Rückweg: Store-Backup zurückspielen (alte Versionen ignorieren die neuen Schlüssel, speichern sie aber nicht mehr).
- Tests: `tests/test_gs1.py`, `tests/test_vorrat.py`.

## 1.5.4
Screenshots und README-Abschnitt.
