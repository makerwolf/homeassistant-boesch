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
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, MAX_BLOCK_GAP, MAX_BLOCK_SIZE
from .modbus_client import BoeschModbusClient, ModbusError
from .registers import DeviceKey, Reg
from .web_client import (
    DP_HK1_COOLING_CURVE,
    DP_HK1_FIXED_SETPOINT_COOLING,
    DP_HK1_FIXED_SETPOINT_HEATING,
    DP_HK1_HEATING_CURVE,
    DP_HK1_HEATING_WATER_MODE,
    DP_HK1_MIXER_POSITION,
    DP_POWER_ELECTRIC,
    DP_POWER_ELECTRIC_COOLING,
    DP_POWER_ELECTRIC_HEATING,
    DP_POWER_ELECTRIC_TWE,
    DP_POWER_OUTPUT,
    DP_POWER_OUTPUT_COOLING,
    DP_POWER_OUTPUT_HEATING,
    DP_POWER_OUTPUT_TWE,
    DP_SEASON_OUTDOOR_TEMPERATURE,
    DP_SYSTEM_IS_PRESENT,
    MANAGER_DEVICE_ID,
    TYPE_CURVE,
    BoeschWebClient,
    WebAuthError,
    WebError,
)

_LOGGER = logging.getLogger(__name__)

# Vom Web-Coordinator gepollte Datenpunkte (nur was Modbus nicht bietet).
WEB_DATAPOINTS_HYDROBOX = [
    DP_HK1_HEATING_WATER_MODE,
    DP_HK1_FIXED_SETPOINT_HEATING,
    DP_HK1_FIXED_SETPOINT_COOLING,
    DP_HK1_HEATING_CURVE,
    DP_HK1_COOLING_CURVE,
    DP_HK1_MIXER_POSITION,
    DP_SEASON_OUTDOOR_TEMPERATURE,
]
WEB_DATAPOINTS_MANAGER = [DP_SYSTEM_IS_PRESENT]

# Hochauflösende Leistung (Option): Modbus-Register-Key -> Web-Datenpunkt.
WEB_POWER = {
    "boesch_wanda_leistung": DP_POWER_OUTPUT,
    "boesch_wanda_leistung_heizen": DP_POWER_OUTPUT_HEATING,
    "boesch_wanda_leistung_twe": DP_POWER_OUTPUT_TWE,
    "boesch_wanda_leistung_kuehlen": DP_POWER_OUTPUT_COOLING,
    "boesch_wanda_el_leistung": DP_POWER_ELECTRIC,
    "boesch_wanda_el_leistung_heizen": DP_POWER_ELECTRIC_HEATING,
    "boesch_wanda_el_leistung_twe": DP_POWER_ELECTRIC_TWE,
    "boesch_wanda_el_leistung_kuehlen": DP_POWER_ELECTRIC_COOLING,
}


def _decode(reg: Reg, raw: int) -> float | int:
    """Rohwert eines 16-Bit-Registers gemäß Registerdefinition dekodieren."""
    if reg.data_type == "int16" and raw >= 0x8000:
        raw -= 0x10000
    return _finish(reg, raw * reg.scale)


def _finish(reg: Reg, value: float) -> float | int:
    """Auf den Registerbereich kappen und runden."""
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


