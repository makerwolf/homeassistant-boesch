# Changelog

Ältere Versionen (bis v0.5.0): siehe
[GitHub Releases](https://github.com/makerwolf/homeassistant-boesch/releases).

## [Unreleased]

## [2026.11.2] – Warnung beim Warmwasser behoben

- **Heiz- und Kühlkurve:** Stützpunkte lassen sich wie in der Web-Oberfläche
  nur noch in ganzen Grad einstellen (bisher 0,5), die Heizkurve höchstens bis
  65 °C (bisher 100 °C). Feiner justiert wird über die Parallelverschiebung
  (0,1 K).
- **Warmwasser:** Behebt die Warnung „provides the deprecated
  _attr_temperature_unit / current_temperature / target_temperature“ im
  Protokoll von Home Assistant 2026.11.

## [2026.11.1] – Home Assistant Marketplace

- **Home Assistant Marketplace:** Installationsanleitung auf den in
  Home Assistant 2026.11 eingebauten Marketplace (Nachfolger von HACS)
  umgestellt.

## [2026.11.0] – Diagnose, Übersetzungen & Typisierung

Ab jetzt Versionsnummern nach Datum (Jahr.Monat.Nummer) wie bei Home Assistant.

- ⚠️ **Mindestens Home Assistant 2026.9:** Der Einrichtungsdialog nutzt jetzt
  probatio, die Validierungs-Bibliothek, die HA seit 2026.9 statt voluptuous
  verwendet.
- ⚠️ **Breaking – Zustände sind jetzt Schlüssel:** Status-Sensoren, Selects und
  der Trinkwasser-Modus speichern feste englische Schlüssel statt deutschem
  Klartext, z. B. `heating` statt „Heizen“, `eco` statt „Eco“,
  `one_time_charge` statt „Einmalladung“. Angezeigt wird weiterhin der
  übersetzte Text. **Automationen, Templates und Dashboard-Bedingungen, die auf
  Klartext-Zustände prüfen, müssen angepasst werden** (Liste der Schlüssel:
  `translations/de.json`). Im Verlauf stehen ältere Einträge mit dem alten Text.
- **Deutsch und Englisch:** Entity-Namen, Zustände, Gerätenamen und
  Fehlermeldungen folgen der Sprache von Home Assistant. Dabei sind auch die
  Schreibweisen geglättet („Rücklauftemperatur“, „Außentemperatur“,
  „Kühlbetrieb“). Entity-IDs bleiben unverändert; selbst vergebene Namen auch.
- **Diagnosedaten:** *Geräte & Dienste → Bösch → ⋮ → Diagnose herunterladen*
  liefert Rohregister, Web-Datenpunkte und Verbindungsstatus. IP, Passwort und
  Seriennummern sind geschwärzt – hilfreich für Fehlerberichte.
- **Geräteinfo:** Mit Web-Passwort zeigen WANDA, Hydrobox und
  Wärmepumpenmanager Seriennummer und Firmware; „Gerät besuchen" öffnet das
  Webinterface.
- **Aufgeräumte Geräteseite:** Laufzeiten, Alarmcode und Fühlereingänge stehen
  unter *Diagnose*, Saison-Schwellen und PV-Sollwerte unter *Konfiguration*.
  Bei Neuinstallation sind `sensor.boesch_wanda_laufzeit_seit_start` und
  `sensor.boesch_hb_hkp2_laufzeit` deaktiviert (bestehende bleiben, wie sie
  sind).
- **Keine Leichen mehr:** Wer HK2, den externen WEZ, einen Fühlereingang oder
  das Web-Passwort abschaltet, bekommt die zugehörigen Entities und ggf. das
  Gerät Wärmepumpenmanager entfernt, statt sie als „nicht verfügbar" zu
  behalten. Übrig gebliebene Geräte lassen sich von Hand löschen.
- **README:** Abschnitte zu Datenaktualisierung, Anwendungsbeispielen,
  bekannten Einschränkungen, Fehlerbehebung und Entfernen.

## [0.6.0] – Hochauflösende Leistung, Mischer & Anwesenheit

- **Hochauflösende Leistungswerte (optional):** Neuer Haken unter
  *Konfigurieren → Webinterface*. Die 8 Leistungssensoren der WANDA
  (`sensor.boesch_wanda_leistung*`, `sensor.boesch_wanda_el_leistung*` – gesamt,
  Heizen, TWE, Kühlen) kommen dann aus dem Webinterface mit **0,01 kW** statt per
  Modbus mit 0,1 kW.
  - Warum: Modbus schneidet die Leistungen ab statt zu runden – in einer
    Parallelmessung lag die elektrische Leistung per Modbus im Mittel
    **ca. 3,5 % zu niedrig** (thermisch ca. 1,1 %). Stromverbrauch im Energy
    Dashboard und Arbeitszahl (JAZ) waren dadurch bisher leicht geschönt.
  - Entity-IDs, Verlauf und Energiezähler bleiben – sie werden nur genauer.
    Beim Einschalten springen die Werte daher um einige Prozent nach oben.
  - Ist das Webinterface kurz nicht erreichbar, gelten für diesen Abruf
    automatisch die Modbus-Werte.
- **Neue Web-Entities** (mit Web-Passwort):
  - `number.boesch_hb_hk1_kuehlkurve_p15` … `_p40` – die 5 Stützpunkte der
    Kühlkurve HK1 (bei 15 / 25 / 30 / 35 / 40 °C Außentemperatur)
  - `sensor.boesch_hb_hk1_mischer` – Mischer-Öffnung HK1 (%)
  - `sensor.boesch_hb_saison_aussentemperatur` – Außentemperatur, nach der die
    Saisonumschaltung schaltet
  - `switch.boesch_wpm_anwesenheit` – Anwesenheitsstatus, **schreibbar**, am
    neuen Gerät **Bösch Wärmepumpenmanager**
- **Robuster:** Ein einzelner gesperrter Datenpunkt im Webinterface lässt die
  übrigen Web-Werte nicht mehr ausfallen.
- **Fix Energiezähler:** War die Wärmepumpe zeitweise nicht erreichbar, wurde
  die ganze Ausfallzeit beim nächsten erfolgreichen Abruf mit der letzten
  Leistung mitgezählt (Strom- und Wärmemenge zu hoch). Ausfälle werden jetzt
  ausgelassen.
- **Fix Verbindung:** Timeouts und Verbindungsabbrüche erscheinen als kurze
  Fehlermeldung statt als Traceback im Log; beim Schalten/Einstellen kommt
  eine verständliche Fehlermeldung. Startet die Integration bei nicht
  erreichbarem Gerät mehrfach neu, bleiben keine Modbus-Verbindungen mehr offen.
- **Web-Passwort geändert?** Home Assistant meldet sich jetzt mit „Erneut
  authentifizieren“ und fragt nach dem neuen Passwort, statt die Web-Entities
  stumm als nicht verfügbar zu zeigen.
- **Entity-Namen nach HA-Standard:** Namen sind jetzt relativ zum Gerät, das
  Kürzel „WP“/„HB“ entfällt – angezeigt wird z. B. „Bösch WANDA
  Vorlauftemperatur B16“ statt „WP Vorlauftemperatur B16“. **Entity-IDs,
  Verlauf und Statistik bleiben unverändert**; selbst vergebene Namen auch.
  Karten ohne eigenen Titel zeigen den neuen Namen.
