"""Gemeinsame Fixtures: Fake-Modbus-Gerät statt echter TCP-Verbindung."""

from __future__ import annotations

import copy
from collections.abc import Generator
from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.boesch.const import (
    CONF_HYDROBOX_ADDRESS,
    CONF_WANDA_ADDRESS,
    DOMAIN,
)
from custom_components.boesch.modbus_client import ModbusError
from custom_components.boesch.web_client import (
    MANAGER_DEVICE_ID,
    WebAuthError,
    WebError,
)

WANDA = 40
HYDROBOX = 50


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """custom_components/boesch für alle Tests ladbar machen."""
    return


class FakeModbusClient:
    """Speicher-Modell von WANDA + Hydrobox: {(unit, address): rohwert}.

    Nicht gesetzte Register lesen sich als 0. `fail` simuliert ein nicht
    erreichbares Gerät.
    """

    instances: ClassVar[list[FakeModbusClient]] = []
    registers: ClassVar[dict[tuple[int, int], int]] = {}
    fail = False
    connect_ok = True

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.closed = False
        self.writes: list[tuple[int, int, int]] = []
        FakeModbusClient.instances.append(self)

    @property
    def connected(self) -> bool:
        return not self.closed

    async def async_connect(self) -> bool:
        return FakeModbusClient.connect_ok

    async def async_close(self) -> None:
        self.closed = True

    async def read_block(self, address: int, count: int, unit: int) -> list[int]:
        if FakeModbusClient.fail:
            raise ModbusError("Gerät nicht erreichbar")
        return [
            FakeModbusClient.registers.get((unit, a), 0)
            for a in range(address, address + count)
        ]

    async def write_register(self, address: int, value: int, unit: int) -> None:
        if FakeModbusClient.fail:
            raise ModbusError("Gerät nicht erreichbar")
        self.writes.append((unit, address, value))
        FakeModbusClient.registers[(unit, address)] = value


@pytest.fixture
def fake_modbus() -> Generator[type[FakeModbusClient]]:
    """FakeModbusClient in Setup und Config-Flow einsetzen."""
    FakeModbusClient.instances = []
    FakeModbusClient.registers = {}
    FakeModbusClient.fail = False
    FakeModbusClient.connect_ok = True
    with (
        patch("custom_components.boesch.BoeschModbusClient", FakeModbusClient),
        patch("custom_components.boesch.config_flow.BoeschModbusClient", FakeModbusClient),
    ):
        yield FakeModbusClient


class FakeWebClient:
    """Webinterface als Dict: {(DeviceId, DatapointConfigId): Wert}.

    DeviceId eines Modbus-Geräts ist "dev<adresse>". `auth_error`/`error`
    simulieren falsches Passwort bzw. nicht erreichbares Webinterface.
    """

    instances: ClassVar[list[FakeWebClient]] = []
    values: ClassVar[dict[tuple[str, str], Any]] = {}
    auth_error = False
    error = False

    def __init__(self, session, host: str, password: str) -> None:
        self.password = password
        self.writes: list[tuple[str, str, str, Any]] = []
        FakeWebClient.instances.append(self)

    def _check(self) -> None:
        if FakeWebClient.auth_error:
            raise WebAuthError("Passwort abgelehnt")
        if FakeWebClient.error:
            raise WebError("Webinterface nicht erreichbar")

    async def async_login(self) -> None:
        self._check()

    async def async_get_devices(self) -> list[dict[str, Any]]:
        self._check()
        return [
            {"DeviceId": MANAGER_DEVICE_ID, "Address": "", "Serial": "S-WPM",
             "SoftwareVersion": "1.6.5.44"},
            {"DeviceId": "dev40", "Address": "40", "Serial": "S-WANDA",
             "SoftwareVersion": "1.1.2.39"},
            {"DeviceId": "dev50", "Address": "50", "Serial": "S-HB",
             "SoftwareVersion": "1.1.1.20"},
        ]

    async def async_get_device_id(self, address: int) -> str:
        self._check()
        return f"dev{address}"

    async def async_read(self, device_id: str, config_ids: list[str]) -> dict[str, Any]:
        self._check()
        return {
            cid: copy.deepcopy(FakeWebClient.values[(device_id, cid)])
            for cid in config_ids
            if (device_id, cid) in FakeWebClient.values
        }

    async def async_write(self, device_id, config_id, value_type, value) -> None:
        self._check()
        self.writes.append((device_id, config_id, value_type, value))
        FakeWebClient.values[(device_id, config_id)] = value


@pytest.fixture
def fake_web() -> Generator[type[FakeWebClient]]:
    """FakeWebClient in Setup und Config-Flow einsetzen."""
    FakeWebClient.instances = []
    FakeWebClient.values = {}
    FakeWebClient.auth_error = False
    FakeWebClient.error = False
    with (
        patch("custom_components.boesch.BoeschWebClient", FakeWebClient),
        patch("custom_components.boesch.config_flow.BoeschWebClient", FakeWebClient),
    ):
        yield FakeWebClient


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Config-Entry wie nach der Ersteinrichtung (ohne Web-Passwort)."""
    return MockConfigEntry(
        domain=DOMAIN,
        version=2,
        title="Bösch",
        data={
            CONF_HOST: "192.0.2.10",
            CONF_PORT: 502,
            CONF_WANDA_ADDRESS: WANDA,
            CONF_HYDROBOX_ADDRESS: HYDROBOX,
        },
    )
