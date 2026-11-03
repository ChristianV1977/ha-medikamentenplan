# Changelog

## 1.9.0 (2026-11-03)
- **Erinnerungen je Plan**, in HA bedienbar ueber Entities am Plan-Geraet (Standard AUS, niemand bekommt ungefragt Nachrichten):
  - `switch` Erinnerungen aktiv, vier `time` (morgens/mittags/abends/nachts) und ein `time` fuer die Nachkauf-Erinnerung, `number` Nachkauf ab Reichweite (Tage, Standard 7), `select` Erinnerungsziel (ein `notify`-Dienst, z. B. `mobile_app_<geraet>`).
  - Einnahme-Erinnerung: zur eingestellten Uhrzeit, wenn der Plan in diesem Zeitfenster taegliche, nicht abgesetzte Medikamente hat. Nachkauf-Erinnerung: taeglich zur eingestellten Zeit, wenn die Reichweite inkl. Vorrat die Schwelle erreicht. Jede Art hoechstens einmal pro Tag (auch ueber Neustarts, im Store).
  - Nachrichten enthalten bewusst keine Medikamentennamen, nur Anzahlen.
  - Service `medikamentenplan.erinnerung_testen` (Feld `plan`): Testnachricht, als TEST markiert, an das Ziel des Plans.
  - Einschraenkungen: Medikamente im Intervall- oder Bedarfsmodus loesen keine Zeit-Erinnerung aus; verpasste Minute (HA aus) wird nicht nachgeholt; die Schwelle gilt nur fuer die Erinnerung, nicht fuer Status/Nachbestelldatum.
- **Medikamente ohne Admin pflegen** (Options-Flow braucht Admin): neue Services `medikament_hinzufuegen`, `medikament_bearbeiten`, `medikament_absetzen`, `medikament_entfernen`, alle mit Pflichtfeld `plan`; Bearbeiten/Absetzen/Entfernen nehmen die `entity_id` des Reichweite-Sensors und pruefen, dass sie zum angegebenen Plan gehoert. Grenzen und Pflichtregeln wie im Options-Flow (Logik in `pflege.py`, vom Options-Flow mitgenutzt). Name, PZN (mit Pruefziffer, lernt die Zuordnung), Darreichungsform, Dosis je Zeitfenster, Intervall/Bedarf, Packungsgroesse, Anbruch, Notiz u. a.; beim Bearbeiten aendern nur gelieferte Felder, Leerstring loescht ein optionales Feld, der Vorrat bleibt. Entfernen verlangt `bestaetigen: true`.
- **Neue Karte** `custom:medikamentenplan-pflege-card` (Option `plan`, Script 1.6.8): Liste der Medikamente dieses Plans, Formular zum Anlegen und Bearbeiten, Absetzen/Wieder aufnehmen, Entfernen mit Zweit-Tipp. Nur DOM per textContent.
- Hinweis: Normale HA-Nutzer duerfen Services aufrufen; die Trennung zwischen Plaenen ist Anzeige- und Plan-Pruefung, kein Zugriffsschutz.
- Tests: `tests/test_erinnerung.py`, `tests/test_pflege.py`.

## 1.8.0 (2026-11-03)
- **Personensicht:** Die Services `scan_code`, `vorrat_hinzufuegen`, `packung_anfangen` und `pzn_zuordnen` haben ein optionales Feld `plan` (Titel des Plans). Damit werden PZN-Treffer, Kandidatenliste und `entity_id`-Pruefung nur in diesem Plan gesucht; ohne `plan` bleibt das Verhalten unveraendert. Die Seriennummer-Doppelsperre gilt bewusst weiter planuebergreifend.
- Scanner-Karte (Script 1.6.7): neue Option `plan: <Plan-Titel>` reicht das Feld an die Services weiter. So zeigt der Scan-Dialog einer Person nie Medikamente eines anderen Plans.
- Hinweis: Das ist eine Anzeige-/Suchtrennung, kein Zugriffsschutz; Entities bleiben fuer alle HA-Nutzer lesbar. Die Trennung im Dashboard erfolgt ueber Sichtbarkeit pro Nutzer.

