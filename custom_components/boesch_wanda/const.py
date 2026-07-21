"""Konstanten für die Bösch WANDA Integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "boesch_wanda"

MANUFACTURER: Final = "Bösch"
MODEL_WANDA: Final = "WANDA 10"
MODEL_HYDROBOX: Final = "Hydrobox"

# --- Config-Keys ---
CONF_WANDA_ADDRESS: Final = "wanda_address"
CONF_HYDROBOX_ADDRESS: Final = "hydrobox_address"
CONF_ENABLE_HK2: Final = "enable_hk2"
CONF_ENABLE_WEZ: Final = "enable_wez"

CONF_SCAN_LIVE: Final = "scan_live"
CONF_SCAN_DEFAULT: Final = "scan_default"
CONF_SCAN_SETPOINT: Final = "scan_setpoint"
CONF_SCAN_HOURS: Final = "scan_hours"

# --- Defaults ---
DEFAULT_HOST: Final = "192.168.0.202"
DEFAULT_PORT: Final = 502
DEFAULT_WANDA_ADDRESS: Final = 40
DEFAULT_HYDROBOX_ADDRESS: Final = 50

# Poll-Gruppen -> Default-Intervall in Sekunden.
# Bilden die scan_interval-Klassen der ursprünglichen boesch.yaml ab.
POLL_LIVE: Final = "live"
POLL_DEFAULT: Final = "default"
POLL_SETPOINT: Final = "setpoint"
POLL_HOURS: Final = "hours"

DEFAULT_SCAN_LIVE: Final = 15
DEFAULT_SCAN_DEFAULT: Final = 30
DEFAULT_SCAN_SETPOINT: Final = 60
DEFAULT_SCAN_HOURS: Final = 300

SCAN_OPTION_BY_GROUP: Final = {
    POLL_LIVE: CONF_SCAN_LIVE,
    POLL_DEFAULT: CONF_SCAN_DEFAULT,
    POLL_SETPOINT: CONF_SCAN_SETPOINT,
    POLL_HOURS: CONF_SCAN_HOURS,
}

SCAN_DEFAULT_BY_GROUP: Final = {
    POLL_LIVE: DEFAULT_SCAN_LIVE,
    POLL_DEFAULT: DEFAULT_SCAN_DEFAULT,
    POLL_SETPOINT: DEFAULT_SCAN_SETPOINT,
    POLL_HOURS: DEFAULT_SCAN_HOURS,
}

# Feature-Tags (Options-Flow blendet die zugehörigen Register aus).
FEATURE_HK2: Final = "hk2"
FEATURE_WEZ: Final = "wez"

# Modbus-Client / Block-Read
CONNECT_TIMEOUT: Final = 5
MAX_BLOCK_SIZE: Final = 100  # max. Register pro Read-Request (Modbus-Limit 125)
MAX_BLOCK_GAP: Final = 8     # kleine Lücken werden mitgelesen, statt neu zu pollen
