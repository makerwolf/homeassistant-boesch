# Bösch WANDA Wärmepumpe – Home Assistant Integration (Modbus TCP + Webinterface)

[![marketplace](https://img.shields.io/badge/Home%20Assistant-Marketplace-41BDF5.svg)](https://hacs.xyz/docs/marketplace/)
[![version](https://img.shields.io/github/v/release/makerwolf/homeassistant-boesch)](https://github.com/makerwolf/homeassistant-boesch/releases)
![license](https://img.shields.io/badge/license-MIT-green.svg)

Eine eigenständige, per UI konfigurierbare Home-Assistant-Integration für die
Luft-Wasser-Wärmepumpe **Bösch WANDA 10** mit **Hydrobox** von
**[Bösch](https://www.boesch.at/)** (Heizbösch, Österreich), angebunden über
**Modbus TCP** und optional über das Webinterface (**Kermi x-center**,
Wärmepumpenmanager RW60). Installierbar über HACS bzw. den Marketplace. Sie
kapselt die gesamte Modbus-Kommunikation in einer einzigen TCP-Verbindung und
einem zentralen, datengetriebenen Registermodell.

> **English:** Home Assistant custom integration (HACS) for the **Boesch WANDA 10**
> air-to-water heat pump with **Hydrobox** (Bösch / Heizbösch, Austria) via
> **Modbus TCP** and the **Kermi x-center** web interface: temperatures, COP,
> power and energy meters for the Energy Dashboard, heating curve, domestic hot
> water (`water_heater`) and operating modes. UI in German and English.

> **Unterstützte Geräte:** ausschließlich Bösch **WANDA 10** mit **Hydrobox**.
> Andere Wärmepumpen werden nicht unterstützt, und das ist auch nicht geplant.

> ⚠️ Inoffizielles Community-Projekt, **nicht** mit der Bösch Heizsysteme GmbH
> verbunden oder von ihr unterstützt. Nutzung auf eigene Verantwortung.
> Mit KI-Unterstützung entwickelt, siehe [Entstehung mit KI](#entstehung-mit-ki).

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
  Stützpunkte von Heiz- und Kühlkurve, Mischer-Öffnung, Saison-Außentemperatur,
  Anwesenheitsstatus und Softwareupdate-Status – optional
  auch hochauflösende Leistungswerte (0,01 statt 0,1 kW) für genauere
  Energiezähler und eine **feine Heizkurve** in 0,1-K-Schritten, die Home
  Assistant rechnet.
- **UI-Konfiguration**: Verbindungstest im Setup, Options-Menü für Heizkreis 2,
  externen Wärmeerzeuger, Poll-Intervalle und frei belegbare Fühlereingänge.
- **Effizientes Polling**: ein `DataUpdateCoordinator` je Intervall-Klasse
  (15/30/60/300 s), zusammenhängende Register werden als Block gelesen.
- **Energie & Effizienz**: aus den Leistungen berechnete kWh-Zähler (Strom &
  Wärmemenge, gesamt + je Modus) fürs Energy Dashboard, plus laufende
  Jahresarbeitszahl (JAZ/SCOP).

## Installation (Marketplace)

Voraussetzung: Home Assistant **2026.9** oder neuer. Ab **2026.11** über den
eingebauten Marketplace, bei älteren Versionen über HACS (gleiche Schritte).

1. *Einstellungen → Marketplace* öffnen und nach „Bösch" suchen.
   Solange die Integration noch nicht im Katalog steht: ⋮ →
   *Benutzerdefinierte Repositories* →
   `https://github.com/makerwolf/homeassistant-boesch` als Kategorie
   **Integration** hinzufügen.
2. „Bösch" installieren, Home Assistant neu starten.
3. *Einstellungen → Geräte & Dienste → Integration hinzufügen → Bösch*.

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
| `number.boesch_hb_hk1_festwert` | Konstanter Vorlauf-Sollwert Heizen (0–100 °C, 0,1 K) |
| `number.boesch_hb_hk1_festwert_kuehlen` | Konstanter Sollwert Kühlen (5–30 °C, 0,1 K) |
| `number.boesch_hb_hk1_heizkurve_m20` … `_p20` | Vorlauf-Sollwert bei −20 … +20 °C Außentemperatur (9 Stützpunkte, 0–65 °C, ganze Grad) |
| `number.boesch_hb_hk1_kuehlkurve_p15` … `_p40` | Kühl-Vorlauf-Sollwert bei 15 / 25 / 30 / 35 / 40 °C Außentemperatur (5 Stützpunkte, 5–30 °C, ganze Grad) |
| `sensor.boesch_hb_hk1_mischer` | Mischer-Öffnung HK1 (%) |
| `sensor.boesch_hb_saison_aussentemperatur` | Außentemperatur, nach der die Saisonumschaltung (Sommer/Winter/Kühlen) schaltet |
| `switch.boesch_wpm_anwesenheit` | Anwesenheitsstatus des Wärmepumpenmanagers (an = anwesend) |
| `sensor.boesch_wpm_update_status` | Softwareupdate-Status (Aktuell / Neue Version verfügbar / Wird heruntergeladen / …), Diagnose |
| `sensor.boesch_wpm_update_fortschritt` | Download-Fortschritt eines Updates (%), Diagnose |
| `sensor.boesch_wpm_update_info` | Infotext während eines Updates, Diagnose (standardmäßig deaktiviert) |
| `sensor.boesch_wpm_firmware` / `_wanda_firmware` / `_hb_firmware` | Firmware-Version von Wärmepumpenmanager, WANDA und Hydrobox, Diagnose – der Verlauf zeigt, wann ein Update kam |

Die Update-Werte sind nur lesend: ein Update startet die Integration nie.
Achtung, die Web-Oberfläche startet es beim Öffnen von *System-Einstellungen →
Update* von selbst, sobald eine neue Version verfügbar ist.

**Hochauflösende Leistungswerte** (Haken unter *Konfigurieren → Webinterface*):
Modbus liefert die Leistungen nur in 0,1-kW-Schritten und **schneidet ab**
(gemessen: el. Leistung im Mittel ~3,5 % zu niedrig). Mit dem Haken werden die
8 bestehenden Leistungssensoren (`sensor.boesch_wanda_leistung*`,
`sensor.boesch_wanda_el_leistung*`) stattdessen aus dem Webinterface mit
0,01 kW gefüllt – Entity-IDs und Verlauf bleiben, Stromverbrauch und JAZ
werden genauer. Ist das Webinterface kurz nicht erreichbar, gelten für diesen
Poll die Modbus-Werte. Beim Einschalten springen die Werte daher um einige
Prozent nach oben.

**Feine Heizkurve** (Haken unter *Konfigurieren → Webinterface*): Stützpunkte
und Parallelverschiebung der Bösch-Kurve kennen nur ganze Grad, bei einer
Fußbodenheizung ist 1 K Vorlauf viel. Mit dem Haken rechnet Home Assistant die
Kurve selbst in 0,1-K-Schritten und schreibt das Ergebnis jede Minute (gefiltert)
als Festwert HK1; der Heizmodus steht dabei auf „Festwert“.

| Entity | Bedeutung |
|---|---|
| `switch.boesch_hb_hk1_feinkurve_aktiv` | An: Festwert = aktueller HK1-Soll, dann Heizmodus „Festwert“ (kein Sprung). Aus: zurück auf „Kurve“ |
| `number.boesch_hb_hk1_feinkurve_m20` … `_p20` | 9 Stützpunkte (0,1 K). Beim ersten Einschalten = Bösch-Kurve + Parallelverschiebung |
| `number.boesch_hb_hk1_fein_parallel` | Feine Parallelverschiebung (−5…+5 K), gespeichert |
| `number.boesch_hb_hk1_zuschlag` | Zuschlag für Automationen (−5…+5 K), läuft durch die Rampe, nach Neustart 0 |
| `number.boesch_hb_hk1_sofort_anhebung` | Sofort-Anhebung (0…12 K, z. B. Anlaufhilfe nach Warmwasser): wird sofort geschrieben, nach Neustart 0 |
| `sensor.boesch_hb_hk1_fein_festwert` | Berechneter Festwert; Attribute: Basiskurve, Ziel vor Rampe, zuletzt geschrieben, Grund fürs Halten, HK1-/Puffer-Soll |

Rechenweg: Kurve über die **gemittelte Außentemperatur** interpolieren (wie das
Gerät selbst), + feine Parallelverschiebung + Zuschlag, auf 20–40 °C begrenzen.
Eine Rampe fährt das Ziel langsam an (senken 0,1 K, heben 0,2 K je 10 min), weil
der Puffer-Soll dem HK1-Soll folgt. Geschrieben wird frühestens alle 10 min und
nur bei ≥ 0,1 K Unterschied. Die Sofort-Anhebung kommt danach dazu (bis 45 °C)
und geht an Rampe und Filter vorbei. Grenzen, Rampe und Schreibabstand stehen
unter *Konfigurieren → Feine Heizkurve*.

Gehalten wird (nichts geschrieben, Rampe pausiert) bei Warmwasser und Abtauen
(außer Sofort-Anhebung), ohne Außentemperatur oder Webinterface. Stellt jemand
am Gerät den Heizmodus um, schaltet sich die Steuerung ab, ohne zurückzuschalten.
Genauso, wenn der Festwert von außen geändert wird – im Webinterface, über
`number.boesch_hb_hk1_festwert` oder von einer zweiten
Home-Assistant-Instanz mit aktiver feiner Kurve: Der Heizmodus bleibt dann auf
„Festwert“, es steuert nur noch der andere. Die feine Kurve also immer nur in
einer Instanz einschalten. In beiden Fällen erscheint ein Hinweis unter
*Einstellungen → Reparaturen* (das Gerät heizt dann mit festem Wert ohne
Außentemperatur-Führung); er verschwindet, sobald die feine Kurve wieder
eingeschaltet wird.
**Fällt Home Assistant länger aus**, heizt das Gerät mit dem zuletzt
geschriebenen Festwert weiter. Rückweg ohne HA: im Bösch-Webinterface den
Heizmodus HK1 auf „Kurve“ stellen; das Gerät regelt dann wieder nach seiner
eigenen Kurve. HA erkennt die Umstellung beim nächsten Start und lässt die
feine Kurve aus.
Beim Beenden von Home Assistant wird der Festwert ohne Zuschlag und
Sofort-Anhebung geschrieben, damit keine Anhebung stehen bleibt. Entladen der
Integration oder Abschalten der Option stellt den Heizmodus zurück auf „Kurve“.
**Die Parallelverschiebung am Gerät (`number.boesch_hb_hk1_parallel`) wirkt
nicht, solange die feine Heizkurve aktiv ist.** Im Festwert-Modus übernimmt das
Gerät den Festwert unverändert als HK1-Soll (und Heizspeicher-Soll). Stattdessen
die feine Parallelverschiebung oder den Zuschlag verwenden.

#### Dashboard-Karte „Heizkurve“

Die Integration bringt eine Karte mit, die eine Heizkurve als Diagramm zeigt;
die Stützpunkte lassen sich mit der Maus/dem Finger ziehen (oder per Pfeiltasten).
Eine Dashboard-Ressource ist nicht nötig – nach dem Einrichten der Integration
einmal den Browser neu laden, dann steht sie unter *Karte hinzufügen →
Heizkurve*. Die Vorbelegung nimmt die feine Heizkurve (sonst die Bösch-Kurve)
und die gemittelte Außentemperatur als Betriebspunkt.

```yaml
type: custom:heizkurve-card
title: Feine Heizkurve
outdoor_entity: sensor.boesch_hb_aussentemperatur_gemittelt
flow_entity: sensor.boesch_hb_hk1_ist   # optional: Ist-Vorlauf als Punkt
points:
  - { x: -20, entity: number.boesch_hb_hk1_feinkurve_m20 }
  - { x: -15, entity: number.boesch_hb_hk1_feinkurve_m15 }
  # … bis
  - { x: 20, entity: number.boesch_hb_hk1_feinkurve_p20 }
```

Weitere Optionen: `y_min`, `y_max`, `step` (Schrittweite beim Ziehen, sonst die
der Entity). Die Karte funktioniert mit beliebigen `number`-Entities.

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
Strompreis anheben (mit feiner Heizkurve stattdessen `number.boesch_hb_hk1_zuschlag`),
Benachrichtigung bei `binary_sensor.boesch_wanda_alarm_bs`.

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
- **`fine_curve.py`** – feine Heizkurve: Interpolation, Rampe, Schreibfilter
  und ein eigener Coordinator (60 s), Zustand im HA-Store.
- **`card.py` + `frontend/heizkurve-card.js`** – Lovelace-Karte, beim Setup als
  statischer Pfad bereitgestellt und als Frontend-Modul geladen.
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

- Nur für **WANDA 10 + Hydrobox** entwickelt und getestet. Andere Wärmepumpen,
  auch andere Bösch- oder Kermi-Geräte, werden nicht unterstützt.
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
2. Bei Installation über den Marketplace (oder HACS): *Marketplace → Bösch →
   ⋮ → Entfernen*, sonst den Ordner `<config>/custom_components/boesch/`
   löschen.
3. Home Assistant neu starten.

Selbst angelegte Helfer (z. B. `utility_meter` für die JAZ) und Automationen
bleiben bestehen und müssen bei Bedarf von Hand gelöscht werden.

## Entstehung mit KI

Diese Integration ist mit **KI-Unterstützung** entstanden: Ein Großteil des
Codes, der Tests und der Doku wurde mit [Claude Code](https://claude.com/claude-code)
(Anthropic) geschrieben, unter meiner Anleitung und auf Grundlage meiner
Messungen.

Von mir kommen die Anforderungen, die Entscheidungen, das Lesen des Codes und
das Testen an der eigenen WANDA 10 mit Hydrobox. Jedes Register und jeder Web-Datenpunkt wurde
am echten Gerät geprüft, Befunde wie der Datentyp-Fehler in der Bösch-Doku oder
die abgeschnittenen Leistungswerte stammen aus eigenen Messungen. Automatische
Tests (> 95 % Abdeckung) und `mypy --strict` laufen bei jeder Änderung in CI.

Ehrlich gesagt: Ohne KI gäbe es dieses Repo nicht in diesem Umfang, Detailgrad
und dieser Code-Qualität. Allein hätte ich höchstens die Grundfunktionen
geschafft, und die erst nach dem Winter. Fehler sind trotzdem möglich, es
gibt keine Garantie (siehe Hinweis oben). Fehler bitte als
[Issue](https://github.com/makerwolf/homeassistant-boesch/issues) melden.

## Credits

- Register-Mappings gegengeprüft mit
  [col-panic/homeassistant-boesch-heatpump-integration](https://github.com/col-panic/homeassistant-boesch-heatpump-integration)
  (andere Hardware, gleiche Steuerungsplattform).
- [Home Assistant Modbus-Integration](https://www.home-assistant.io/integrations/modbus/)
  als Referenz für Datentypen und Optionen.

## Lizenz

[MIT](LICENSE)
