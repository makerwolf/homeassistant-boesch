# Bösch WANDA 10 + Hydrobox → Home Assistant (Modbus TCP)

Kontext-Übergabe für Claude Code. Stand: 2026-07-21.

## Hardware & Netzwerk

| | |
|---|---|
| Wärmepumpe | Bösch WANDA 10 (Heizbösch / boesch.at) |
| Zusatzmodul | Hydrobox |
| IP | `192.168.0.18` (diese Anlage, Stand 2026-11 — in der Integration kein Default), Modbus TCP Port `502` |
| WANDA | `device_address: 40` |
| Hydrobox | `device_address: 50` |
| Function Code | `0x03` (holding register) für alle Datenpunkte |
| Doku | `2026-07-21_Modbusliste_WANDA+Hydrobox.xlsx` (von Bösch, 2 Blätter: WANDA, Hydrobox) |

Bestehende HA-Config: `modbus.yaml` enthält bereits einen Hub `VM-3P75CT`
(Stromzähler, `type: udp`, 192.168.0.7). Der bleibt unangetastet.

## Dateien

| Datei | Inhalt |
|---|---|
| `boesch.yaml` | 1 Modbus-TCP-Hub, 77 Sensoren (23× WANDA, 54× Hydrobox) |
| `boesch-templates.yaml` | 16 Klartext-Status-Sensoren + 6 Binary-Sensors |

Einbindung:

```yaml
# modbus.yaml – am Ende als weiteres Listenelement
- name: "VM-3P75CT"
  ...
- !include boesch.yaml

# configuration.yaml
template: !include boesch-templates.yaml
```

`boesch.yaml` ist ein einzelnes Mapping (kein `-` am Anfang), damit
`- !include boesch.yaml` es als Listenelement einhängen kann. WANDA und
Hydrobox teilen sich eine TCP-Verbindung, unterschieden über `device_address`.

## ⚠️ Kernbefund: Datentyp-Fehler in der Bösch-Doku

