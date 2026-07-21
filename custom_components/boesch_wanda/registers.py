"""Zentrales, datengetriebenes Registermodell für WANDA + Hydrobox.

Jede Zeile hier ersetzt einen handgeschriebenen Sensor-Block der ursprünglichen
`boesch.yaml` bzw. einen Klartext-Template-Sensor der `boesch-templates.yaml`.
Alle bereits verifizierten Entscheidungen (int16 + scale 0.1, uint16-Ausnahmen,
Kappungsgrenzen min/max, Enum-Bereiche, Poll-Klassen) sind 1:1 übernommen.

WICHTIG — Datentyp: Die Bösch-Liste deklariert die WANDA-Register als 'Float'
mit Faktor 0.1. Das ist falsch: das Gerät liefert je 1 Register (16 Bit). Daher
durchgängig int16 + scale 0.1 (uint16 nur wo nie negativ + Bereich nötig).

Das `writable`-Flag markiert die in der Bösch-Liste als R/W dokumentierten
Register. In Phase 1 (read-only) werden daraus noch KEINE number/select/switch-
Entities erzeugt — das Flag ist bereits gesetzt, damit der spätere Schritt ein
reines "Plattform aktivieren" ist.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .const import (
    DEFAULT_HYDROBOX_ADDRESS,
    DEFAULT_WANDA_ADDRESS,
    FEATURE_HK2,
    FEATURE_WEZ,
    POLL_DEFAULT,
    POLL_HOURS,
    POLL_LIVE,
    POLL_SETPOINT,
)


class DeviceKey(str, Enum):
    """Logisches Gerät, unter dem die Entity im Device-Registry hängt."""

    WANDA = "wanda"
    HYDROBOX = "hydrobox"


# Default-Modbus-Adressen je Gerät. Die tatsächlich benutzte Adresse kommt aus
# dem Config-Entry; diese Map dient nur der Zuordnung DeviceKey -> Adressfeld.
DEFAULT_ADDRESS_BY_DEVICE = {
    DeviceKey.WANDA: DEFAULT_WANDA_ADDRESS,
    DeviceKey.HYDROBOX: DEFAULT_HYDROBOX_ADDRESS,
}


class Kind(str, Enum):
    """Entity-Typ, der aus dem Register erzeugt wird."""

    SENSOR = "sensor"          # numerischer Messwert (read-only)
    ENUM = "enum"              # numerischer Code -> Klartext (sensor, device_class enum)
    BINARY = "binary"          # 0/1-Flag -> binary_sensor (is_on = value > on_threshold)
    NUMBER = "number"          # schreibbarer numerischer Sollwert (R/W)
    SELECT = "select"          # schreibbarer Enum/Modus (R/W)
    SWITCH = "switch"          # schreibbares 0/1-Flag (R/W)


# --------------------------------------------------------------------------
#  Enum-Wertetabellen (aus boesch-templates.yaml übernommen)
# --------------------------------------------------------------------------

WP_STATUS = {
    0: "Standby", 1: "Alarm", 2: "Trinkwassererwärmung", 3: "Kühlen",
    4: "Heizen", 5: "Abtauung", 6: "Vorbereitung", 7: "Blockiert",
    8: "EVU-Sperre", 9: "Nicht verfügbar",
}

HK_STATUS = {
    0: "Aus", 1: "Heizen", 2: "Kühlen", 3: "Taupunkt", 4: "Pumpenwartungslauf",
    5: "Frostschutz", 6: "Handbetrieb", 7: "Testmodus", 8: "Initialisierung",
    9: "Sicherheitszustand",
}

BETRIEBSMODUS = {0: "Aus", 1: "Heizen", 2: "Kühlen"}
BETRIEBSART = {0: "Auto", 1: "Aus"}
ENERGIEMODUS = {0: "Off", 1: "Eco", 2: "Normal", 3: "Comfort", 4: "Benutzerdefiniert"}
SAISON = {0: "Auto", 1: "Heizen", 2: "Kühlen", 3: "Aus"}
EINMALLADUNG = {0: "Aus", 1: "Ein"}
WEZ_BETRIEBSART = {
    0: "Auto", 1: "Nur Wärmepumpe", 2: "Beide", 3: "Sekundärer Wärmeerzeuger",
}
WEZ_STATUS = {
    0: "Keine Anforderung", 100: "Anforderung",
    200: "Auto Parallel Bereitschaft", 201: "Auto Alternativ Bereitschaft",
    202: "Auto TeilParallel Bereitschaft Parallel",
    203: "Auto TeilParallel Bereitschaft Alternativ",
    204: "Bereitschaft wegen Störung", 205: "Bereitschaft Handbetrieb Parallel",
    206: "Bereitschaft Handbetrieb Alternativ", 207: "Bereitschaft EVU-Sperre",
    208: "Bereitschaft External Request", 209: "Bereitschaft External Request Komfort",
    210: "Bereitschaft Funktionsheizen", 211: "Bereitschaft PV",
    300: "Auto Parallel Anforderung", 301: "Auto Alternativ Anforderung",
    302: "Auto TeilParallel Anforderung Parallel",
    303: "Auto TeilParallel Anforderung Alternativ",
    304: "Anforderung wegen Störung", 305: "Anforderung Handbetrieb Parallel",
    306: "Anforderung Handbetrieb Alternativ", 307: "Anforderung EVU-Sperre",
    308: "Anforderung External Request", 309: "Anforderung External Request Komfort",
    310: "Anforderung Funktionsheizen", 311: "Anforderung PV",
}


@dataclass(frozen=True)
class Reg:
    """Ein Modbus-Holding-Register und die daraus abgeleitete Entity."""

    key: str                         # == bisherige unique_id (boesch_*)
    name: str                        # == bisheriger Sensor-Name (Entity-ID-Kontinuität)
    device: DeviceKey
    address: int
    kind: Kind = Kind.SENSOR
    poll_group: str = POLL_DEFAULT
    data_type: str = "int16"         # int16 | uint16
    scale: float = 1.0
    precision: int | None = None
    unit: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    min_value: float | None = None   # Kappungsgrenze beim Lesen (value < min -> min)
    max_value: float | None = None
    options: dict[int, str] | None = None  # nur für Kind.ENUM
    on_threshold: float = 0.0        # nur für Kind.BINARY: is_on = value > threshold
    writable: bool = False           # in der Bösch-Liste als R/W dokumentiert
    feature: str | None = None       # None | FEATURE_HK2 | FEATURE_WEZ
    icon: str | None = None
    entity_category: str | None = None


# Kürzel-Helfer für die häufigsten Muster ------------------------------------

def _temp(key, name, dev, addr, group=POLL_DEFAULT, *, mn=-50.0, mx=150.0,
          writable=False, feature=None):
    return Reg(key=key, name=name, device=dev, address=addr, poll_group=group,
               data_type="int16", scale=0.1, precision=1, unit="°C",
               device_class="temperature", state_class="measurement",
               min_value=mn, max_value=mx, writable=writable, feature=feature)


def _power(key, name, dev, addr, group=POLL_LIVE):
    return Reg(key=key, name=name, device=dev, address=addr, poll_group=group,
               data_type="int16", scale=0.1, precision=2, unit="kW",
               device_class="power", state_class="measurement",
               min_value=0.0, max_value=100.0)


def _cop(key, name, dev, addr, group=POLL_LIVE):
    return Reg(key=key, name=name, device=dev, address=addr, poll_group=group,
               data_type="int16", scale=0.1, precision=2,
               state_class="measurement", min_value=0.0, max_value=20.0)


def _enum(key, name, dev, addr, options, group=POLL_DEFAULT, *,
          writable=False, feature=None, icon=None):
    return Reg(key=key, name=name, device=dev, address=addr, kind=Kind.ENUM,
               poll_group=group, options=options, min_value=min(options),
               max_value=max(options), writable=writable, feature=feature, icon=icon)


def _binary(key, name, dev, addr, group=POLL_SETPOINT, *, threshold=0.0,
            device_class=None, icon=None, feature=None):
    return Reg(key=key, name=name, device=dev, address=addr, kind=Kind.BINARY,
               poll_group=group, on_threshold=threshold, device_class=device_class,
               icon=icon, feature=feature)


# --- Schreibbare Register (R/W) ---------------------------------------------
# min_value/max_value dienen bei number/select doppelt: als Lese-Kappung UND als
# Eingabegrenze der Entity. Der Schreib-Rohwert wird in coordinator.py aus scale
# zurückgerechnet.

def _number(key, name, dev, addr, group=POLL_SETPOINT, *, data_type="int16",
            scale=1.0, precision=None, unit=None, device_class=None,
            mn=None, mx=None, icon=None, feature=None):
    return Reg(key=key, name=name, device=dev, address=addr, kind=Kind.NUMBER,
               poll_group=group, data_type=data_type, scale=scale, precision=precision,
               unit=unit, device_class=device_class, min_value=mn, max_value=mx,
               writable=True, icon=icon, feature=feature)


def _tnum(key, name, dev, addr, mn, mx, group=POLL_SETPOINT, *, feature=None):
    """Schreibbarer Temperatur-Sollwert (°C, scale 0.1)."""
    return _number(key, name, dev, addr, group, scale=0.1, precision=1, unit="°C",
                   device_class="temperature", mn=mn, mx=mx, feature=feature)


def _select(key, name, dev, addr, options, group=POLL_SETPOINT, *,
            icon=None, feature=None):
    return Reg(key=key, name=name, device=dev, address=addr, kind=Kind.SELECT,
               poll_group=group, options=options, min_value=min(options),
               max_value=max(options), writable=True, icon=icon, feature=feature)


def _switch(key, name, dev, addr, group=POLL_SETPOINT, *, icon=None, feature=None):
    return Reg(key=key, name=name, device=dev, address=addr, kind=Kind.SWITCH,
               poll_group=group, min_value=0.0, max_value=1.0, writable=True,
               icon=icon, feature=feature)


W = DeviceKey.WANDA
H = DeviceKey.HYDROBOX


REGISTERS: list[Reg] = [
    # =================  WANDA (device 40)  =================
    # ---- Energiequelle / Ladekreis ----
    _temp("boesch_wp_b15_quelle_eintritt", "WP Energiequellen Eintrittstemperatur B15", W, 2, POLL_DEFAULT),
    _temp("boesch_wp_b16_vorlauf", "WP Vorlauftemperatur B16", W, 50, POLL_LIVE),
    _temp("boesch_wp_b17_ruecklauf", "WP Ruecklauftemperatur B17", W, 51, POLL_LIVE),
    Reg("boesch_wp_p13_durchfluss", "WP Durchfluss P13", W, 52, poll_group=POLL_LIVE,
        data_type="int16", scale=0.1, precision=1, unit="L/min",
        device_class="volume_flow_rate", state_class="measurement",
        min_value=0.0, max_value=200.0),

    # ---- Leistung / Effizienz ----
    _cop("boesch_wp_cop", "WP COP aktuell", W, 100),
    _cop("boesch_wp_cop_heizen", "WP COP Heizen", W, 101),
    _cop("boesch_wp_cop_twe", "WP COP TWE", W, 102),
    _cop("boesch_wp_cop_kuehlen", "WP COP Kuehlen", W, 103),
    _power("boesch_wp_leistung", "WP Leistung aktuell", W, 104),
    _power("boesch_wp_leistung_heizen", "WP Leistung Heizen", W, 105),
    _power("boesch_wp_leistung_twe", "WP Leistung TWE", W, 106),
    _power("boesch_wp_leistung_kuehlen", "WP Leistung Kuehlen", W, 107),
    _power("boesch_wp_el_leistung", "WP elektr. Leistung aktuell", W, 108),
    _power("boesch_wp_el_leistung_heizen", "WP elektr. Leistung Heizen", W, 109),
    _power("boesch_wp_el_leistung_twe", "WP elektr. Leistung TWE", W, 110),
    _power("boesch_wp_el_leistung_kuehlen", "WP elektr. Leistung Kuehlen", W, 111),

    # ---- Verdichter-Status ----
    # Register 152 ist KEIN Betriebsstundenzaehler: per Verlauf (history-17.csv)
    # verifiziert wechselt der Wert 0<->nonzero synchron zur el. Leistung und
    # faellt beim Stopp auf 0 zurueck -> binaeres "Verdichter laeuft"-Flag, nicht
    # kumulativ. Das echte Laufzeit-Register ist unbekannt (bei Boesch nachfragen).
    _binary("boesch_wp_verdichter_laeuft", "WP Verdichter läuft", W, 152,
            POLL_DEFAULT, device_class="running", icon="mdi:heat-pump"),

    # ---- Status / Alarm ----
    _enum("boesch_wp_status", "WP Status", W, 200, WP_STATUS, POLL_LIVE, icon="mdi:heat-pump"),
    Reg("boesch_wp_alarmcode", "WP AlarmCode", W, 250, poll_group=POLL_DEFAULT,
        min_value=0.0),

    # ---- PV Modulation ----
    _binary("boesch_wp_pv_modulation", "WP PV Modulation", W, 300, POLL_DEFAULT,
            icon="mdi:solar-power"),
    _number("boesch_wp_pv_leistung", "WP PV Modulation Leistung", W, 301, POLL_DEFAULT,
            data_type="uint16", scale=0.1, precision=1, unit="W",
            device_class="power", mn=0.0, mx=6553.0),
    _tnum("boesch_wp_pv_soll_heizen", "WP PV Solltemp Heizen", W, 302, 0.0, 100.0),
    _tnum("boesch_wp_pv_soll_twe", "WP PV Solltemp TWE", W, 303, 0.0, 100.0),

    # =================  HYDROBOX (device 50)  =================
    # ---- Speicher Heizen / Kühlen / TWE ----
    _temp("boesch_hb_heizspeicher_ist", "HB Heizspeicher Ist", H, 1),
    _temp("boesch_hb_heizspeicher_soll", "HB Heizspeicher Soll", H, 2),
    _temp("boesch_hb_kuehlspeicher_ist", "HB Kuehlspeicher Ist", H, 50),
    _temp("boesch_hb_kuehlspeicher_soll", "HB Kuehlspeicher Soll", H, 51),
    _temp("boesch_hb_twe_ist", "HB TWE Ist", H, 100),
    _temp("boesch_hb_twe_soll", "HB TWE Soll", H, 101),
    _tnum("boesch_hb_twe_konst_soll", "HB TWE konstanter Sollwert", H, 102, 0.0, 85.0),
    _switch("boesch_hb_twe_einmalladung", "HB TWE Einmalladung", H, 103,
            icon="mdi:water-boiler"),
    _tnum("boesch_hb_twe_soll_einmal", "HB TWE Sollwert Einmalladung", H, 104, 30.0, 60.0),

    # ---- Heizkreis 1 ----
    _enum("boesch_hb_hk1_status", "HB HK1 Status", H, 150, HK_STATUS, icon="mdi:radiator"),
    _temp("boesch_hb_hk1_ist", "HB HK1 Isttemperatur", H, 151),
    _temp("boesch_hb_hk1_soll", "HB HK1 Solltemperatur", H, 152),
    _enum("boesch_hb_hk1_betriebsmodus", "HB HK1 Betriebsmodus", H, 153, BETRIEBSMODUS,
          icon="mdi:sun-snowflake-variant"),
    _select("boesch_hb_hk1_betriebsart", "HB HK1 Betriebsart", H, 154, BETRIEBSART,
            icon="mdi:toggle-switch"),
    _select("boesch_hb_hk1_energiemodus", "HB HK1 Energiemodus", H, 155, ENERGIEMODUS,
            icon="mdi:leaf"),
    _number("boesch_hb_hk1_parallel", "HB HK1 Parallelverschiebung Kurve", H, 156,
            mn=-5.0, mx=5.0, icon="mdi:tune-vertical"),
    _select("boesch_hb_hk1_saison", "HB HK1 Manuelle Saisonauswahl", H, 157, SAISON,
            icon="mdi:calendar-sync"),
    _tnum("boesch_hb_hk1_sommer_aus", "HB HK1 Sommerbetrieb Heizen Aus", H, 158, 0.0, 50.0),
    _tnum("boesch_hb_hk1_winter_ein", "HB HK1 Winterbetrieb Heizen Ein", H, 159, 0.0, 50.0),
    _tnum("boesch_hb_hk1_kuehl_ein", "HB HK1 Kuehlbetrieb Ein", H, 160, 0.0, 50.0),
    _tnum("boesch_hb_hk1_kuehl_aus", "HB HK1 Kuehlbetrieb Aus", H, 161, 0.0, 50.0),
    _binary("boesch_hb_hk1_sommer", "HB HK1 Sommerbetrieb", H, 162, icon="mdi:weather-sunny"),
    _binary("boesch_hb_hk1_kuehl", "HB HK1 Kuehlbetrieb", H, 163, icon="mdi:snowflake"),

    # ---- Heizkreis 2 (optional) ----
    _enum("boesch_hb_hk2_status", "HB HK2 Status", H, 175, HK_STATUS,
          icon="mdi:radiator", feature=FEATURE_HK2),
    _temp("boesch_hb_hk2_ist", "HB HK2 Isttemperatur", H, 176, feature=FEATURE_HK2),
    _temp("boesch_hb_hk2_soll", "HB HK2 Solltemperatur", H, 177, feature=FEATURE_HK2),
    _enum("boesch_hb_hk2_betriebsmodus", "HB HK2 Betriebsmodus", H, 178, BETRIEBSMODUS,
          icon="mdi:sun-snowflake-variant", feature=FEATURE_HK2),
    _select("boesch_hb_hk2_betriebsart", "HB HK2 Betriebsart", H, 179, BETRIEBSART,
            icon="mdi:toggle-switch", feature=FEATURE_HK2),
    _select("boesch_hb_hk2_energiemodus", "HB HK2 Energiemodus", H, 180, ENERGIEMODUS,
            icon="mdi:leaf", feature=FEATURE_HK2),
    _number("boesch_hb_hk2_parallel", "HB HK2 Parallelverschiebung Kurve", H, 181,
            mn=-5.0, mx=5.0, icon="mdi:tune-vertical", feature=FEATURE_HK2),
    _select("boesch_hb_hk2_saison", "HB HK2 Manuelle Saisonauswahl", H, 182, SAISON,
            icon="mdi:calendar-sync", feature=FEATURE_HK2),
    _tnum("boesch_hb_hk2_sommer_aus", "HB HK2 Sommerbetrieb Heizen Aus", H, 183, 0.0, 50.0,
          feature=FEATURE_HK2),
    _tnum("boesch_hb_hk2_winter_ein", "HB HK2 Winterbetrieb Heizen Ein", H, 184, 0.0, 50.0,
          feature=FEATURE_HK2),
    _tnum("boesch_hb_hk2_kuehl_ein", "HB HK2 Kuehlbetrieb Ein", H, 185, 0.0, 50.0,
          feature=FEATURE_HK2),
    _tnum("boesch_hb_hk2_kuehl_aus", "HB HK2 Kuehlbetrieb Aus", H, 186, 0.0, 50.0,
          feature=FEATURE_HK2),
    _binary("boesch_hb_hk2_sommer", "HB HK2 Sommerbetrieb", H, 187,
            icon="mdi:weather-sunny", feature=FEATURE_HK2),
    _binary("boesch_hb_hk2_kuehl", "HB HK2 Kuehlbetrieb", H, 188,
            icon="mdi:snowflake", feature=FEATURE_HK2),

    # ---- Externer Wärmeerzeuger (optional) ----
    _enum("boesch_hb_wez_heizen_status", "HB ext. WEZ Heizen Status", H, 200, WEZ_STATUS,
          POLL_SETPOINT, icon="mdi:fire", feature=FEATURE_WEZ),
    _select("boesch_hb_wez_heizen_art", "HB ext. WEZ Heizen Betriebsart", H, 201,
            WEZ_BETRIEBSART, icon="mdi:fire-circle", feature=FEATURE_WEZ),
    _enum("boesch_hb_wez_twe_status", "HB ext. WEZ TWE Status", H, 202, WEZ_STATUS,
          POLL_SETPOINT, icon="mdi:fire", feature=FEATURE_WEZ),
    _select("boesch_hb_wez_twe_art", "HB ext. WEZ TWE Betriebsart", H, 203,
            WEZ_BETRIEBSART, icon="mdi:fire-circle", feature=FEATURE_WEZ),
]

# ---- Rohe Fühlereingänge (BEWUSST OHNE min/max) ----
# Nicht belegte Eingänge sollen sichtbar unsinnig bleiben statt gekappt zu werden.
for _key, _name, _addr in [
    ("boesch_hb_ai1", "HB AI1 (CN6) Temperatur", 250),
    ("boesch_hb_ai2", "HB AI2 (CN6) Temperatur", 251),
    ("boesch_hb_ai3", "HB AI3 (CN47) Temperatur", 252),
    ("boesch_hb_ai4", "HB AI4 (CN47) Temperatur", 253),
    ("boesch_hb_t1", "HB T1 (CN10) Temperatur", 254),
    ("boesch_hb_ai6", "HB AI6 (CN13) Temperatur", 255),
    ("boesch_hb_ai7", "HB AI7 (CN15) Temperatur", 256),
    ("boesch_hb_ai8", "HB AI8 (CN13) Temperatur", 257),
    ("boesch_hb_tw_ibh", "HB Tw (IBH) Temperatur", 258),
]:
    REGISTERS.append(Reg(
        key=_key, name=_name, device=H, address=_addr, poll_group=POLL_SETPOINT,
        data_type="int16", scale=0.1, precision=1, unit="°C",
        device_class="temperature", state_class="measurement",
    ))

REGISTERS += [
    # ---- Außentemperatur ----
    # col-panic (Mozart RW60) liest 254/255; unsere Liste sagt 275/276.
    _temp("boesch_hb_aussentemperatur", "HB Aussentemperatur", H, 275),
    _temp("boesch_hb_aussentemperatur_gemittelt", "HB Aussentemperatur gemittelt", H, 276, POLL_SETPOINT),

    # ---- Betriebsstunden ----
    # Einheit MINUTEN, nicht Stunden: per Verlauf (history-16.csv) verifiziert —
    # der Zaehler steigt ~1:1 mit der Uhr (+5 pro 5 min Echtzeit).
    Reg("boesch_hb_hkp1_laufzeit", "HB Heizkreispumpe 1 Laufzeit", H, 300,
        poll_group=POLL_HOURS, data_type="uint16", unit="min",
        device_class="duration", state_class="total_increasing", min_value=0.0),
    # Doku vergibt 301 dreifach (HKP2, Ext.WEZ1-1, Ext.WEZ1-2) - bei Bösch prüfen.
    Reg("boesch_hb_hkp2_laufzeit", "HB Heizkreispumpe 2 Laufzeit", H, 301,
        poll_group=POLL_HOURS, data_type="uint16", unit="min",
        device_class="duration", state_class="total_increasing", min_value=0.0),
]


def registers_for(enable_hk2: bool, enable_wez: bool) -> list[Reg]:
    """Registerliste, gefiltert nach aktivierten Features."""
    result = []
    for reg in REGISTERS:
        if reg.feature == FEATURE_HK2 and not enable_hk2:
            continue
        if reg.feature == FEATURE_WEZ and not enable_wez:
            continue
        result.append(reg)
    return result
