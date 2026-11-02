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
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from .const import (
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
    DEFAULT_ENABLE_HK2,
    DEFAULT_ENABLE_WEZ,
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
from .registers import AI_INPUTS
from .web_client import BoeschWebClient, WebAuthError, WebError

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


async def _test_web(hass, host: str, hydrobox_unit: int, password: str) -> str | None:
    """Webinterface-Login + Hydrobox-Suche testen; liefert Fehlerschlüssel oder None."""
    client = BoeschWebClient(async_get_clientsession(hass), host, password)
    try:
        await client.async_login()
        await client.async_get_device_id(hydrobox_unit)
    except WebAuthError:
        return "invalid_auth"
    except WebError:
        return "web_cannot_connect"
    return None


def _web_password_field(current: str | None) -> dict:
    """Optionales Passwortfeld für das Webinterface (leer = aus)."""
    return {
        vol.Optional(
            CONF_WEB_PASSWORD, description={"suggested_value": current}
        ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
    }


class BoeschConfigFlow(ConfigFlow, domain=DOMAIN):
    """Setup-Flow."""

    VERSION = 2

    _discovered_host: str | None = None

    @staticmethod
    def _schema(defaults: dict[str, Any]) -> vol.Schema:
        return vol.Schema(
            {
                # Kein Default: die IP ist in jedem Netz eine andere.
                vol.Required(
                    CONF_HOST,
                    description={"suggested_value": defaults.get(CONF_HOST)},
                ): str,
                vol.Required(
                    CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)
                ): int,
                vol.Required(
                    CONF_WANDA_ADDRESS,
                    default=defaults.get(CONF_WANDA_ADDRESS, DEFAULT_WANDA_ADDRESS),
                ): int,
                vol.Required(
                    CONF_HYDROBOX_ADDRESS,
                    default=defaults.get(
                        CONF_HYDROBOX_ADDRESS, DEFAULT_HYDROBOX_ADDRESS
                    ),
                ): int,
            }
        )

    async def _validate(self, user_input: dict[str, Any]) -> str | None:
        """Verbindung testen; liefert Fehlerschlüssel oder None."""
        try:
            await _test_connection(
                user_input[CONF_HOST],
                user_input[CONF_PORT],
                user_input[CONF_WANDA_ADDRESS],
            )
        except ModbusError:
            return "cannot_connect"
        except Exception:  # noqa: BLE001
            return "unknown"
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ersteinrichtung. Das Web-Passwort ist optional und landet in den
        Optionen (dort später änderbar), nicht in den Verbindungsdaten."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._async_abort_entries_match({CONF_HOST: user_input[CONF_HOST]})
            data = {k: v for k, v in user_input.items() if k != CONF_WEB_PASSWORD}
            password = (user_input.get(CONF_WEB_PASSWORD) or "").strip()
            error = await self._validate(data)
            if not error and password:
                error = await _test_web(
                    self.hass, data[CONF_HOST], data[CONF_HYDROBOX_ADDRESS], password
                )
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title="Bösch",
                    data=data,
                    options={CONF_WEB_PASSWORD: password} if password else {},
                )

        # Nach DHCP-Discovery die gefundene IP vorbelegen.
        defaults = user_input or {CONF_HOST: self._discovered_host}
        return self.async_show_form(
            step_id="user",
            data_schema=self._schema(defaults).extend(
                _web_password_field(defaults.get(CONF_WEB_PASSWORD))
            ),
            errors=errors,
        )

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        """Kermi x-center (Hostname xcenter*) per DHCP gefunden.

        Bekanntes Gerät (gleiche MAC): neue IP übernehmen, Entry neu laden.
        Sonst Setup-Formular mit vorbelegter IP anzeigen.
        """
        host = discovery_info.ip
        await self.async_set_unique_id(format_mac(discovery_info.macaddress))
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})

        # Manuell angelegte Entries haben keine MAC: über die IP erkennen und
        # die MAC nachtragen, damit spätere IP-Wechsel erkannt werden.
        for entry in self._async_current_entries(include_ignore=False):
            if entry.data.get(CONF_HOST) == host:
                if entry.unique_id is None:
                    self.hass.config_entries.async_update_entry(
                        entry, unique_id=self.unique_id
                    )
                return self.async_abort(reason="already_configured")

        self._discovered_host = host
        self.context["title_placeholders"] = {"host": host}
        return await self.async_step_user()

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Verbindungsdaten (IP, Port, Modbus-Adressen) nachträglich ändern.

        Modbus TCP kennt keine Authentifizierung, daher gibt es kein Passwort.
        """
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            if error := await self._validate(user_input):
                errors["base"] = error
            else:
                # Der Update-Listener in __init__ lädt den Entry neu.
                self.hass.config_entries.async_update_entry(
                    entry, data={**entry.data, **user_input}
                )
                return self.async_abort(reason="reconfigure_successful")

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._schema(user_input or entry.data),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return BoeschOptionsFlow()


class BoeschOptionsFlow(OptionsFlow):
    """Options-Flow: Menü mit Allgemein (Features/Intervalle) und Fühlereingängen."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init", menu_options=["general", "inputs", "web"]
        )

    async def async_step_general(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Heizkreise, externer Wärmeerzeuger, Poll-Intervalle."""
        if user_input is not None:
            # Bestehende Optionen (z. B. ai_inputs) erhalten.
            return self.async_create_entry(
                title="", data={**self.config_entry.options, **user_input}
            )

        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_ENABLE_HK2,
                    default=opts.get(CONF_ENABLE_HK2, DEFAULT_ENABLE_HK2),
                ): bool,
                vol.Required(
                    CONF_ENABLE_WEZ,
                    default=opts.get(CONF_ENABLE_WEZ, DEFAULT_ENABLE_WEZ),
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
        return self.async_show_form(step_id="general", data_schema=schema)

    async def async_step_inputs(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Frei belegbare Fühlereingänge (AI1..Tw): Name eingeben = aktivieren."""
        if user_input is not None:
            names = {
                key: value.strip()
                for key, value in user_input.items()
                if value and value.strip()
            }
            return self.async_create_entry(
                title="",
                data={**self.config_entry.options, CONF_AI_INPUTS: names},
            )

        current: dict[str, str] = self.config_entry.options.get(CONF_AI_INPUTS, {})
        schema = vol.Schema(
            {
                vol.Optional(key, default=current.get(key, "")): str
                for key, _label, _addr in AI_INPUTS
            }
        )
        return self.async_show_form(step_id="inputs", data_schema=schema)

    async def async_step_web(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Webinterface (Kermi x-center): Passwort setzen = Web-Entities aktiv.

        Leer lassen schaltet die Web-Entities ab. Host ist derselbe wie für Modbus.
        """
        errors: dict[str, str] = {}
        if user_input is not None:
            password = (user_input.get(CONF_WEB_PASSWORD) or "").strip()
            entry = self.config_entry
            if password and (
                error := await _test_web(
                    self.hass,
                    entry.data[CONF_HOST],
                    entry.data.get(CONF_HYDROBOX_ADDRESS, DEFAULT_HYDROBOX_ADDRESS),
                    password,
                )
            ):
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title="",
                    data={**entry.options, CONF_WEB_PASSWORD: password},
                )

        schema = vol.Schema(
            _web_password_field(self.config_entry.options.get(CONF_WEB_PASSWORD))
        )
        return self.async_show_form(step_id="web", data_schema=schema, errors=errors)