Die Modbusliste deklariert die WANDA-Register (Blatt „WANDA") als
**Datenpunkttyp `Float`** mit **Faktor 0,1**. Das ist falsch.

Ein IEEE-754-Float belegt 2 Register (4 Byte). Das Gerät liefert für diese
Register aber nur **1 Register (2 Byte)**. Beim Lesen als `float32` kommt
durchgängig:

```
ERROR [homeassistant.components.modbus] Received 2 bytes, unpack error
unpack requires a buffer of 4 bytes
```

**Korrekt ist `data_type: int16` + `scale: 0.1`** (der Rohwert steht in
Zehntel — genau dazu passt der dokumentierte Faktor 0,1).

Unabhängig bestätigt durch
[col-panic/homeassistant-boesch-heatpump-integration](https://github.com/col-panic/homeassistant-boesch-heatpump-integration):
dessen Config setzt gar kein `data_type` und nutzt damit den HA-Default
`int16`, ebenfalls mit `scale: 0.1`.

Ein Fehlerbericht an den Autor der Liste (Bösch) wurde formuliert, inkl.
zwei Rückfragen: (1) sind alle WANDA-Register 16 Bit? (2) wie ist Register
152 Betriebsstunden bei längerer Laufzeit ausgelegt?

## Config-Entscheidungen

- **`device_address:` statt `slave:`** — laut HA-Doku exakt synonym
  („Identical to `device_address`"), keine Deprecation. Nur Kosmetik.
- **`uint16` statt `int16`** bei 4 Sensoren, die nie negativ werden und
  Bereich brauchen: WANDA 152 (Betriebsstunden), WANDA 301 (PV-Leistung),
  Hydrobox 300/301 (Pumpenlaufzeiten).
- **`min_value`/`max_value` auf 68 der 77 Sensoren.** Achtung: diese Optionen
  **kappen** (`value < min → min`), sie filtern nicht. Deshalb nur gesetzt,
  wo der Bereich laut Doku oder physikalisch feststeht: Enums auf ihre
  dokumentierten Bereiche, COP 0–20, Leistungen 0–100 kW, Temperaturen
  −50…150 °C.
- **Rohe Fühlereingänge (250–258) bewusst OHNE min/max** — ein unbelegter
  Eingang würde sonst sauber auf 150 °C gekappt und sähe wie ein echter
  Messwert aus. Unbeschnitten ist sofort erkennbar, dass nichts dranhängt.
- **`nan_value: 0` NICHT übernommen** (col-panic setzt das auf Status-
  Registern). Damit würde „Status Heizkreis = 0" — also *Aus*, ein gültiger
  Zustand — als `unknown` verschwinden. Sieht nach Bug in seiner Config aus.
  In `boesch.yaml` steht stattdessen ein auskommentierter
  `nan_value: 0x8000`-Hinweis bei den AI-Eingängen.
- **`device_class: power_factor` für COP NICHT übernommen** (col-panic macht
  das) — power_factor ist semantisch ein Prozentwert.
- scan_interval: 15 s für Live-Werte, 30 s Standard, 60 s Sollwerte,
  300 s Betriebsstundenzähler.

## Vergleich mit col-panic-Integration

Andere Hardware (Mozart 13 AC RW60), daher andere Topologie — aber die
Register-Mappings validieren sich gegenseitig.

**Identisch:** COP 100–103, Leistungen 104–111, Status WP 200,
TWE 100–104, Heizkreis 150/153/155/156.

**Abweichend:**

- Slave-Topologie: bei ihm 50 = Speichermodul Heizen, **51 = Speichermodul
  TWE**, 30 = Heizkreismodul. Die Hydrobox fasst das in 50 zusammen.
- Außentemperatur: er liest **254/255**, unsere Doku sagt **275/276**.
  Bei uns sind 254/255 Fühler-Rohwerte (T1/AI6). Da die übrigen Register
  exakt matchen, ist das kein globaler Off-by-one, sondern Modul-Differenz.

Er hat ~30 Sensoren, wir 77 (ihm fehlen Vor-/Rücklauf, Durchfluss,
Betriebsstunden, PV-Modulation, Heizkreis 2, externer Wärmeerzeuger).

## Offene Punkte / noch zu verifizieren

1. **Plausibilität der Werte** nach dem Reload — Vorlauf ~30–45 °C,
   COP ~3–5. Falls etwas um Faktor 10 danebenliegt, `scale` prüfen.
2. **Außentemperatur 275/276** — kommt da Plausibles? Sonst 254/255 testen.
3. **TWE-Register auf `device_address: 50`** — falls leer, Slave 51 testen
   (so macht es col-panic).
4. **Register 301 Hydrobox** ist in der Bösch-Doku *dreifach* vergeben
   (Heizkreispumpe 2, Ext. WEZ 1-1, Ext. WEZ 1-2). Vermutlich 302/303.
   Bei Bösch nachfragen.
5. **WANDA 152 = Laufzeit seit letztem Start** (geklärt 2026-09-24, kein Gesamtzähler):
   Zehntelstunden, Reset auf 0 beim Abschalten; max. ~6553 h, also kein Überlaufproblem.
6. **R/W-Register sind aktuell nur lesend** eingebunden. Für echte Steuerung
   (Parallelverschiebung, TWE-Einmalladung, Sollwerte) fehlen noch
   `number`/`select`/`climate`-Entities. In `boesch.yaml` steht am Ende ein
   auskommentiertes `climate`-Beispiel für den TWE-Sollwert.

## Nebenbefund

Die `scan_interval < 5 s`-Warnungen im HA-Log stammen alle vom bestehenden
`VM-3P75CT`-Hub, nicht von Bösch.

## Quellen

- Bösch Modbusliste: `2026-07-21_Modbusliste_WANDA+Hydrobox.xlsx`
- [HA Modbus Integration](https://www.home-assistant.io/integrations/modbus/)
- [col-panic/homeassistant-boesch-heatpump-integration](https://github.com/col-panic/homeassistant-boesch-heatpump-integration)
