"""Config-, Reconfigure-, Reauth- und Options-Flow."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_DHCP, SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from custom_components.boesch.const import (
    CONF_AI_INPUTS,
    CONF_ENABLE_HK2,
    CONF_ENABLE_WEZ,
    CONF_HYDROBOX_ADDRESS,
    CONF_SCAN_DEFAULT,
    CONF_SCAN_HOURS,
    CONF_SCAN_LIVE,
    CONF_SCAN_SETPOINT,
    CONF_WANDA_ADDRESS,
    CONF_WEB_PASSWORD,
    CONF_WEB_POWER,
    DOMAIN,
)

USER_INPUT = {
    CONF_HOST: "192.0.2.10",
    CONF_PORT: 502,
    CONF_WANDA_ADDRESS: 40,
    CONF_HYDROBOX_ADDRESS: 50,
}
MAC = "aa:bb:cc:dd:ee:ff"


@pytest.fixture(autouse=True)
def no_setup():
    """Nur den Flow testen; das Laden des Entries deckt test_init.py ab."""
    with patch("custom_components.boesch.async_setup_entry", return_value=True):
        yield


async def _user(hass, user_input):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    return await hass.config_entries.flow.async_configure(result["flow_id"], user_input)


def _dhcp(ip: str) -> DhcpServiceInfo:
    return DhcpServiceInfo(ip=ip, hostname="xcenter", macaddress=MAC.replace(":", ""))


# ---- Ersteinrichtung --------------------------------------------------------


async def test_user_creates_entry(hass, fake_modbus) -> None:
    result = await _user(hass, USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == USER_INPUT
    assert result["options"] == {}  # ohne Web-Passwort keine Web-Optionen
    assert fake_modbus.instances[0].closed  # Test-Verbindung wieder zu


async def test_user_with_web_password(hass, fake_modbus, fake_web) -> None:
    result = await _user(hass, {**USER_INPUT, CONF_WEB_PASSWORD: " geheim "})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_WEB_PASSWORD not in result["data"]
    assert result["options"] == {CONF_WEB_PASSWORD: "geheim"}


@pytest.mark.parametrize(
    ("attr", "error"),
    [("auth_error", "invalid_auth"), ("error", "web_cannot_connect")],
)
async def test_user_web_errors(hass, fake_modbus, fake_web, attr, error) -> None:
    setattr(fake_web, attr, True)
    result = await _user(hass, {**USER_INPUT, CONF_WEB_PASSWORD: "pw"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


async def test_user_cannot_connect(hass, fake_modbus) -> None:
    fake_modbus.fail = True
    result = await _user(hass, USER_INPUT)
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_connect_refused(hass, fake_modbus) -> None:
    fake_modbus.connect_ok = False
    result = await _user(hass, USER_INPUT)
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_unknown_error(hass, fake_modbus) -> None:
    with patch(
        "custom_components.boesch.config_flow._test_connection",
        side_effect=RuntimeError,
    ):
        result = await _user(hass, USER_INPUT)
    assert result["errors"] == {"base": "unknown"}


async def test_user_duplicate_host(hass, fake_modbus, config_entry) -> None:
    config_entry.add_to_hass(hass)
    result = await _user(hass, USER_INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


# ---- DHCP --------------------------------------------------------------------


async def test_dhcp_new_device(hass, fake_modbus) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=_dhcp("192.0.2.20")
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    # Gefundene IP ist im Formular vorbelegt.
    host_key = next(k for k in result["data_schema"].schema if k == CONF_HOST)
    assert host_key.description == {"suggested_value": "192.0.2.20"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_HOST: "192.0.2.20"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == MAC


async def test_dhcp_known_mac_updates_ip(hass, config_entry) -> None:
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(config_entry, unique_id=MAC)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=_dhcp("192.0.2.99")
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert config_entry.data[CONF_HOST] == "192.0.2.99"


async def test_dhcp_manual_entry_gets_mac(hass, config_entry) -> None:
    """Manuell angelegter Entry (ohne MAC) wird über die IP erkannt."""
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_DHCP}, data=_dhcp(USER_INPUT[CONF_HOST])
    )
    assert result["type"] is FlowResultType.ABORT
    assert config_entry.unique_id == MAC


# ---- Reconfigure ---------------------------------------------------------------


async def test_reconfigure(hass, fake_modbus, config_entry) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"

    fake_modbus.fail = True
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_HOST: "192.0.2.30"}
    )
    assert result["errors"] == {"base": "cannot_connect"}

    fake_modbus.fail = False
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_HOST: "192.0.2.30"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data[CONF_HOST] == "192.0.2.30"


# ---- Reauth (Web-Passwort) -----------------------------------------------------


async def test_reauth(hass, fake_web, config_entry) -> None:
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry, options={CONF_WEB_POWER: True, CONF_WEB_PASSWORD: "alt"}
    )
    result = await config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    fake_web.auth_error = True
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_WEB_PASSWORD: "falsch"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    fake_web.auth_error = False
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_WEB_PASSWORD: " neu "}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    # Übrige Optionen bleiben erhalten.
    assert config_entry.options == {CONF_WEB_POWER: True, CONF_WEB_PASSWORD: "neu"}


# ---- Options --------------------------------------------------------------------


async def _options(hass, entry, step: str):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": step}
    )


async def test_options_general_keeps_other_options(hass, config_entry) -> None:
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry, options={CONF_AI_INPUTS: {"boesch_hb_ai8": "Puffer"}}
    )
    result = await _options(hass, config_entry, "general")
    assert result["step_id"] == "general"
    general = {
        CONF_ENABLE_HK2: True,
        CONF_ENABLE_WEZ: False,
        CONF_SCAN_LIVE: 10,
        CONF_SCAN_DEFAULT: 30,
        CONF_SCAN_SETPOINT: 60,
        CONF_SCAN_HOURS: 300,
    }
    result = await hass.config_entries.options.async_configure(result["flow_id"], general)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options == {CONF_AI_INPUTS: {"boesch_hb_ai8": "Puffer"}, **general}


async def test_options_inputs(hass, config_entry) -> None:
    config_entry.add_to_hass(hass)
    result = await _options(hass, config_entry, "inputs")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"boesch_hb_ai8": "  Puffer oben ", "boesch_hb_ai1": "  "}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    # Leere Namen = Eingang aus; Namen werden getrimmt.
    assert config_entry.options[CONF_AI_INPUTS] == {"boesch_hb_ai8": "Puffer oben"}


async def test_options_web(hass, fake_web, config_entry) -> None:
    config_entry.add_to_hass(hass)

    fake_web.auth_error = True
    result = await _options(hass, config_entry, "web")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_WEB_PASSWORD: "falsch", CONF_WEB_POWER: True}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    fake_web.auth_error = False
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_WEB_PASSWORD: "pw", CONF_WEB_POWER: True}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options == {CONF_WEB_PASSWORD: "pw", CONF_WEB_POWER: True}


async def test_options_web_disable(hass, fake_web, config_entry) -> None:
    """Leeres Passwort schaltet die Web-Funktionen ohne Test ab."""
    config_entry.add_to_hass(hass)
    fake_web.error = True
    result = await _options(hass, config_entry, "web")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_WEB_POWER: False}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options[CONF_WEB_PASSWORD] == ""
