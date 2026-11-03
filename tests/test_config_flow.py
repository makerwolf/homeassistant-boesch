"""Config-Flow: Ersteinrichtung, Verbindungsfehler, Duplikate."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResultType

from custom_components.boesch.const import (
    CONF_HYDROBOX_ADDRESS,
    CONF_WANDA_ADDRESS,
    DOMAIN,
)

USER_INPUT = {
    CONF_HOST: "192.0.2.10",
    CONF_PORT: 502,
    CONF_WANDA_ADDRESS: 40,
    CONF_HYDROBOX_ADDRESS: 50,
}


async def _start(hass):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})


async def test_user_flow_creates_entry(hass, fake_modbus) -> None:
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == USER_INPUT
    assert result["options"] == {}  # ohne Web-Passwort keine Web-Optionen
    # Die Test-Verbindung wird wieder geschlossen.
    assert fake_modbus.instances[0].closed


async def test_user_flow_cannot_connect(hass, fake_modbus) -> None:
    fake_modbus.fail = True
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_duplicate_host(hass, fake_modbus, config_entry) -> None:
    config_entry.add_to_hass(hass)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
