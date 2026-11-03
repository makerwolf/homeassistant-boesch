"""Gemeinsame Fixtures: Fake-Modbus-Gerät statt echter TCP-Verbindung."""

from __future__ import annotations

from collections.abc import Generator
from typing import ClassVar
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
