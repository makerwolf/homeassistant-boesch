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
    # Wärmepumpenmanager (x-center) – nur Webinterface-Entities, keine Register.
    MANAGER = "manager"


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
    WATER_HEATER = "water_heater"  # von der water_heater-Entity bedient (nicht standalone)


# --------------------------------------------------------------------------
#  Enum-Wertetabellen (aus boesch-templates.yaml übernommen)
# --------------------------------------------------------------------------

# Zustände als Schlüssel; die Anzeigetexte (de/en) stehen in translations/.
WP_STATUS = {
    0: "standby", 1: "alarm", 2: "hot_water", 3: "cooling", 4: "heating",
    5: "defrost", 6: "preparation", 7: "blocked", 8: "utility_lock",
    9: "not_available",
}

HK_STATUS = {
    0: "off", 1: "heating", 2: "cooling", 3: "dew_point", 4: "pump_maintenance",
    5: "frost_protection", 6: "manual", 7: "test_mode", 8: "initialization",
    9: "safety_state",
}

BETRIEBSMODUS = {0: "off", 1: "heating", 2: "cooling"}
BETRIEBSART = {0: "auto", 1: "off"}
ENERGIEMODUS = {0: "off", 1: "eco", 2: "normal", 3: "comfort", 4: "custom"}
SAISON = {0: "auto", 1: "heating", 2: "cooling", 3: "off"}
WEZ_BETRIEBSART = {0: "auto", 1: "heat_pump_only", 2: "both", 3: "secondary"}
WEZ_STATUS = {
    0: "no_request", 100: "request",
    200: "standby_auto_parallel", 201: "standby_auto_alternative",
    202: "standby_auto_partial_parallel", 203: "standby_auto_partial_alternative",
    204: "standby_fault", 205: "standby_manual_parallel",
    206: "standby_manual_alternative", 207: "standby_utility_lock",
    208: "standby_external_request", 209: "standby_external_request_comfort",
    210: "standby_screed_heating", 211: "standby_pv",
    300: "request_auto_parallel", 301: "request_auto_alternative",
    302: "request_auto_partial_parallel", 303: "request_auto_partial_alternative",
    304: "request_fault", 305: "request_manual_parallel",
    306: "request_manual_alternative", 307: "request_utility_lock",
    308: "request_external_request", 309: "request_external_request_comfort",
    310: "request_screed_heating", 311: "request_pv",
}


@dataclass(frozen=True)
class Reg:
    """Ein Modbus-Holding-Register und die daraus abgeleitete Entity."""

    key: str                         # unique_id; ohne "boesch_" = translation_key
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
    entity_category: str | None = None  # None | "config" | "diagnostic"
    enabled_default: bool = True     # False = neu angelegt, aber deaktiviert
    configurable: bool = False       # frei belegbarer Eingang: im Options-Flow
                                     # aktivier- und benennbar (siehe CONF_AI_INPUTS)


# Kürzel-Helfer für die häufigsten Muster ------------------------------------

def _temp(key: str, dev: DeviceKey, addr: int, group: str = POLL_DEFAULT, *,
          mn: float = -50.0, mx: float = 150.0, writable: bool = False,
          feature: str | None = None) -> Reg:
    return Reg(key=key, device=dev, address=addr, poll_group=group,
               data_type="int16", scale=0.1, precision=1, unit="°C",
               device_class="temperature", state_class="measurement",
               min_value=mn, max_value=mx, writable=writable, feature=feature)


def _power(key: str, dev: DeviceKey, addr: int, group: str = POLL_LIVE) -> Reg:
    return Reg(key=key, device=dev, address=addr, poll_group=group,
               data_type="int16", scale=0.1, precision=2, unit="kW",
               device_class="power", state_class="measurement",
               min_value=0.0, max_value=100.0)


def _cop(key: str, dev: DeviceKey, addr: int, group: str = POLL_LIVE) -> Reg:
    return Reg(key=key, device=dev, address=addr, poll_group=group,
               data_type="int16", scale=0.1, precision=2,
               state_class="measurement", min_value=0.0, max_value=20.0)


def _enum(key: str, dev: DeviceKey, addr: int, options: dict[int, str],
          group: str = POLL_DEFAULT, *, writable: bool = False,
          feature: str | None = None) -> Reg:
    return Reg(key=key, device=dev, address=addr, kind=Kind.ENUM,
               poll_group=group, options=options, min_value=min(options),
               max_value=max(options), writable=writable, feature=feature)