class WebPowerSource:
    """Hochauflösende WANDA-Leistungen aus dem Webinterface (0,01 statt 0,1 kW).

    Modbus schneidet die Leistungen auf 0,1 kW ab (systematisch zu niedrig),
    das x-center kennt sie mit 0,01 kW. Liefert {Register-Key: kW}.
    """

    def __init__(self, client: BoeschWebClient, wanda_unit: int) -> None:
        self._client = client
        self._wanda_unit = wanda_unit
        self._device_id: str | None = None

    async def async_read(self) -> dict[str, float]:
        if self._device_id is None:
            self._device_id = await self._client.async_get_device_id(self._wanda_unit)
        values = await self._client.async_read(self._device_id, list(WEB_POWER.values()))
        result: dict[str, float] = {}
        for key, config_id in WEB_POWER.items():
            value = values.get(config_id)
            if isinstance(value, (int, float)):
                result[key] = float(value)
        return result


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
        web_power: WebPowerSource | None = None,
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
        self._reg_by_key = {r.key: r for r in regs}
        self._web_power = web_power
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
        if self._web_power is not None:
            await self._apply_web_power(data)
        return data

    async def _apply_web_power(self, data: dict[str, float | int | None]) -> None:
        """Modbus-Leistungen durch die Web-Werte ersetzen, falls verfügbar.

        Rückfall pro Poll: schlägt das Webinterface fehl oder fehlt ein Wert,
        bleibt der Modbus-Wert stehen – die Energiezähler laufen weiter.
        """
        try:
            values = await self._web_power.async_read()
        except WebError as err:
            _LOGGER.debug("Web-Leistung nicht verfügbar, nutze Modbus: %s", err)
            return
        for key, value in values.items():
            if (reg := self._reg_by_key.get(key)) is not None:
                data[key] = _finish(reg, value)

    async def async_write(self, reg: Reg, value: float) -> None:
        """Einen skalaren Wert in ein schreibbares Register schreiben.

        Kehrt die Dekodierung um: value/scale -> ganzzahliger Rohwert, negative
        int16-Werte als Zweierkomplement. Danach sofortiger Refresh, damit die
        Entity den bestätigten Gerätewert zeigt.
        """
        raw = round(value / reg.scale) & 0xFFFF
        unit = self._unit_by_device[reg.device]
        try:
            await self._client.write_register(reg.address, raw, unit)
        except ModbusError as err:
            raise HomeAssistantError(str(err)) from err
        await self.async_request_refresh()


class BoeschWebCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator für die Webinterface-Datenpunkte (Hydrobox + Wärmepumpenmanager).

    Daten: {DatapointConfigId: Value}. Die DeviceId der Hydrobox wird beim
    ersten Poll über ihre Modbus-Adresse nachgeschlagen; der Manager hat immer
    die Null-GUID.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: BoeschWebClient,
        interval: int,
        hydrobox_unit: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_web",
            update_interval=timedelta(seconds=interval),
            config_entry=entry,
        )
        self._client = client
        self._hydrobox_unit = hydrobox_unit
        self._device_id: str | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            if self._device_id is None:
                self._device_id = await self._client.async_get_device_id(
                    self._hydrobox_unit
                )
            data = await self._client.async_read(
                self._device_id, WEB_DATAPOINTS_HYDROBOX
            )
            data.update(
                await self._client.async_read(MANAGER_DEVICE_ID, WEB_DATAPOINTS_MANAGER)
            )
        except WebAuthError as err:
            # Passwort geändert: HA startet daraufhin den Reauth-Flow.
            raise ConfigEntryAuthFailed(str(err)) from err
        except WebError as err:
            raise UpdateFailed(str(err)) from err
        return data

    async def async_write(self, config_id: str, value_type: str, value: Any) -> None:
        """Datenpunkt schreiben, danach sofortiger Refresh."""
        if self._device_id is None:
            raise HomeAssistantError("Webinterface nicht verbunden")
        device_id = (
            MANAGER_DEVICE_ID if config_id in WEB_DATAPOINTS_MANAGER else self._device_id
        )
        try:
            await self._client.async_write(device_id, config_id, value_type, value)
        except WebError as err:
            raise HomeAssistantError(str(err)) from err
        await self.async_request_refresh()

    async def async_write_curve_point(self, config_id: str, x: float, y: float) -> None:
        """Einen Stützpunkt einer Kurve (Heiz- oder Kühlkurve) ändern.

        Die Kurve wird nur als Ganzes geschrieben. Deshalb vorher frisch lesen,
        damit eine zwischenzeitliche Änderung in der Web-Oberfläche nicht mit
        dem Stand des letzten Polls überschrieben wird.
        """
        if self._device_id is None:
            raise HomeAssistantError("Webinterface nicht verbunden")
        try:
            values = await self._client.async_read(self._device_id, [config_id])
        except WebError as err:
            raise HomeAssistantError(str(err)) from err
        curve = values.get(config_id)
        points = (curve or {}).get("CurveValues") or []
        point = next((p for p in points if p.get("XValue") == x), None)
        if point is None:
            raise HomeAssistantError(f"Kurve hat keinen Stützpunkt bei {x:g} °C")
        point["YValue"] = y
        await self.async_write(config_id, TYPE_CURVE, curve)
