"""DataUpdateCoordinator(s) für die Bösch WANDA Integration.

Pro Poll-Gruppe (live/default/setpoint/hours) läuft ein eigener Coordinator mit
eigenem Intervall — das bildet die scan_interval-Klassen der ursprünglichen
boesch.yaml ab. Innerhalb einer Gruppe werden zusammenhängende Registerbereiche
je Gerät als Block gelesen (statt jedes Register einzeln), was die Zahl der
Modbus-Roundtrips deutlich reduziert.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, MAX_BLOCK_GAP, MAX_BLOCK_SIZE
from .modbus_client import BoeschModbusClient, ModbusError
from .registers import DeviceKey, Reg

_LOGGER = logging.getLogger(__name__)


def _decode(reg: Reg, raw: int) -> float | int:
    """Rohwert eines 16-Bit-Registers gemäß Registerdefinition dekodieren."""
    if reg.data_type == "int16" and raw >= 0x8000:
        raw -= 0x10000
    value: float = raw * reg.scale
    if reg.min_value is not None and value < reg.min_value:
        value = reg.min_value
    if reg.max_value is not None and value > reg.max_value:
        value = reg.max_value
    if reg.scale == 1.0:
        return int(value)
    return round(value, reg.precision if reg.precision is not None else 3)


def _build_blocks(regs: list[Reg]) -> list[tuple[int, int]]:
    """Zusammenhängende Registerbereiche als (start, count) berechnen.

    Kleine Lücken (<= MAX_BLOCK_GAP) werden mitgelesen; Blöcke werden bei
    MAX_BLOCK_SIZE gekappt (Modbus erlaubt max. 125 Register pro Request).
    """
    if not regs:
        return []
    ordered = sorted(regs, key=lambda r: r.address)
    blocks: list[tuple[int, int]] = []
    start = ordered[0].address
    last = ordered[0].address
    for reg in ordered[1:]:
        gap = reg.address - last
        span = reg.address - start + 1
        if gap <= MAX_BLOCK_GAP and span <= MAX_BLOCK_SIZE:
            last = reg.address
        else:
            blocks.append((start, last - start + 1))
            start = reg.address
            last = reg.address
    blocks.append((start, last - start + 1))
    return blocks


class BoeschCoordinator(DataUpdateCoordinator[dict[str, float | int | None]]):
    """Coordinator für eine Poll-Gruppe."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: BoeschModbusClient,
        group: str,
        interval: int,
        regs: list[Reg],
        unit_by_device: dict[DeviceKey, int],
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{group}",
            update_interval=timedelta(seconds=interval),
            config_entry=entry,
        )
        self._client = client
        self.regs = regs
        self._unit_by_device = unit_by_device
        # Pro Gerät die Blöcke einmalig vorab berechnen.
        self._plan: dict[DeviceKey, list[tuple[int, int]]] = {}
        self._regs_by_device: dict[DeviceKey, list[Reg]] = {}
        for device in DeviceKey:
            dev_regs = [r for r in regs if r.device == device]
            if dev_regs:
                self._regs_by_device[device] = dev_regs
                self._plan[device] = _build_blocks(dev_regs)

    async def _async_update_data(self) -> dict[str, float | int | None]:
        data: dict[str, float | int | None] = {}
        try:
            for device, blocks in self._plan.items():
                unit = self._unit_by_device[device]
                dev_regs = self._regs_by_device[device]
                for start, count in blocks:
                    raw = await self._client.read_block(start, count, unit)
                    for reg in dev_regs:
                        idx = reg.address - start
                        if 0 <= idx < len(raw):
                            data[reg.key] = _decode(reg, raw[idx])
        except ModbusError as err:
            raise UpdateFailed(str(err)) from err
        return data

    async def async_write(self, reg: Reg, value: float) -> None:
        """Einen skalaren Wert in ein schreibbares Register schreiben.

        Kehrt die Dekodierung um: value/scale -> ganzzahliger Rohwert, negative
        int16-Werte als Zweierkomplement. Danach sofortiger Refresh, damit die
        Entity den bestätigten Gerätewert zeigt.
        """
        raw = int(round(value / reg.scale)) & 0xFFFF
        unit = self._unit_by_device[reg.device]
        await self._client.write_register(reg.address, raw, unit)
        await self.async_request_refresh()