def _binary(key: str, dev: DeviceKey, addr: int, group: str = POLL_SETPOINT, *,
            threshold: float = 0.0, device_class: str | None = None,
            feature: str | None = None) -> Reg:
    return Reg(key=key, device=dev, address=addr, kind=Kind.BINARY,
               poll_group=group, on_threshold=threshold, device_class=device_class,
               feature=feature)


# --- Schreibbare Register (R/W) ---------------------------------------------
# min_value/max_value dienen bei number/select doppelt: als Lese-Kappung UND als
# Eingabegrenze der Entity. Der Schreib-Rohwert wird in coordinator.py aus scale
# zurückgerechnet.

def _number(key: str, dev: DeviceKey, addr: int, group: str = POLL_SETPOINT, *,
            data_type: str = "int16", scale: float = 1.0,
            precision: int | None = None, unit: str | None = None,
            device_class: str | None = None, mn: float | None = None,
            mx: float | None = None, feature: str | None = None,
            category: str | None = None) -> Reg:
    return Reg(key=key, device=dev, address=addr, kind=Kind.NUMBER,
               poll_group=group, data_type=data_type, scale=scale, precision=precision,
               unit=unit, device_class=device_class, min_value=mn, max_value=mx,
               writable=True, feature=feature, entity_category=category)


def _tnum(key: str, dev: DeviceKey, addr: int, mn: float, mx: float,
          group: str = POLL_SETPOINT, *, feature: str | None = None,
          category: str | None = None) -> Reg:
    """Schreibbarer Temperatur-Sollwert (°C, scale 0.1)."""
    return _number(key, dev, addr, group, scale=0.1, precision=1, unit="°C",
                   device_class="temperature", mn=mn, mx=mx, feature=feature,
                   category=category)


def _select(key: str, dev: DeviceKey, addr: int, options: dict[int, str],
            group: str = POLL_SETPOINT, *, feature: str | None = None) -> Reg:
    return Reg(key=key, device=dev, address=addr, kind=Kind.SELECT,
               poll_group=group, options=options, min_value=min(options),
               max_value=max(options), writable=True, feature=feature)


def _switch(key: str, dev: DeviceKey, addr: int, group: str = POLL_SETPOINT, *,
            feature: str | None = None) -> Reg:
    return Reg(key=key, device=dev, address=addr, kind=Kind.SWITCH,
               poll_group=group, min_value=0.0, max_value=1.0, writable=True,
               feature=feature)


W = DeviceKey.WANDA
H = DeviceKey.HYDROBOX


