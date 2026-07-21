"""Config- und Options-Flow für die Bösch WANDA Integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback

from .const import (
    CONF_ENABLE_HK2,
    CONF_ENABLE_WEZ,
    CONF_HYDROBOX_ADDRESS,
    CONF_SCAN_DEFAULT,
    CONF_SCAN_HOURS,
    CONF_SCAN_LIVE,
    CONF_SCAN_SETPOINT,
    CONF_WANDA_ADDRESS,
    DEFAULT_HOST,
    DEFAULT_HYDROBOX_ADDRESS,
    DEFAULT_PORT,
    DEFAULT_SCAN_DEFAULT,
    DEFAULT_SCAN_HOURS,
    DEFAULT_SCAN_LIVE,
    DEFAULT_SCAN_SETPOINT,
    DEFAULT_WANDA_ADDRESS,
    DOMAIN,
)
from .modbus_client import BoeschModbusClient, ModbusError

# WANDA-Statusregister — dient als Verbindungs-/Erreichbarkeitstest.
_TEST_ADDRESS = 200


async def _test_connection(host: str, port: int, wanda_unit: int) -> None:
    """Verbindung testen; wirft bei Fehler eine ModbusError."""
    client = BoeschModbusClient(host, port)
    try:
        if not await client.async_connect():
            raise ModbusError("connect_failed")
        await client.read_block(_TEST_ADDRESS, 1, wanda_unit)
    finally:
        await client.async_close()


class BoeschConfigFlow(ConfigFlow, domain=DOMAIN):
    """Setup-Flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._async_abort_entries_match({CONF_HOST: user_input[CONF_HOST]})
            try:
                await _test_connection(
                    user_input[CONF_HOST],
                    user_input[CONF_PORT],
                    user_input[CONF_WANDA_ADDRESS],
                )
            except ModbusError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title="Bösch", data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Required(
                    CONF_WANDA_ADDRESS, default=DEFAULT_WANDA_ADDRESS
                ): int,
                vol.Required(
                    CONF_HYDROBOX_ADDRESS, default=DEFAULT_HYDROBOX_ADDRESS
                ): int,
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return BoeschOptionsFlow()


class BoeschOptionsFlow(OptionsFlow):
    """Options-Flow: Features und Poll-Intervalle."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_ENABLE_HK2,
                    default=opts.get(CONF_ENABLE_HK2, True),
                ): bool,
                vol.Required(
                    CONF_ENABLE_WEZ,
                    default=opts.get(CONF_ENABLE_WEZ, True),
                ): bool,
                vol.Required(
                    CONF_SCAN_LIVE,
                    default=opts.get(CONF_SCAN_LIVE, DEFAULT_SCAN_LIVE),
                ): vol.All(int, vol.Range(min=5, max=3600)),
                vol.Required(
                    CONF_SCAN_DEFAULT,
                    default=opts.get(CONF_SCAN_DEFAULT, DEFAULT_SCAN_DEFAULT),
                ): vol.All(int, vol.Range(min=5, max=3600)),
                vol.Required(
                    CONF_SCAN_SETPOINT,
                    default=opts.get(CONF_SCAN_SETPOINT, DEFAULT_SCAN_SETPOINT),
                ): vol.All(int, vol.Range(min=5, max=3600)),
                vol.Required(
                    CONF_SCAN_HOURS,
                    default=opts.get(CONF_SCAN_HOURS, DEFAULT_SCAN_HOURS),
                ): vol.All(int, vol.Range(min=30, max=3600)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
