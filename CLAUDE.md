# Bösch WANDA 10 + Hydrobox → Home Assistant

Kontext für Claude Code: Custom Integration `custom_components/boesch`
(Modbus TCP + optional Webinterface). Stand: 2026-11-03.

## Hardware & Netzwerk

| | |
|---|---|
| Wärmepumpe | Bösch WANDA 10 (Heizbösch / boesch.at), technisch ein Kermi-Gerät |
| Zusatzmodul | Hydrobox (RW10) |
| Gateway | Kermi x-center („Wärmepumpenmanager RW60“): Modbus TCP Port `502` + Webinterface Port `80` |
| IP | anlagenspezifisch, nicht im Repo (in der Integration kein Default; DHCP-Erkennung über Hostname `xcenter`) |
| Modbus-Adressen | WANDA `40`, Hydrobox `50`; Function Code `0x03` (Holding Register) für alle Datenpunkte |
| Doku | `Reference/2026-07-21_Modbusliste_WANDA+Hydrobox.xlsx` (von Bösch, Blätter WANDA + Hydrobox; `Reference/` ist gitignored) |

Code-Aufbau: siehe README, Abschnitt „Architektur“. Werkzeuge:
`scripts/scan_registers.py` (read-only Register-Scanner mit Snapshot-Diff),
`scripts/web_probe.py` (read-only Test des Web-Clients ohne HA).

## ⚠️ Kernbefund: Datentyp-Fehler in der Bösch-Doku

