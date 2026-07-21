# Bösch WANDA 10 + Hydrobox — Home Assistant Integration

Eine eigenständige, per UI konfigurierbare Home-Assistant-Integration für die
Wärmepumpe **Bösch WANDA 10** samt **Hydrobox**, angebunden über **Modbus TCP**.
Sie kapselt die gesamte Modbus-Kommunikation mit beiden Geräten in einer
einzigen TCP-Verbindung und einem zentralen, datengetriebenen Registermodell.

> Ersetzt die frühere YAML-Lösung (`boesch.yaml` + `boesch-templates.yaml`,
> jetzt im Ordner `Reference/`).

## Status

**Phase 1 – read-only.** Alle 77 Register werden als `sensor`- bzw.
`binary_sensor`-Entities bereitgestellt, inkl. Klartext für Status-/Enum-Register
(ersetzt die 16 Template-Sensoren). Die als **R/W** dokumentierten Register sind
im Registermodell bereits mit `writable=True` markiert, werden aber noch **nicht**
beschreibbar ausgespielt. Der Schreibpfad (`number`/`select`/`switch`/`climate`)
folgt in einer späteren Phase — dann nur „Plattform aktivieren", kein Umbau.

## Installation (HACS)

1. HACS → Integrationen → ⋮ → *Benutzerdefinierte Repositories*
2. Dieses Repository als Kategorie **Integration** hinzufügen.
3. „Bösch WANDA" installieren, Home Assistant neu starten.
4. *Einstellungen → Geräte & Dienste → Integration hinzufügen → Bösch WANDA*.

Alternativ den Ordner `custom_components/boesch_wanda/` manuell in die HA-Konfig
kopieren.

## Konfiguration

**Setup:** IP (Default `192.168.0.202`), Port (`502`), Modbus-Adresse WANDA
(`40`) und Hydrobox (`50`). Vor dem Anlegen wird die Verbindung getestet.

**Optionen** (nachträglich änderbar):

| Option | Default | Wirkung |
|---|---|---|
| Heizkreis 2 vorhanden | ein | Blendet die HK2-Entities ein/aus |
| Externer Wärmeerzeuger vorhanden | ein | Blendet die WEZ-Entities ein/aus |
| Intervall Live-Werte | 15 s | Vorlauf/Rücklauf, COP, Leistungen, WP-Status |
| Intervall Standard | 30 s | Temperaturen, Speicher, Außentemperatur |
| Intervall Sollwerte | 60 s | Sollwerte, Betriebsarten, Fühler-Rohwerte |
| Intervall Betriebsstunden | 300 s | Zählerstände |

## Architektur

- **`registers.py`** – zentrale Registertabelle. Jede Zeile = eine Entity.
  Enthält Datentyp, Skalierung, Einheit, Kappungsgrenzen, Enum-Mapping,
  Poll-Gruppe, `writable`-Flag und Feature-Tag (HK2/WEZ).
- **`modbus_client.py`** – ein serialisierter `AsyncModbusTcpClient` für beide
  Geräte (unterschieden per `device_id`).
- **`coordinator.py`** – ein `DataUpdateCoordinator` je Poll-Gruppe. Liest
  zusammenhängende Registerbereiche als **Block** (weniger Roundtrips als 77
  Einzel-Reads).
- **`sensor.py` / `binary_sensor.py`** – erzeugen die Entities rein aus dem
  Registermodell. Enum-Register erscheinen als Klartext-Sensoren.

Zwei HA-Geräte im Device-Registry: **Bösch WANDA** und **Bösch Hydrobox**.
Die `unique_id`s (`boesch_wp_*` / `boesch_hb_*`) sind aus der YAML-Lösung
übernommen, damit Entity-IDs und Dashboards erhalten bleiben.

## ⚠️ Datentyp-Kernbefund

Die Bösch-Modbusliste deklariert die WANDA-Register als `Float` mit Faktor 0,1 —
das ist **falsch**. Das Gerät liefert je **1 Register (16 Bit)**; ein `float32`
bräuchte 2 Register und scheitert mit `unpack requires a buffer of 4 bytes`.
Korrekt ist **`int16` + `scale 0.1`** (bei nie-negativen Größen mit Bereich
`uint16`). Diese Integration setzt das durchgängig um.

## Offene Punkte

- Betriebsstunden Verdichter (WANDA 152): `uint16 × 0.1` deckt nur ~6553 h ab.
- Hydrobox-Register 301 ist in der Bösch-Doku dreifach vergeben.
- Außentemperatur: unsere Liste sagt 275/276, col-panic liest 254/255. Beide
  Register sind als Entities vorhanden.

## Quellen

- Bösch-Modbusliste (siehe `Reference/`)
- [HA Modbus Integration](https://www.home-assistant.io/integrations/modbus/)
- [col-panic/homeassistant-boesch-heatpump-integration](https://github.com/col-panic/homeassistant-boesch-heatpump-integration)

## Lizenz

MIT