REGISTERS: list[Reg] = [
    # =================  WANDA (device 40)  =================
    # ---- Energiequelle / Ladekreis ----
    _temp("boesch_wanda_b15_quelle_eintritt", W, 2, POLL_DEFAULT),
    _temp("boesch_wanda_b16_vorlauf", W, 50, POLL_LIVE),
    _temp("boesch_wanda_b17_ruecklauf", W, 51, POLL_LIVE),
    Reg("boesch_wanda_p13_durchfluss", W, 52, poll_group=POLL_LIVE,
        data_type="int16", scale=0.1, precision=1, unit="L/min",
        device_class="volume_flow_rate", state_class="measurement",
        min_value=0.0, max_value=200.0),

    # ---- Leistung / Effizienz ----
    _cop("boesch_wanda_cop", W, 100),
    _cop("boesch_wanda_cop_heizen", W, 101),
    _cop("boesch_wanda_cop_twe", W, 102),
    _cop("boesch_wanda_cop_kuehlen", W, 103),
    _power("boesch_wanda_leistung", W, 104),
    _power("boesch_wanda_leistung_heizen", W, 105),
    _power("boesch_wanda_leistung_twe", W, 106),
    _power("boesch_wanda_leistung_kuehlen", W, 107),
    _power("boesch_wanda_el_leistung", W, 108),
    _power("boesch_wanda_el_leistung_heizen", W, 109),
    _power("boesch_wanda_el_leistung_twe", W, 110),
    _power("boesch_wanda_el_leistung_kuehlen", W, 111),

    # ---- Verdichter-Laufzeit seit Start ----
    # Register 152 = Stunden, die der Verdichter seit dem letzten Start
    # durchlaeuft (Zehntelstunden; per Verlauf history-20.csv verifiziert:
    # +10 roh pro Stunde Echtzeit, Reset auf 0 beim Abschalten). Kein Status-Flag
    # -> "Verdichter laeuft" kommt aus der el. Leistung (binary_sensor.py).
    # Per Live-Modbus als einzelnes 16-Bit-Register verifiziert (153 existiert nicht).
    Reg("boesch_wanda_laufzeit_seit_start", W, 152,
        poll_group=POLL_DEFAULT, data_type="uint16", scale=0.1, precision=1,
        unit="h", device_class="duration", state_class="measurement",
        min_value=0.0, entity_category="diagnostic",
        enabled_default=False),

    # ---- Status / Alarm ----
    _enum("boesch_wanda_status", W, 200, WP_STATUS, POLL_LIVE),
    Reg("boesch_wanda_alarmcode", W, 250, poll_group=POLL_DEFAULT,
        min_value=0.0, entity_category="diagnostic"),

    # ---- PV Modulation ----
    _binary("boesch_wanda_pv_modulation", W, 300, POLL_DEFAULT),
    _number("boesch_wanda_pv_leistung", W, 301, POLL_DEFAULT,
            data_type="uint16", scale=0.1, precision=1, unit="W",
            device_class="power", mn=0.0, mx=6553.0, category="config"),
    _tnum("boesch_wanda_pv_soll_heizen", W, 302, 0.0, 100.0,
          category="config"),
    _tnum("boesch_wanda_pv_soll_twe", W, 303, 0.0, 100.0,
          category="config"),

    # =================  HYDROBOX (device 50)  =================
    # ---- Speicher Heizen / Kühlen / TWE ----
    _temp("boesch_hb_heizspeicher_ist", H, 1),
    _temp("boesch_hb_heizspeicher_soll", H, 2),
    _temp("boesch_hb_kuehlspeicher_ist", H, 50),
    _temp("boesch_hb_kuehlspeicher_soll", H, 51),
    _temp("boesch_hb_twe_ist", H, 100),
    _temp("boesch_hb_twe_soll", H, 101),
    # TWE-Sollwert (102) + Einmalladung (103) werden von der water_heater-Entity
    # bedient (Kind.WATER_HEATER -> kein eigenes number/switch). Beide im DEFAULT-
    # Poll, damit sie mit dem Ist-Wert (100) in EINEM Coordinator liegen.
    Reg("boesch_hb_twe_konst_soll", H, 102,
        kind=Kind.WATER_HEATER, poll_group=POLL_DEFAULT, scale=0.1, precision=1,
        unit="°C", device_class="temperature", min_value=0.0, max_value=85.0,
        writable=True),
    Reg("boesch_hb_twe_einmalladung", H, 103,
        kind=Kind.WATER_HEATER, poll_group=POLL_DEFAULT,
        min_value=0.0, max_value=1.0, writable=True),
    _tnum("boesch_hb_twe_soll_einmal", H, 104, 30.0, 60.0),

    # ---- Heizkreis 1 ----
    _enum("boesch_hb_hk1_status", H, 150, HK_STATUS),
    _temp("boesch_hb_hk1_ist", H, 151),
    _temp("boesch_hb_hk1_soll", H, 152),
    _enum("boesch_hb_hk1_betriebsmodus", H, 153, BETRIEBSMODUS),
    _select("boesch_hb_hk1_betriebsart", H, 154, BETRIEBSART),
    _select("boesch_hb_hk1_energiemodus", H, 155, ENERGIEMODUS),
    _number("boesch_hb_hk1_parallel", H, 156,
            mn=-5.0, mx=5.0),
    _select("boesch_hb_hk1_saison", H, 157, SAISON),
    _tnum("boesch_hb_hk1_sommer_aus", H, 158, 0.0, 50.0, category="config"),
    _tnum("boesch_hb_hk1_winter_ein", H, 159, 0.0, 50.0, category="config"),
    _tnum("boesch_hb_hk1_kuehl_ein", H, 160, 0.0, 50.0, category="config"),
    _tnum("boesch_hb_hk1_kuehl_aus", H, 161, 0.0, 50.0, category="config"),
    _binary("boesch_hb_hk1_sommer", H, 162),
    _binary("boesch_hb_hk1_kuehl", H, 163),

    # ---- Heizkreis 2 (optional) ----
    _enum("boesch_hb_hk2_status", H, 175, HK_STATUS, feature=FEATURE_HK2),
    _temp("boesch_hb_hk2_ist", H, 176, feature=FEATURE_HK2),
    _temp("boesch_hb_hk2_soll", H, 177, feature=FEATURE_HK2),
    _enum("boesch_hb_hk2_betriebsmodus", H, 178, BETRIEBSMODUS, feature=FEATURE_HK2),
    _select("boesch_hb_hk2_betriebsart", H, 179, BETRIEBSART, feature=FEATURE_HK2),
    _select("boesch_hb_hk2_energiemodus", H, 180, ENERGIEMODUS, feature=FEATURE_HK2),
    _number("boesch_hb_hk2_parallel", H, 181,
            mn=-5.0, mx=5.0, feature=FEATURE_HK2),
    _select("boesch_hb_hk2_saison", H, 182, SAISON, feature=FEATURE_HK2),
    _tnum("boesch_hb_hk2_sommer_aus", H, 183, 0.0, 50.0,
          feature=FEATURE_HK2, category="config"),
    _tnum("boesch_hb_hk2_winter_ein", H, 184, 0.0, 50.0,
          feature=FEATURE_HK2, category="config"),
    _tnum("boesch_hb_hk2_kuehl_ein", H, 185, 0.0, 50.0,
          feature=FEATURE_HK2, category="config"),
    _tnum("boesch_hb_hk2_kuehl_aus", H, 186, 0.0, 50.0,
          feature=FEATURE_HK2, category="config"),
    _binary("boesch_hb_hk2_sommer", H, 187, feature=FEATURE_HK2),
    _binary("boesch_hb_hk2_kuehl", H, 188, feature=FEATURE_HK2),

    # ---- Externer Wärmeerzeuger (optional) ----
    _enum("boesch_hb_wez_heizen_status", H, 200, WEZ_STATUS,
          POLL_SETPOINT, feature=FEATURE_WEZ),
    _select("boesch_hb_wez_heizen_art", H, 201,
            WEZ_BETRIEBSART, feature=FEATURE_WEZ),
    _enum("boesch_hb_wez_twe_status", H, 202, WEZ_STATUS,
          POLL_SETPOINT, feature=FEATURE_WEZ),
    _select("boesch_hb_wez_twe_art", H, 203,
            WEZ_BETRIEBSART, feature=FEATURE_WEZ),
]

