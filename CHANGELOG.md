# Changelog

Ältere Versionen (bis v0.5.0): siehe
[GitHub Releases](https://github.com/makerwolf/homeassistant-boesch/releases).

## [Unreleased]

## [2026.11.4] – Feine Heizkurve & Heizkurven-Karte

Die Bösch-Heizkurve lässt sich nur in ganzen Grad einstellen – Stützpunkte
wie Parallelverschiebung. Für eine Fußbodenheizung ist 1 K Vorlauf ein großer
Schritt. Mit dieser Version kann Home Assistant die Heizkurve HK1 selbst in
**0,1-K-Schritten** rechnen und ans Gerät schreiben. Dazu kommt eine
Dashboard-Karte, mit der sich die Kurve direkt im Diagramm einstellen lässt.

Alles Neue ist optional und braucht das Web-Passwort (*Konfigurieren →
Webinterface*). Wer nichts einschaltet, merkt von dem Update nur die feineren
Festwerte.

### ✨ Feine Heizkurve HK1

**Einschalten**

1. *Geräte & Dienste → Bösch → Konfigurieren → Webinterface* → Haken bei
   **„Feine Heizkurve aus Home Assistant verwenden“**.
2. Am Gerät *Bösch Hydrobox* den Schalter **„Feine Heizkurve aktiv“**
   einschalten.

Beim ersten Einschalten übernimmt die feine Kurve die aktuelle Bösch-Kurve
samt Parallelverschiebung, und der erste geschriebene Wert ist genau der Soll,
den das Gerät gerade selbst rechnet – es springt nichts. Ab dann lässt sich die
Kurve in Zehntelgrad verfeinern. Ausschalten stellt den Heizmodus zurück auf
„Außentemperaturkurve“; die Bösch-Kurve am Gerät bleibt dabei unverändert.

**Wie es arbeitet**

Home Assistant interpoliert die Kurve über die **gemittelte Außentemperatur**
(wie das Gerät selbst), addiert feine Parallelverschiebung und Zuschlag und
schreibt das Ergebnis als *Festwert HK1*; der Heizmodus HK1 steht dabei auf
„Festwert“. Das Gerät übernimmt den Wert exakt als Soll für Heizkreis und
Heizspeicher.

**Neue Entities**

| Entity | Bereich | Wofür |
|---|---|---|
| HK1 Feinkurve bei −20 … +20 °C (`number.boesch_hb_hk1_feinkurve_m20` … `_p20`) | 10–65 °C, 0,1 K | die 9 Stützpunkte |
| HK1 feine Parallelverschiebung (`number.boesch_hb_hk1_fein_parallel`) | −5 … +5 K | ganze Kurve verschieben, bleibt gespeichert |
| HK1 Zuschlag (`number.boesch_hb_hk1_zuschlag`) | −5 … +5 K | für Automationen, z. B. Nachtabsenkung; fährt über die Rampe |
| HK1 Sofort-Anhebung (`number.boesch_hb_hk1_sofort_anhebung`) | 0 … 12 K | z. B. Anlaufhilfe nach Warmwasser; wirkt sofort |
| HK1 berechneter Festwert (`sensor.boesch_hb_hk1_fein_festwert`) | | was geschrieben wird; Attribute zeigen Basiskurve, Ziel, zuletzt geschriebenen Wert und warum gerade gehalten wird |
| Feine Heizkurve aktiv (`switch.boesch_hb_hk1_feinkurve_aktiv`) | | ein/aus |

Zuschlag und Sofort-Anhebung stehen nach einem Neustart von Home Assistant
wieder auf 0 – eine Automation, die sie setzt, bleibt so nie hängen.

Beispiel Nachtabsenkung:

```yaml
triggers:
  - trigger: time
    at: "22:00:00"
    id: nacht
  - trigger: time
    at: "05:00:00"
    id: tag
actions:
  - action: number.set_value
    target:
      entity_id: number.boesch_hb_hk1_zuschlag
    data:
      value: "{{ -2 if trigger.id == 'nacht' else 0 }}"
```

**Schonend für Gerät und Heizung**

- **Rampe:** Änderungen werden langsam angefahren – standardmäßig 0,1 K senken
  bzw. 0,2 K heben je 10 Minuten. Die Sofort-Anhebung geht als einzige an der
  Rampe vorbei.
- **Wenig Schreibzugriffe:** höchstens alle 10 Minuten und nur bei mindestens
  0,1 K Unterschied.
- **Grenzen:** Vorlauf standardmäßig 20–40 °C, mit Sofort-Anhebung bis 45 °C.
- Grenzen, Rampe und Schreibabstand lassen sich unter *Konfigurieren →
  Feine Heizkurve (Grenzen, Rampe)* anpassen.
- **Halten:** Während Warmwasser und Abtauen sowie ohne Außentemperatur oder
  Webinterface wird nichts geschrieben, die Rampe pausiert.
- **Neustart:** Beim Beenden von Home Assistant wird der Festwert ohne Zuschlag
  und Sofort-Anhebung geschrieben, damit keine Anhebung stehen bleibt, solange
  HA nicht läuft. Danach macht die Kurve von selbst weiter.

**Zieht sich zurück statt gegenzusteuern**

Wird der Heizmodus HK1 umgestellt (auch zurück auf „Außentemperaturkurve“ –
am Gerät, im Webinterface oder in HA) oder der Festwert von außen geändert –
im Webinterface, über die Entity „HK1 Festwert Heizen“ oder durch eine zweite
Home-Assistant-Instanz mit feiner Heizkurve –, schaltet sich die feine
Heizkurve ab und meldet das unter **Einstellungen → System → Reparaturen**.
Das Gerät heizt dann mit festem Wert **ohne Außentemperatur-Führung** weiter.
Abhilfe: den Schalter wieder einschalten oder den Heizmodus auf
„Außentemperaturkurve“ stellen; der Hinweis verschwindet dann von selbst.
Die feine Heizkurve deshalb immer nur in einer Instanz einschalten.

**Gut zu wissen**

- ⚠️ Solange die feine Heizkurve aktiv ist, **wirkt die Parallelverschiebung am
  Gerät (`number.boesch_hb_hk1_parallel`) nicht** – das Gerät übernimmt den
  Festwert unverändert. Stattdessen die feine Parallelverschiebung oder den
  Zuschlag verwenden.
- Änderungen an der Bösch-Kurve (`number.boesch_hb_hk1_heizkurve_*`) haben bei
  aktiver feiner Heizkurve keine Wirkung; sie gelten erst wieder nach dem
  Ausschalten.
- Home Assistant muss laufen, damit die Kurve der Außentemperatur folgt. Fällt
  HA länger aus, heizt das Gerät mit dem zuletzt geschriebenen Festwert weiter.
  **Notfall-Rückweg:** Im Bösch-Webinterface (oder am Gerät) den Heizmodus HK1
  auf „Kurve“ stellen – dann regelt das Gerät wieder selbst nach seiner
  eigenen Heizkurve. Läuft HA wieder, erkennt es die Umstellung, lässt die
  feine Heizkurve aus und meldet das unter Reparaturen; bei Bedarf einfach
  wieder einschalten.

### 📈 Dashboard-Karte „Heizkurve“

- Zeigt eine Heizkurve als Diagramm mit dem aktuellen Betriebspunkt
  (Außentemperatur, optional Ist-Vorlauf als zweiter Punkt).
- Stützpunkte per Maus oder Finger ziehen, Feinschritte mit den Pfeiltasten.
- Kommt mit der Integration und wird automatisch geladen – **keine
  Dashboard-Ressource nötig**. Nach dem Update einmal den Browser neu laden,
  dann steht sie unter *Karte hinzufügen → Heizkurve*.
- Vorbelegt mit der feinen Heizkurve (sonst der Bösch-Kurve) und der
  gemittelten Außentemperatur; funktioniert aber mit beliebigen
  `number`-Entities.

```yaml
type: custom:heizkurve-card
title: Feine Heizkurve
outdoor_entity: sensor.boesch_hb_aussentemperatur_gemittelt
flow_entity: sensor.boesch_hb_hk1_ist
points:
  - { x: -20, entity: number.boesch_hb_hk1_feinkurve_m20 }
  - { x: -15, entity: number.boesch_hb_hk1_feinkurve_m15 }
  - { x: -10, entity: number.boesch_hb_hk1_feinkurve_m10 }
  - { x: -5, entity: number.boesch_hb_hk1_feinkurve_m5 }
  - { x: 0, entity: number.boesch_hb_hk1_feinkurve_0 }
  - { x: 5, entity: number.boesch_hb_hk1_feinkurve_p5 }
  - { x: 10, entity: number.boesch_hb_hk1_feinkurve_p10 }
  - { x: 15, entity: number.boesch_hb_hk1_feinkurve_p15 }
  - { x: 20, entity: number.boesch_hb_hk1_feinkurve_p20 }
```

Weitere Optionen: `y_min`, `y_max`, `step`.

### Weitere Änderungen

- **Festwert Heizen und Kühlen HK1** (`number.boesch_hb_hk1_festwert`,
  `number.boesch_hb_hk1_festwert_kuehlen`) jetzt in 0,1-K-Schritten statt 0,5 K.

## [2026.11.3] – Softwareupdate & Firmware-Versionen

- **Softwareupdate (Webinterface):** neue Diagnose-Sensoren am
  Wärmepumpenmanager aus *System-Einstellungen → Update*: Update-Status
  (z. B. „Aktuell“, „Neue Version verfügbar“), Download-Fortschritt und
  Infotext (standardmäßig deaktiviert). Nur lesend – ein Update wird nie
  gestartet.
- **Firmware-Versionen (Webinterface):** je ein Diagnose-Sensor für
  Wärmepumpenmanager, WANDA und Hydrobox. Im Verlauf sieht man, wann eine neue
  Firmware kam; die Version in den Geräteinfos aktualisiert sich jetzt auch
  ohne Neustart von Home Assistant.

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
