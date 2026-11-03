# Changelog

Ältere Versionen (bis v0.5.0): siehe
[GitHub Releases](https://github.com/makerwolf/homeassistant-boesch/releases).

## [Unreleased]

<!-- Geplant als v0.6.0 – Hochauflösende Leistung, Mischer & Anwesenheit.
     Beim Release: Überschrift auf die Version umbenennen und diesen Abschnitt
     als Release Notes verwenden (siehe CLAUDE.md, "Release-Ablauf"). -->

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