# ---- Frei belegbare Fühlereingänge (BEWUSST OHNE min/max) ----
# Belegung ist anlagenspezifisch (vom Techniker verdrahtet), daher configurable:
# im Options-Flow einzeln aktivier- und benennbar. Standard = deaktiviert.
# Ohne min/max, damit ein unbelegter Eingang sichtbar unsinnig bleibt.
AI_INPUTS: list[tuple[str, str, int]] = [
    ("boesch_hb_ai1", "AI1 (CN6)", 250),
    ("boesch_hb_ai2", "AI2 (CN6)", 251),
    ("boesch_hb_ai3", "AI3 (CN47)", 252),
    ("boesch_hb_ai4", "AI4 (CN47)", 253),
    ("boesch_hb_t1", "T1 (CN10)", 254),
    ("boesch_hb_ai6", "AI6 (CN13)", 255),
    ("boesch_hb_ai7", "AI7 (CN15)", 256),
    ("boesch_hb_ai8", "AI8 (CN13)", 257),
    ("boesch_hb_tw_ibh", "Tw (IBH)", 258),
]
for _key, _label, _addr in AI_INPUTS:
    REGISTERS.append(Reg(
        key=_key, device=H, address=_addr,
        poll_group=POLL_SETPOINT, data_type="int16", scale=0.1, precision=1,
        unit="°C", device_class="temperature", state_class="measurement",
        configurable=True, entity_category="diagnostic",
    ))

REGISTERS += [
    # ---- Außentemperatur ----
    # col-panic (Mozart RW60) liest 254/255; unsere Liste sagt 275/276.
    _temp("boesch_hb_aussentemperatur", H, 275),
    _temp("boesch_hb_aussentemperatur_gemittelt", H, 276, POLL_SETPOINT),

    # ---- Betriebsstunden ----
    # Einheit MINUTEN, nicht Stunden: per Verlauf (history-16.csv) verifiziert —
    # der Zaehler steigt ~1:1 mit der Uhr (+5 pro 5 min Echtzeit).
    Reg("boesch_hb_hkp1_laufzeit", H, 300,
        poll_group=POLL_HOURS, data_type="uint16", unit="min",
        device_class="duration", state_class="total_increasing", min_value=0.0,
        entity_category="diagnostic"),
    # Doku vergibt 301 dreifach (HKP2, Ext.WEZ1-1, Ext.WEZ1-2) - bei Bösch prüfen.
    Reg("boesch_hb_hkp2_laufzeit", H, 301,
        poll_group=POLL_HOURS, data_type="uint16", unit="min",
        device_class="duration", state_class="total_increasing", min_value=0.0,
        entity_category="diagnostic", enabled_default=False),
]


def registers_for(enable_hk2: bool, enable_wez: bool) -> list[Reg]:
    """Registerliste, gefiltert nach aktivierten Features."""
    result: list[Reg] = []
    for reg in REGISTERS:
        if reg.feature == FEATURE_HK2 and not enable_hk2:
            continue
        if reg.feature == FEATURE_WEZ and not enable_wez:
            continue
        result.append(reg)
    return result
