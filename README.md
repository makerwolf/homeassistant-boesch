# Bösch – Home Assistant Integration

[![hacs](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
![version](https://img.shields.io/badge/version-0.1.0-blue.svg)
![license](https://img.shields.io/badge/license-MIT-green.svg)

Eine eigenständige, per UI konfigurierbare Home-Assistant-Integration für
Wärmepumpen von **[Bösch](https://www.boesch.at/)** (Heizbösch), angebunden über
**Modbus TCP**. Sie kapselt die gesamte Modbus-Kommunikation in einer einzigen
TCP-Verbindung und einem zentralen, datengetriebenen Registermodell.

> **Unterstützte Geräte:** Bösch **WANDA 10** + **Hydrobox**.
> Weitere Bösch-Geräte lassen sich über das Registermodell ergänzen.

> ⚠️ Inoffizielles Community-Projekt, **nicht** mit der Bösch Heizsysteme GmbH
> verbunden oder von ihr unterstützt. Nutzung auf eigene Verantwortung.

## Funktionen

- **77 Datenpunkte** aus WANDA (Modbus-Adresse 40) und Hydrobox (50) über eine
  gemeinsame TCP-Verbindung.
- **Read-only** als `sensor` / `binary_sensor`, Statusregister als
  Enum-Sensoren mit lesbaren Zuständen.
- **Deutsch und Englisch:** Entity-Namen, Zustände und Fehlermeldungen folgen
  der Sprache von Home Assistant.
- **Schreibzugriff** auf alle in der Bösch-Liste als R/W dokumentierten Register:
  - `number` – Sollwerte (Parallelverschiebung, Sommer-/Winter-/Kühl-Schwellen,
    PV-Leistung & -Solltemperaturen, TWE-Sollwerte)
  - `select` – Modi (HK1/HK2 Betriebsart · Energiemodus · Saison, externer WEZ)
  - `water_heater` – Trinkwassererwärmung mit Ist-/Zieltemperatur und
    Einmalladungs-Modus
- **Webinterface (optional)**: Einstellungen, die per Modbus fehlen, über das
  Webinterface der Wärmepumpe (Kermi x-center): Heizmodus HK1
  (Außentemperaturkurve / Festwert / Aus), Festwert Heizen und Kühlen, die
  Stützpunkte von Heiz- und Kühlkurve, Mischer-Öffnung, Saison-Außentemperatur und
  Anwesenheitsstatus – optional
  auch hochauflösende Leistungswerte (0,01 statt 0,1 kW) für genauere
  Energiezähler.
- **UI-Konfiguration**: Verbindungstest im Setup, Options-Menü für Heizkreis 2,
  externen Wärmeerzeuger, Poll-Intervalle und frei belegbare Fühlereingänge.
- **Effizientes Polling**: ein `DataUpdateCoordinator` je Intervall-Klasse
  (15/30/60/300 s), zusammenhängende Register werden als Block gelesen.
- **Energie & Effizienz**: aus den Leistungen berechnete kWh-Zähler (Strom &
  Wärmemenge, gesamt + je Modus) fürs Energy Dashboard, plus laufende
  Jahresarbeitszahl (JAZ/SCOP).

## Installation (HACS)

1. HACS → Integrationen → ⋮ → *Benutzerdefinierte Repositories*
2. `https://github.com/makerwolf/homeassistant-boesch` als Kategorie
   **Integration** hinzufügen.
3. „Bösch" installieren, Home Assistant neu starten.
4. *Einstellungen → Geräte & Dienste → Integration hinzufügen → Bösch*.

Alternativ den Ordner `custom_components/boesch/` manuell nach
`<config>/custom_components/` kopieren und HA neu starten.

## Konfiguration

**Setup:** IP-Adresse der Wärmepumpe (Pflichtfeld, kein Default), Port (`502`), Modbus-Adresse WANDA (`40`) und
Hydrobox (`50`). Vor dem Anlegen wird die Verbindung getestet.
Optional das **Web-Passwort** (wie beim Browser-Login am Webinterface), um die
Webinterface-Entities zu aktivieren; später unter *Konfigurieren →
Webinterface* änderbar, leer lassen schaltet sie ab.

**Auto-Erkennung:** Das Kermi x-center meldet sich per DHCP mit dem Hostnamen
`xcenter`. Home Assistant schlägt die Wärmepumpe dann unter *Entdeckt* vor,
die IP ist vorbelegt. Wechselt die IP später, übernimmt die Integration die
neue Adresse automatisch (Erkennung über die MAC-Adresse).

**Optionen** (über *Konfigurieren* → Menü, jederzeit änderbar):

*Allgemein:*

| Option | Default | Wirkung |
|---|---|---|
| Zweiter Heizkreis vorhanden | aus | Blendet die HK2-Entities ein/aus |
| Externer Wärmeerzeuger vorhanden | aus | Blendet die WEZ-Entities ein/aus |
| Intervall Live-Werte | 15 s | Vorlauf/Rücklauf, COP, Leistungen, WP-Status |
| Intervall Standard | 30 s | Temperaturen, Speicher |
| Intervall Sollwerte | 60 s | Sollwerte, Betriebsarten, Fühlereingänge |
| Intervall Betriebsstunden | 300 s | Zählerstände |

HK2 und WEZ sind **Opt-in** (Basisanlage: 1 Heizkreis, kein externer WEZ).

*Fühlereingänge (AI1–AI8):* Die frei belegbaren Analogeingänge der Hydrobox sind
anlagenspezifisch verdrahtet (vom Techniker) und daher **standardmäßig
ausgeblendet**. Pro Eingang einen Namen eingeben aktiviert und benennt ihn; leer
lassen blendet ihn aus. Beispiel: `AI1 → Heizspeicher-Temperatur`,
`AI8 → Außentemperatur`.

## Geräte & Entities

Zwei Geräte im Device-Registry: **Bösch WANDA** und **Bösch Hydrobox**. Die
`unique_id`s (und darauf abgebildet die `entity_id`s) folgen dem Schema
`boesch_wanda_*` (WANDA) bzw. `boesch_hb_*` (Hydrobox) — z. B.
`sensor.boesch_wanda_b16_vorlauf`. Ein Upgrade von einer älteren Version
benennt bestehende Entities per Migration einmalig um; Historie und
Langzeitstatistik bleiben dabei erhalten.

Mit Web-Passwort kommen dazu (Hydrobox bzw. drittes Gerät **Bösch
Wärmepumpenmanager**):

| Entity | Inhalt |
|---|---|
| `select.boesch_hb_hk1_heizmodus` | Heizmodus HK1: Außentemperaturkurve / Festwert / Aus |
| `number.boesch_hb_hk1_festwert` | Konstanter Vorlauf-Sollwert Heizen (0–100 °C) |
| `number.boesch_hb_hk1_festwert_kuehlen` | Konstanter Sollwert Kühlen (5–30 °C) |
| `number.boesch_hb_hk1_heizkurve_m20` … `_p20` | Vorlauf-Sollwert bei −20 … +20 °C Außentemperatur (9 Stützpunkte) |
| `number.boesch_hb_hk1_kuehlkurve_p15` … `_p40` | Kühl-Vorlauf-Sollwert bei 15 / 25 / 30 / 35 / 40 °C Außentemperatur (5 Stützpunkte, 5–30 °C) |
| `sensor.boesch_hb_hk1_mischer` | Mischer-Öffnung HK1 (%) |
| `sensor.boesch_hb_saison_aussentemperatur` | Außentemperatur, nach der die Saisonumschaltung (Sommer/Winter/Kühlen) schaltet |
| `switch.boesch_wpm_anwesenheit` | Anwesenheitsstatus des Wärmepumpenmanagers (an = anwesend) |

**Hochauflösende Leistungswerte** (Haken unter *Konfigurieren → Webinterface*):
Modbus liefert die Leistungen nur in 0,1-kW-Schritten und **schneidet ab**
(gemessen: el. Leistung im Mittel ~3,5 % zu niedrig). Mit dem Haken werden die
8 bestehenden Leistungssensoren (`sensor.boesch_wanda_leistung*`,
`sensor.boesch_wanda_el_leistung*`) stattdessen aus dem Webinterface mit
0,01 kW gefüllt – Entity-IDs und Verlauf bleiben, Stromverbrauch und JAZ
werden genauer. Ist das Webinterface kurz nicht erreichbar, gelten für diesen
Poll die Modbus-Werte. Beim Einschalten springen die Werte daher um einige
Prozent nach oben.

Die Web-API ist inoffiziell (aus der Web-Oberfläche abgeleitet) und kann sich
mit Firmware-Updates ändern.

Mit Web-Passwort zeigen die Geräte außerdem **Seriennummer und Firmware**;
„Gerät besuchen" öffnet das Webinterface.

**Kategorien:** Laufzeiten, Alarmcode und die rohen Fühlereingänge stehen unter
*Diagnose*, Saison-Schwellen, PV-Sollwerte und Kurven-Stützpunkte unter
*Konfiguration*. Zwei selten gebrauchte Sensoren werden **deaktiviert**
angelegt und lassen sich in den Entity-Einstellungen einschalten:
`sensor.boesch_wanda_laufzeit_seit_start` und `sensor.boesch_hb_hkp2_laufzeit`
(Register 301 ist in der Doku mehrfach vergeben, siehe unten).

Wer HK2, den externen WEZ, einen Fühlereingang oder das Web-Passwort wieder
abschaltet, bekommt die zugehörigen Entities (und ggf. das Gerät
Wärmepumpenmanager) automatisch entfernt.

**Zustände in Automationen:** Enum-Sensoren, Selects und der Trinkwasser-Modus
speichern feste englische Schlüssel, angezeigt wird der übersetzte Text. In
Automationen und Templates daher die Schlüssel verwenden, z. B.
`sensor.boesch_wanda_status` = `heating` (Anzeige „Heizen“),
`water_heater.boesch_hb_twe` = `normal` / `one_time_charge` („Einmalladung“).
Alle Schlüssel stehen in
[`translations/de.json`](custom_components/boesch/translations/de.json) unter
`entity`. Im Automations-Editor bietet HA sie als Auswahl an.

## Datenaktualisierung

Die Integration fragt die Wärmepumpe zyklisch ab (`local_polling`), es gibt
keine Push-Meldungen. Je Intervall-Klasse läuft ein eigener Abruf, Standard
15 / 30 / 60 / 300 s (siehe *Optionen*). Zusammenhängende Register werden als
Block gelesen, eine komplette Runde sind nur wenige Modbus-Anfragen. Die
Webinterface-Werte laufen im Takt der Sollwerte (60 s), die hochauflösenden
Leistungen im Live-Takt. Nach jedem Schreiben wird sofort neu gelesen.

## Anwendungsbeispiele

**Trinkwasser mit PV-Überschuss laden** (Einspeise-Sensor anpassen):

```yaml
automation:
  - alias: "WP: TWE-Einmalladung bei PV-Überschuss"
    triggers:
      - trigger: numeric_state
        entity_id: sensor.netz_einspeisung   # W, positiv = Einspeisung
        above: 2500
        for: "00:10:00"
    conditions:
      - condition: state
        entity_id: water_heater.boesch_hb_twe
        state: "normal"
    actions:
      - action: water_heater.set_operation_mode
        target:
          entity_id: water_heater.boesch_hb_twe
        data:
          operation_mode: "one_time_charge"
```

**Anwesenheit an den Wärmepumpenmanager melden** (braucht Web-Passwort):

```yaml
automation:
  - alias: "WP: Anwesenheit"
    triggers:
      - trigger: state
        entity_id: zone.home
    actions:
      - action: "switch.turn_{{ 'on' if states('zone.home') | int > 0 else 'off' }}"
        target:
          entity_id: switch.boesch_wpm_anwesenheit
```

Weitere Ideen: Energiemodus `select.boesch_hb_hk1_energiemodus` nachts auf
*Eco* (`eco`), Parallelverschiebung `number.boesch_hb_hk1_parallel` bei günstigem
Strompreis anheben, Benachrichtigung bei `binary_sensor.boesch_wanda_alarm_bs`.

## Energie & Effizienz (Energy Dashboard)

Aus den momentanen Leistungen (kW) werden per trapezförmiger Zeit-Integration
kumulative **kWh-Zähler** gebildet (`total_increasing`, neustartfest):

- **Strom**: `WP Stromverbrauch gesamt` + je Modus (Heizen / TWE / Kühlen)
- **Wärmemenge**: `WP Wärmemenge gesamt` + je Modus

Der Gesamt-Stromzähler kommt direkt ins **Energy Dashboard** (unter *Einzelne
Geräte*). **Nicht** täglich resetten — das Dashboard periodisiert selbst aus dem
kumulativen Wert.

Aus Wärmemenge ÷ Stromenergie ergibt sich die laufende **Arbeitszahl** (SCOP
*seit Installation*): `WP Arbeitszahl gesamt` sowie je Modus (Heizen / TWE /
Kühlen). Das ist ein Lebensdauer-Mittel — es stabilisiert sich, je mehr Energie
zusammenkommt (anfangs schwankt es noch stark).

**Tages-/Monatswerte** (optional, ohne die Basiszähler anzutasten) via
`utility_meter`-Helper:

```yaml
utility_meter:
  wp_strom_taeglich:
    source: sensor.boesch_wanda_energie_el_gesamt
    cycle: daily
  wp_strom_monatlich:
    source: sensor.boesch_wanda_energie_el_gesamt
    cycle: monthly
```

### Jahresarbeitszahl (JAZ) pro Jahr

Die Integration liefert bewusst nur die *Lebensdauer*-Arbeitszahl. Eine **Jahres**-
JAZ mit frei wählbarem Stichtag ist Verrechnungslogik (Nutzer-Politik, kein
Gerätefakt) und wird daher aus den kumulativen Zählern mit HA-Bordmitteln
zusammengesetzt — das hält die Integration schlank und die Reset-Regel flexibel.

Empfehlung: ein **Wärmepumpenjahr** (Reset im Sommer, z. B. 1. Juli), damit jede
Heizsaison in *einem* Zeitraum liegt statt über den Jahreswechsel zerschnitten zu
werden. Am einfachsten über die HA-Helfer-UI (*Einstellungen → Geräte & Dienste →
Helfer*: zwei **Verbrauchszähler** ohne Zyklus + ein **Template**-Sensor) plus
eine Reset-Automatisierung. Als YAML:

```yaml
utility_meter:
  wp_waerme_wpjahr:
    source: sensor.boesch_wanda_energie_th_gesamt
    cycle: none          # kein Auto-Reset — Reset per Automation am 1. Juli
  wp_strom_wpjahr:
    source: sensor.boesch_wanda_energie_el_gesamt
    cycle: none

template:
  - sensor:
      - name: "WP Jahresarbeitszahl"
        state: >
          {% set el = states('sensor.wp_strom_wpjahr') | float(0) %}
          {% set th = states('sensor.wp_waerme_wpjahr') | float(0) %}
          {{ (th / el) | round(2) if el > 0.5 else 'unknown' }}
        state_class: measurement

automation:
  - alias: "WP-Jahr zurücksetzen (1. Juli)"
    triggers:
      - trigger: time
        at: "00:00:00"
    conditions:
      - "{{ now().month == 7 and now().day == 1 }}"
    actions:
      - action: utility_meter.calibrate
        target:
          entity_id: [sensor.wp_waerme_wpjahr, sensor.wp_strom_wpjahr]
        data:
          value: 0
```

Für striktes **Kalenderjahr** stattdessen an beiden `utility_meter` `cycle: yearly`
setzen und die Automation weglassen. Über die UI angelegte Helfer bekommen
entity_ids aus ihrem Namen (Umlaute → `ae/oe`→`a/o`) — die Referenzen im
Template-Sensor entsprechend anpassen.

## Architektur

- **`registers.py`** – zentrale Registertabelle; jede Zeile beschreibt eine
  Entity (Datentyp, Skalierung, Einheit, Grenzen, Enum-Mapping, Poll-Gruppe,
  Schreibbarkeit, Feature-Tag).
- **`modbus_client.py`** – ein serialisierter `AsyncModbusTcpClient` für beide
  Geräte (unterschieden per `device_id`), lesen und schreiben (FC 0x03 / 0x06).
- **`coordinator.py`** – ein Coordinator je Poll-Gruppe, Block-Reads, Encode der
  Schreibwerte (`value / scale`, int16-Zweierkomplement) plus sofortiger Refresh;
  dazu der Web-Coordinator und das optionale Ersetzen der Leistungswerte.
- **`web_client.py`** – schlanker Client fürs Webinterface (Kermi x-center):
  Login per Cookie, Lesen/Schreiben von Datenpunkten, Auto-Relogin.
- **`sensor` / `binary_sensor` / `number` / `select` / `switch` /
  `water_heater`** – erzeugen die Entities rein aus dem Registermodell.

## ⚠️ Datentyp-Kernbefund

Die Bösch-Modbusliste deklariert die WANDA-Register als `Float` mit Faktor 0,1 —
das ist **falsch**. Das Gerät liefert je **ein Register (16 Bit)**; ein `float32`
bräuchte zwei Register und scheitert mit `unpack requires a buffer of 4 bytes`.
Korrekt ist **`int16` + `scale 0.1`** (bei nie-negativen Größen mit Bereich
`uint16`). Diese Integration setzt das durchgängig um.

Zwei weitere per Verlauf verifizierte Abweichungen von der Doku:

- **Register 152** ist die **Laufzeit seit dem letzten Start** in Zehntelstunden
  (`uint16` × 0,1 → h; springt beim Abschalten auf 0), kein Statusflag — der
  Binärsensor „Verdichter läuft" wird daher aus der **elektrischen Leistung**
  (> 0) abgeleitet.
- **Heizkreispumpen-Laufzeit** (300/301) ist in **Minuten**, nicht Stunden.

## Bekannte Einschränkungen

- Getestet mit **WANDA 10 + Hydrobox**. Andere Bösch-Geräte auf derselben
  Plattform (Kermi x-center) funktionieren vermutlich teilweise, sind aber
  nicht verifiziert.
- **Modbus schneidet Leistungen auf 0,1 kW ab** (el. Leistung im Mittel
  ~3,5 % zu niedrig). Abhilfe: hochauflösende Leistung übers Webinterface.
- Hydrobox-Register **301** ist in der Bösch-Doku dreifach vergeben (Pumpe 2,
  ext. WEZ) – reale Belegung noch zu klären.
- **Außentemperatur:** die Doku nennt 275/276, je nach Anlage liegt sie auf
  einem AI-Eingang (z. B. AI8) – über die konfigurierbaren Fühlereingänge
  abbildbar.
- Übers Webinterface eingebunden ist nur **Heizkreis 1**; Heizmodus, Festwert
  und Kurven von HK2 fehlen noch. Die Web-API ist inoffiziell.
- Die Heiz- und Kühlkurve lassen sich nur als Ganzes schreiben. Die
  Integration liest sie vor jeder Änderung frisch, gleichzeitige Änderungen in
  der Web-Oberfläche können trotzdem kollidieren.

## Fehlerbehebung

- **„Verbindung fehlgeschlagen" im Setup:** IP prüfen, Modbus TCP muss am
  Wärmepumpenmanager aktiv sein (Port 502). Viele Modbus-Gateways erlauben
  nur wenige gleichzeitige Verbindungen – andere Modbus-Clients (z. B. eine
  alte `modbus:`-YAML-Konfiguration für dieselbe IP) abschalten.
- **Werte um Faktor 10 daneben oder Fühler zeigt Unsinn:** Fühlereingänge sind
  bewusst ungekappt; ein unbelegter Eingang zeigt einen offensichtlich
  falschen Wert. Den Eingang in den Optionen leeren.
- **„Erneut authentifizieren" erscheint:** Das Web-Passwort wurde geändert.
  Auf die Meldung klicken und das neue Passwort eingeben.
- **Web-Entities „nicht verfügbar":** Webinterface im Browser prüfen; Modbus-
  Entities laufen davon unabhängig weiter.
- **Diagnosedaten:** *Einstellungen → Geräte & Dienste → Bösch → ⋮ →
  Diagnose herunterladen*. Enthält Rohregister und Web-Datenpunkte, IP,
  Passwort und Seriennummern sind geschwärzt – gern an ein Issue anhängen.
- **Debug-Log:** in derselben Ansicht *Debug-Protokollierung aktivieren*,
  oder dauerhaft:

  ```yaml
  logger:
    logs:
      custom_components.boesch: debug
  ```

## Entfernen

1. *Einstellungen → Geräte & Dienste → Bösch → ⋮ → Löschen*. Geräte und
   Entities werden entfernt, die Historie bleibt in der Datenbank.
2. Bei Installation über HACS: *HACS → Bösch → ⋮ → Entfernen*, sonst den
   Ordner `<config>/custom_components/boesch/` löschen.
3. Home Assistant neu starten.

Selbst angelegte Helfer (z. B. `utility_meter` für die JAZ) und Automationen
bleiben bestehen und müssen bei Bedarf von Hand gelöscht werden.

## Credits

- Register-Mappings gegengeprüft mit
  [col-panic/homeassistant-boesch-heatpump-integration](https://github.com/col-panic/homeassistant-boesch-heatpump-integration)
  (andere Hardware, gleiche Steuerungsplattform).
- [Home Assistant Modbus-Integration](https://www.home-assistant.io/integrations/modbus/)
  als Referenz für Datentypen und Optionen.

## Lizenz

[MIT](LICENSE)
