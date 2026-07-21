# Bösch WANDA 10 + Hydrobox — Home Assistant Integration

Eine eigenständige, per UI konfigurierbare Home-Assistant-Integration für die
Wärmepumpe **Bösch WANDA 10** samt **Hydrobox**, angebunden über **Modbus TCP**.
Sie kapselt die gesamte Modbus-Kommunikation mit beiden Geräten in einer
einzigen TCP-Verbindung und einem zentralen, datengetriebenen Registermodell.

> Ersetzt die frühere YAML-Lösung (`boesch.yaml` + `boesch-templates.yaml`,
> jetzt im Ordner `Reference/`).

## Status

**Phase 2 (in Arbeit) – Schreibzugriff.** Read-only-Register erscheinen als
`sensor`/`binary_sensor` (inkl. Klartext für Status-Enums). Die 24 als **R/W**
dokumentierten Register sind jetzt beschreibbar:

- **`number`** (15) – Sollwerte: Parallelverschiebung, Sommer/Winter/Kühl-
  Schwellen, PV-Leistung/-Solltemperaturen, TWE-Sollwerte
- **`select`** (8) – Modi: HK1/HK2 Betriebsart · Energiemodus · Saison, WEZ
  Betriebsart Heizen/TWE
- **`water_heater`** (1) – Trinkwassererwärmung: Ist-Temperatur (100),
  Zieltemperatur (konst. Sollwert 102), Betriebsmodus Normal/Einmalladung (103)
- **`number`** – zusätzlich: TWE-Sollwert Einmalladung (104)

Geschrieben wird per FC 0x06; nach jedem Write folgt ein sofortiger Refresh, der
den bestätigten Gerätewert zurückliest.

**Noch offen:** optionale dünne `climate`-Hülle für die Heizkreise (Schritt 3).
Die Heizkreise haben bewusst **keine** `climate`-Entity mit Zieltemperatur — ihr
Solltemperatur-Register ist read-only (von der Heizkurve berechnet); gesteuert
wird über Energiemodus + Parallelverschiebung.

## Installation (HACS)

1. HACS → Integrationen → ⋮ → *Benutzerdefinierte Repositories*
2. Dieses Repository als Kategorie **Integration** hinzufügen.
3. „Bösch WANDA" installieren, Home Assistant neu starten.
4. *Einstellungen → Geräte & Dienste → Integration hinzufügen → Bösch WANDA*.

Alternativ den Ordner `custom_components/boesch/` manuell in die HA-Konfig
kopieren.

## Konfiguration

**Setup:** IP (Default `192.168.0.202`), Port (`502`), Modbus-Adresse WANDA
(`40`) und Hydrobox (`50`). Vor dem Anlegen wird die Verbindung getestet.

**Optionen** (über *Konfigurieren* → Menü, nachträglich änderbar):

*Allgemein:*

| Option | Default | Wirkung |
|---|---|---|
| Zweiter Heizkreis vorhanden | aus | Blendet die HK2-Entities ein/aus |
| Externer Wärmeerzeuger vorhanden | aus | Blendet die WEZ-Entities ein/aus |
| Intervall Live-Werte | 15 s | Vorlauf/Rücklauf, COP, Leistungen, WP-Status |
| Intervall Standard | 30 s | Temperaturen, Speicher, Außentemperatur |
| Intervall Sollwerte | 60 s | Sollwerte, Betriebsarten |
| Intervall Betriebsstunden | 300 s | Zählerstände |

HK2 und WEZ sind **Opt-in** (Basisanlage: 1 Heizkreis, kein externer WEZ) —
bei Bedarf hier aktivieren.

*Fühlereingänge (AI1–AI8):* Die frei belegbaren Analogeingänge der Hydrobox
sind anlagenspezifisch verdrahtet und daher **standardmäßig ausgeblendet**. Pro
Eingang einen Namen eingeben aktiviert und benennt ihn; leer lassen blendet ihn
aus. Beispiel: `AI1 → Heizspeicher-Temperatur`, `AI8 → Außentemperatur`.

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