## 1.7.2 (2026-10-30)
- Scanner-Karte (Script 1.6.6): neue Option `camera: user | environment` (Standard environment). `user` nimmt die Frontkamera (facingMode ideal user), Retry-Kette: user mit Aufloesung, user ohne, Geraete mit Label front/vorder/user (oder `camera_label`, Teilstring), dann video:true. Vorschau wird gespiegelt, die Erkennung liest den ungespiegelten Frame. Debug-Log nennt Geraet und facingMode.

## 1.7.1 (2026-10-30)
- Scanner-Karte (Script 1.6.5): Kamera-Start mit Retry-Kette bei NotReadable/Overconstrained/Abort (environment ohne Aufloesung, ohne facingMode, video:true, jede videoinput-deviceId einzeln), jeder Versuch im Debug-Log, Hinweis "Kamera evtl. von anderer App belegt".
- Neue optionale Kartenoption `pause_fully_motion: <switch-Entity der Fully-Bewegungserkennung>`: schaltet sie vor dem Kamerastart aus (1,8 s Wartezeit) und nach jedem Ende wieder ein (Code erkannt, Abbrechen, Fehler, Zeitueberschreitung 120 s, Karte entfernt, pagehide/Ausblenden).

## 1.7.0 (2026-10-30)
- **"Neue Packung angefangen"** entscheidet selbst: Ist Vorrat da, wird die Packung mit dem fruehesten Verfall aus dem Vorrat angebrochen (deren Packungsgroesse, Vorrat minus 1). Ohne Vorrat gilt sie als neu gekauft (Anbruch heute, Bestand = Packungsgroesse x Anzahl). Eine persistent_notification nennt den eingetretenen Fall.
- **Neuer Button** `button.medikament_*_auf_vorrat_legen` ("Packung auf Vorrat legen"): bucht Anzahl Packungen x Packungsgroesse aus den Popup-Feldern ohne Scan auf Vorrat (Verfall unbekannt), danach Anzahl = 1. Kein Verfall-Datumsfeld (bewusst weggelassen).
- **Entfernt:** Button-Entity `*_aus_vorrat_anbrechen` (Registry-Eintrag nach dem Neustart entfernen). Der Service `medikamentenplan.aus_vorrat_anbrechen` bleibt.
- **Scan-Dialog "Jetzt anfangen"** bleibt unveraendert: die gescannte Packung wird angefangen, nicht aus dem Vorrat genommen.

## 1.6.4 (2026-10-30)
- Scanner-Karte: Vorschau inline in der Karte (kein Overlay mehr), Zustandsmaschine (idle/starting/scanning/found/error), `set hass` speichert nur. Jeder Stop schreibt Status mit Grund, Track-ended und Entfernen der Karte (3 s Gnadenfrist bei Neuaufbau) werden angezeigt, eingeklapptes Debug-Log mit den letzten 10 Ereignissen.

## 1.6.3 (2026-10-30)
- Scanner-Karte: eigene Kamera-Steuerung statt ZXing-Reader (autoplay/muted/playsinline, play() mit Fehlerbehandlung, sichtbare Live-Vorschau). Erkennung nativ per BarcodeDetector (wenn data_matrix unterstuetzt), sonst ZXing per Canvas (max. 1280 px).
- Sichtbarer Status (Kamera startet / Suche Code / Code erkannt) und klare Fehlertexte (keine Berechtigung, Kamera nicht verfuegbar, Exception-Text); Stream wird nach Erkennung/Abbrechen gestoppt; Licht-Schalter und Dauerfokus, wenn unterstuetzt.

## 1.6.2 (2026-10-30)
- Verfallsdatum: Monat 00/13 und unmoegliche Tage (z. B. 260231) werden abgelehnt; leere Charge gilt als nicht vorhanden.

## 1.6.1 (2026-10-30) - Sicherheit
- Scanner-Karte baut den Dialog nur noch per createElement/textContent (kein innerHTML mit Code-Inhalt, Medikamentennamen oder Fehlertexten, XSS-Schutz).
- Parser verwirft Charge/Seriennummer mit unzulaessigen Zeichen (nur GS1-Zeichen ohne < > \" ' &, max. 20) und ungueltige Verfallsdaten; Test fuer eine XSS-Nutzlast in Charge/Seriennummer.

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
