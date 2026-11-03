"""Dünner async-Wrapper um pymodbus AsyncModbusTcpClient.

Eine einzige TCP-Verbindung bedient beide Geräte (WANDA + Hydrobox), über die
`device_id`/`slave`-Adresse unterschieden. Alle Zugriffe sind per Lock
serialisiert, damit sich die beiden Geräte auf der gemeinsamen Verbindung nicht
ins Gehege kommen.
"""

from __future__ import annotations

import asyncio
import inspect
import logging

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from .const import CONNECT_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class ModbusError(Exception):
    """Fehler bei der Modbus-Kommunikation."""


class BoeschModbusClient:
    """Serialisierter TCP-Client für WANDA + Hydrobox."""

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._client = AsyncModbusTcpClient(
            host=host, port=port, timeout=CONNECT_TIMEOUT
        )
        self._lock = asyncio.Lock()
        # pymodbus hat den Parameter von `slave` auf `device_id` umbenannt
        # (3.6..3.8+) – einmalig an der Signatur erkennen.
        params = inspect.signature(self._client.read_holding_registers).parameters
        self._unit_kw = "device_id" if "device_id" in params else "slave"

    async def async_connect(self) -> bool:
        """Verbindung aufbauen. Gibt True bei Erfolg zurück."""
        async with self._lock:
            return await self._client.connect()

    async def async_close(self) -> None:
        """Verbindung schließen."""
        async with self._lock:
            self._client.close()

    @property
    def connected(self) -> bool:
        return self._client.connected

    async def _ensure_connected(self) -> None:
        """Bei Bedarf (neu) verbinden; Aufruf nur unter Lock."""
        if not self._client.connected and not await self._client.connect():
            raise ModbusError(f"Verbindung zu {self._host}:{self._port} fehlgeschlagen")

    async def read_block(self, address: int, count: int, unit: int) -> list[int]:
        """Einen zusammenhängenden Block Holding-Register lesen.

        Gibt die rohen 16-Bit-Registerwerte zurück (noch ohne Vorzeichen/Skalierung).
        Stellt bei Bedarf die Verbindung her.
        """
        async with self._lock:
            await self._ensure_connected()
            try:
                result = await self._client.read_holding_registers(
                    address, count=count, **{self._unit_kw: unit}
                )
            except ModbusException as err:
                # Neuere pymodbus-Versionen werfen bei Timeout/Abbruch, statt
                # ein Fehlerergebnis zurückzugeben.
                raise ModbusError(
                    f"Read-Fehler @unit {unit} addr {address}+{count}: {err}"
                ) from err

        if result is None or result.isError():
            raise ModbusError(
                f"Read-Fehler @unit {unit} addr {address}+{count}: {result}"
            )
        return list(result.registers)

    async def write_register(self, address: int, value: int, unit: int) -> None:
        """Einen 16-Bit-Rohwert in ein Holding-Register schreiben (FC 0x06)."""
        async with self._lock:
            await self._ensure_connected()
            try:
                result = await self._client.write_register(
                    address, value, **{self._unit_kw: unit}
                )
            except ModbusException as err:
                raise ModbusError(
                    f"Write-Fehler @unit {unit} addr {address} = {value}: {err}"
                ) from err

        if result is None or result.isError():
            raise ModbusError(
                f"Write-Fehler @unit {unit} addr {address} = {value}: {result}"
            )