Die Modbusliste deklariert die WANDA-Register als **Datenpunkttyp `Float`**
mit **Faktor 0,1**. Das ist falsch: ein IEEE-754-Float belegt 2 Register, das
Gerät liefert aber nur **1 Register** (beim Lesen als `float32`: „Received 2
bytes, unpack error“). **Korrekt ist `int16` + Faktor 0,1** (Rohwert in
Zehntel). Unabhängig bestätigt durch
[col-panic/homeassistant-boesch-heatpump-integration](https://github.com/col-panic/homeassistant-boesch-heatpump-integration)
(HA-Default `int16`, `scale: 0.1`). Fehlerbericht an Bösch ist formuliert.

## Register-Entscheidungen (`registers.py`)

- **`uint16` statt `int16`** nur bei Werten, die nie negativ werden und den
  Bereich brauchen: WANDA 152 (Laufzeit), WANDA 301 (PV-Leistung), Hydrobox
  300/301 (Pumpenlaufzeiten).
- **`min_value`/`max_value` kappen** (`value < min → min`), sie filtern nicht.
  Deshalb nur, wo der Bereich laut Doku oder physikalisch feststeht: Enums auf
  ihre dokumentierten Bereiche, COP 0–20, Leistungen 0–100 kW, Temperaturen
  −50…150 °C.
- **Rohe Fühlereingänge (250–258) bewusst ohne min/max** — ein unbelegter
  Eingang würde sonst auf 150 °C gekappt und sähe wie ein echter Messwert aus.
  Sie sind opt-in (Options-Flow „Fühlereingänge“).
- **Rohwert 0 ist gültig** (z. B. „Status Heizkreis = 0“ = *Aus*), also nicht
  als „kein Wert“ behandeln (col-panic setzt `nan_value: 0`, vermutlich ein Bug).
- **COP ohne `device_class: power_factor`** (col-panic nutzt das) —
  power_factor ist semantisch ein Prozentwert.
- **WANDA 152 = Laufzeit seit letztem Start** (geklärt 2026-09-24): Zehntel-
  stunden, Reset beim Abschalten, max. ~6553 h — kein Gesamtzähler.
- Poll-Intervalle (Defaults): 15 s Live-Werte, 30 s Standard, 60 s Sollwerte,
  300 s Betriebsstunden.

## Vergleich mit col-panic-Integration

Andere Hardware (Mozart 13 AC RW60), daher andere Topologie — die
Register-Mappings validieren sich aber gegenseitig. **Identisch:** COP 100–103,
Leistungen 104–111, Status WP 200, TWE 100–104, Heizkreis 150/153/155/156.
**Abweichend:** bei ihm 50 = Speichermodul Heizen, 51 = Speichermodul TWE,
30 = Heizkreismodul (die Hydrobox fasst das in 50 zusammen); Außentemperatur
liest er aus 254/255, bei uns sind das Fühler-Rohwerte (T1/AI6) und die
Außentemperatur steht in 275/276 (verifiziert).

## Release-Ablauf

Nutzer-sichtbare Änderungen laufend in `CHANGELOG.md` unter `## [Unreleased]`
eintragen (Stil: kurze Stichpunkte für Nutzer, kein Entwickler-Kram). Beim
Release:

1. `## [Unreleased]` → `## [x.y.z] – <Titel>` umbenennen, neuen leeren
   `## [Unreleased]`-Abschnitt darüber anlegen.
2. `version` in `custom_components/boesch/manifest.json` setzen, Commit
   „Version x.y.z“.
3. Annotierter Tag `vx.y.z`, `main` + Tag pushen.
4. `gh release create vx.y.z --title "vx.y.z – <Titel>" --notes-file <Abschnitt>`
   (nur der Abschnitt der Version, ohne Überschrift).

## Offene Punkte

1. **Register 301 Hydrobox** ist in der Bösch-Doku *dreifach* vergeben
   (Heizkreispumpe 2, Ext. WEZ 1-1, Ext. WEZ 1-2). Vermutlich 302/303 —
   bei Bösch nachfragen.
2. **TWE-Leistung im Web**: Auflösung während einer TWE-Ladung messen
   (`scripts/web_probe.py --host <ip> --watch 600 --twe`).

## Webinterface (Kermi x-center)

Das Bösch-Webinterface ist ein **Kermi x-center** („Wärmepumpenmanager
RW60“, Firmware IFM 1.6.5.44), ausgewertet per HAR-Mitschnitt (`captures/`,
gitignored; Aufnahme mit `har-capture get <ip> --patterns network-device`).
Optional per Web-Passwort im Setup oder später unter Optionen → „Webinterface“
(gespeichert in den Optionen); Client in
`web_client.py`, read-only Test ohne HA: `scripts/web_probe.py --host <ip>`.

- Login `POST /api/Security/Login` → Cookie `XCenter`, manuell mitgeschickt
  (aiohttp verwirft Cookies von IP-Hosts). Session abgelaufen → HTML statt JSON.
- `Device/GetAllDevices`: Feld `Address` = Modbus-Adresse (40/50) → DeviceId.
- `DatapointConfigId`s sind Firmware-Konstanten (Kermi-Frontend:
  `wellknown-datapoints.js`), daher fest in `web_client.py`.
- Schreiben wie die Web-UI: `$type` (.NET-Typ) zuerst, `Single` als String.
- Die Heizkurve (`Curve2d`, 9 Stützpunkte −20…+20 °C, Feld `Info` unbekannt)
  wird nur als Ganzes geschrieben → vorher frisch lesen.

Eingebunden (nur was Modbus nicht hat): Heizmodus HK1 (Kurve/Festwert/Aus),
Festwert Heizen und Kühlen HK1, Heiz- und Kühlkurve HK1, Mischer-Öffnung HK1
(`HeatingCircuit_MixerPosition`; Mischer-Modus/-Konfig/-Laufzeit sind für
Benutzerlevel 10 gesperrt), Saison-Außentemperatur, Anwesenheit (`System_IsPresent`, schreibbar, am
Wärmepumpenmanager = DeviceId Null-GUID → eigenes Gerät `DeviceKey.MANAGER`).

Lesen immer mit `IgnoreErrors: true` (wie die Web-UI): sonst kippt ein einziger
gesperrter Datenpunkt die ganze Sammelabfrage („Lesen nicht erlaubt …“).
Werte ohne Betrieb (z. B. COP TWE) kommen als String `"NaN"` → None.

### ⚠️ Modbus schneidet Leistungen ab (2026-11-03 gemessen)

Die Leistungsregister 104–111 (Faktor 0,1 kW) sind **abgeschnitten, nicht
gerundet**. Das x-center liest dieselben Größen intern mit 0,01 kW (Register
2023 el. / 2028 thermisch, über das Modbus-TCP-Gateway **nicht** lesbar).
10 min Parallelmessung im Heizbetrieb (~1,1 kW el.): Modbus im Mittel
**−3,5 % el.** und −1,1 % thermisch gegenüber Web (passt zu 97–99 % der Punkte
zu Abschneiden). Folge: Stromzähler zu niedrig, JAZ um ~2–3 % geschönt.
Update-Rate Web: el. Leistung ändert sich im Mittel alle ~8 s.

Option „Hochauflösende Leistungswerte“ (`web_power`): der LIVE-Coordinator
ersetzt nach dem Modbus-Read die 8 Leistungs-Keys durch die Web-Werte
(`WEB_POWER` in `coordinator.py`), Rückfall auf Modbus pro Poll bei Web-Fehler.
Entity-IDs/Statistik bleiben. TWE-Auflösung noch offen (siehe Offene Punkte).

### Datenpunkt-Übersicht (Webinterface ↔ Modbus)

Alle Datenpunkte aus dem HAR-Mitschnitt (101) plus live gefundene. Spalten:
**Zugriff** R = nur lesen, RW = schreibbar; UL = nötiges Benutzerlevel zum
Schreiben, falls > 10 (Endkunde = 10). **Modbus** = Register (W = WANDA 40,
H = Hydrobox 50). **Angebunden** = woher die Integration den Wert holt;
„später“ = Kandidat für später, „–“ = bewusst nicht. **Notiz** für
nennenswerte Unterschiede zwischen Web und Modbus.

**WANDA**

| WellKnownName | Anzeige (Web) | Zugriff | Modbus | Angebunden | Notiz |
|---|---|---|---|---|---|
| `EcoODU_CombinedHeatpumpState` | Status Wärmepumpe | R | W 200 | Modbus | |
| `EcoODU_CurrentCOP` | Aktueller COP | R | W 100 | Modbus | Web: Kommazahl (intern Register 2121/2122 als Float), Modbus Faktor 0,1 |
| `EcoODU_CurrentCOPHeating` / `…TWE` / `…Cooling` | Aktueller COP Heizen/TWE/Kühlen | R | W 101–103 | Modbus | Web liefert `"NaN"` ohne Betrieb |
| `EcoODU_CurrentOutputCapacity` | Aktuelle Leistung | R | W 104 | Web (Haken), sonst Modbus | **Web 0,01 kW** (intern Register 2028), Modbus 0,1 kW **abgeschnitten**: −1,1 % gemessen |
| `EcoODU_CurrentOutputCapacityHeating` / `…Twe` / `…Cooling` | Aktuelle Leistung Heizen/TWE/Kühlen | R | W 105–107 | Web (Haken), sonst Modbus | wie oben; TWE-Auflösung noch nicht gemessen |
| `EcoODU_CurrentPowerInverter` | Akt. elektr. Leistung | R | W 108 | Web (Haken), sonst Modbus | **Web 0,01 kW** (intern Register 2023, über Modbus TCP nicht lesbar), Modbus abgeschnitten: **−3,5 %** gemessen; Web ändert sich im Mittel alle ~8 s |
| `EcoODU_CurrentPowerInverterHeating` / `…Twe` / `…Cooling` | Akt. elektr. Leistung Heizen/TWE/Kühlen | R | W 109–111 | Web (Haken), sonst Modbus | wie oben; TWE-Auflösung noch nicht gemessen |
| `EcoODU_CurrentPowerInverterPV` / `…HeatingPV` / `…TwePV` / `…CoolingPV` | Akt. elektr. Leistung (…) PV | R | – | später | PV-Anteil der el. Leistung, nur Web |
| `EcoODU_PvIsActive` | Status PV Modulation | R | W 300 | Modbus | |
| `EcoODU_RequestedPowerHeating` / `…Twe` / `…Cooling` | Leistungsanforderung Heizen/TWE/Kühlen | R | – | später | nur Web |

**Hydrobox**

| WellKnownName | Anzeige (Web) | Zugriff | Modbus | Angebunden | Notiz |
|---|---|---|---|---|---|
| (ohne) | Status Heizkreis HK1 | R | H 150 | Modbus | |
| `HeatingCircuit_TemperatureActualValue` | Isttemperatur Heizkreis HK1 | R | H 151 | Modbus | |
| `HeatingCircuit_TemperatureSetpoint` | Solltemperatur Heizkreis HK1 | RW (UL40) | H 152 | Modbus (lesen) | Schreiben nur Installateur |
| `HeatingCircuit_OperationMode` | Betriebsart HK1 | RW | H 154 | Modbus | |
| `HeatingCircuit_EnergyMode` | Energiemodus HK1 | RW | H 155 | Modbus | |
| `HeatingCircuit_TemperatureAdjust` | Parallelverschiebung Kurve HK1 | RW | H 156 | Modbus | |
| `HeatingCircuit_ManualSaison` | Manuelle Saisonauswahl HK1 | RW | H 157 | Modbus | |
| `HeatingCircuit_SummerModeUpperThreshold` / `…LowerThreshold` | Sommer-/Winterbetrieb HK1 | RW | H 158 / 159 | Modbus | |
| `HeatingCircuit_ChangeOverUpperThreshold` / `…LowerThreshold` | Kühlbetrieb Ein/Aus HK1 | RW | H 160 / 161 | Modbus | |
| `HeatingCircuit_SummerMode` | Sommerbetrieb HK1 | R | H 162 | Modbus | |
| `HeatingCircuit_ChangeOver` | Kühlbetrieb HK1 | R | H 163 | Modbus | |
| `HeatingCircuit2_EnergyMode` | Energiemodus HK2 | RW | H 180 | Modbus (HK2 opt-in) | |
| `HeatingCircuit_HeatingWaterMode` | Heizmodus HK1 | RW | – | **Web** | Kurve / Festwert / Aus |
| `HeatingCircuit_FixedSetpointHeating` | Konstanter Sollwert Heizkreis HK1 | RW | – | **Web** | |
| `HeatingCircuit_FixedSetpointCooling` | Konstanter Sollwert Kühlkreis HK1 | RW | – | **Web** | |
| `HeatingCircuit_HeatingCurve` | Stützpunkte Heizkurve | RW | – | **Web** | `Curve2d`, 9 Punkte −20…+20 °C, nur als Ganzes schreibbar |
| `HeatingCircuit_CoolingCurve` | Stützpunkte Kühlkurve | RW | – | **Web** | nicht im Mitschnitt, live gelesen; `Curve2d`, 5 Punkte bei 15/25/30/35/40 °C |
| `HeatingCircuit_MixerPosition` | Mischer-Öffnung HK1 | R | – | **Web** | nicht im Mitschnitt, live gelesen; `…MixerMode` / `…ConfigMixingCircuit` / `…RuntimeMixer` für UL10 gesperrt |
| `HeatingCircuit_Offset{Eco,Normal,Comfort,Custom}` (+ `…Cooling`) | Offsets HK1 (8×) | RW | – | später | −10…+10 K |
| `HeatingCircuit_HeatExchangeType` | Wärmeübertrager HK1 | RW | – | später | |
| `HeatingCircuit_Name` | Heizkreisname HK1 | RW | – | – | |
| `HeatingCircuit_OffsetTroja` / `…TrojaEnabled` | Externe Parallelverschiebung HK1 | RW (UL30) | – | – | Installateur |
| `HeatingCircuit_RoomPanelDeviceId` | Zuordnung RBG HK1 | RW (UL30) | – | – | Installateur |
| `HeatingCircuit_OperatingHoursPump` | Heizkreispumpe 1 Laufzeit | R | H 300 | Modbus | |
| (ohne) | Ext. WEZ 1-1 / 1-2 / 1-3 Laufzeit | R | H 301? | – | Bösch-Doku vergibt 301 dreifach (siehe Offene Punkte) |
| `EcoIDU_HeatingTemperatureActual` | Isttemperatur Heizspeicher | R | H 1 | Modbus | |
| `EcoIDU_CoolingTemperatureActual` | Isttemperatur Kühlspeicher | R | H 50 | Modbus | |
| `EcoIDU_TweTemperatureActual` | Isttemperatur TWE | R | H 100 | Modbus | |
| `EcoIDU_TweSetpoint` | Solltemperatur TWE | R | H 101 | Modbus | |
| `EcoIDU_TemperatureSetpointTwe` | Konstanter Sollwert TWE | RW | H 102 | Modbus (`water_heater`) | |
| `EcoIDU_OneTimeTwe` | Einmalladung TWE | RW | H 103 | Modbus (`water_heater`) | |
| `EcoIDU_OneTimeTweSetpoint` | Sollwert Einmalladung TWE | RW | H 104 | Modbus | |
| `EcoIDU_TweEnableUser` | TWE aktivieren | RW | – | später | |
| `EcoIDU_ErrorSetpointTwe` | Störsollwert TWE | RW | – | später | |
| `EcoIDU_RoomPanelDeviceIdTwe` | Zuordnung RBG TWE | RW (UL30) | – | – | Installateur |
| `EcoIDU_Tsensor1`…`4`, `…5` (T1), `…8`, `EcoIDU_TwSensor` | AI1–AI4, T1, AI8, Tw (IBH) | R | H 250–254, 257, 258 | Modbus (opt-in) | |
| `EcoIDU_StateDigitalInput1`…`7` | DI1–DI7 Status | R | – | später | Digitaleingänge, nur Web |
| `LuftTemperatur` | Außentemperatur | R | H 275 | Modbus | |
| `Aussentemperatur_gemittelt` | Gemittelte Außentemperatur | R | H 276 | Modbus | |
| `HP_Aussentemperatur_Saison` | Saison-Außentemperatur | R | – | **Web** | Grundlage der Saisonumschaltung |
| `DeviceType`, `Serialnumber` | Gerätetyp, Seriennummer | R | – | – | Geräteinfo |

**Wärmepumpenmanager (x-center, DeviceId Null-GUID)**

| WellKnownName | Anzeige (Web) | Zugriff | Modbus | Angebunden | Notiz |
|---|---|---|---|---|---|
| `System_IsPresent` | Anwesenheitsstatus | RW | – | **Web** (`switch`) | versteckt unter System-Einstellungen → Interne Statuswerte |
| `DH_SGReady1` / `DH_SGReady2` / `DH_SmartGridState` | EVU / SGReady2 / SmartGrid State | R | – | später | SG-Ready-Status; Invertierung (UL30) nicht |
| `S0_1_W` | S0_1 W | R | – | später | S0-Zählereingang in W (falls belegt) |
| `RemoteControlConnected` / `RemoteControlEnabled` | Verbunden mit Server / Serververbindung erlauben | R / RW | – | – | Kermi-Cloud |
| `DH_Led1` / `DH_Led2` / `DH_Output1` / `DH_Output2` / `DH_SendErrorToOutputs` | LEDs, Ausgänge | RW (UL20/30) | – | – | Installateur |
| `ReferenceId`, `SystemSerialNo` | Referenz-Id, Seriennummer | RW (UL20/40) | – | – | |

Außerdem für später, aber nicht im Mitschnitt: HK2-Pendants von Heizmodus/Festwert/Heizkurve
(IDs in `wellknown-datapoints.js`), Szenen (z. B. „Trinkwassererwärmung“
ausführen/zurücksetzen), aktuelle Alarme.

## Quellen

- Bösch Modbusliste: `Reference/2026-07-21_Modbusliste_WANDA+Hydrobox.xlsx`
- [col-panic/homeassistant-boesch-heatpump-integration](https://github.com/col-panic/homeassistant-boesch-heatpump-integration)
- [jr42/py-kermi-xcenter](https://github.com/jr42/py-kermi-xcenter) (Kermi-Web-API, `docs/http_specification.md`)
- [solentlabs/har-capture](https://github.com/solentlabs/har-capture) (HAR-Mitschnitt mit Bereinigung)
