"""Water-Heater-Plattform: Trinkwassererwärmung (TWE).

Bündelt die TWE-Register zu einer Entity:
- current_temperature  = TWE Ist (100)
- target_temperature   = TWE konstanter Sollwert (102, schreibbar 0-85 °C)
- operation mode       = Einmalladung (103): "Normal" / "Einmalladung"

Der Einmalladungs-Zielwert (104) bleibt eine separate number-Entity daneben.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BoeschConfigEntry
from .entity import BoeschEntity

# Register-Keys, die die water_heater-Entity bündelt.
KEY_CURRENT = "boesch_hb_twe_ist"          # 100
KEY_TARGET = "boesch_hb_twe_konst_soll"    # 102 (Anker)
KEY_BOOST = "boesch_hb_twe_einmalladung"   # 103

OP_NORMAL = "Normal"
OP_BOOST = "Einmalladung"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BoeschConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Die TWE-water_heater-Entity erzeugen (an ihren Coordinator gebunden)."""
    for coordinator in entry.runtime_data.coordinators.values():
        regs_by_key = {r.key: r for r in coordinator.regs}
        if KEY_TARGET in regs_by_key:
            async_add_entities(
                [BoeschWaterHeater(coordinator, regs_by_key[KEY_TARGET], entry)]
            )
            return


class BoeschWaterHeater(BoeschEntity, WaterHeaterEntity):
    """Trinkwassererwärmung als water_heater-Entity."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        WaterHeaterEntityFeature.TARGET_TEMPERATURE
        | WaterHeaterEntityFeature.OPERATION_MODE
    )
    _attr_operation_list = [OP_NORMAL, OP_BOOST]
    _attr_icon = "mdi:water-boiler"

    def __init__(self, coordinator, target_reg, entry) -> None:
        # Anker = Zielwert-Register (102) — liefert device_info + Verfügbarkeit.
        super().__init__(coordinator, target_reg, entry)
        self._attr_unique_id = "boesch_hb_twe"
        self._attr_name = "HB Trinkwasser"
        self._target_reg = target_reg
        self._boost_reg = {r.key: r for r in coordinator.regs}[KEY_BOOST]
        self._attr_min_temp = target_reg.min_value
        self._attr_max_temp = target_reg.max_value
        self._attr_target_temperature_step = target_reg.scale

    @property
    def current_temperature(self) -> float | None:
        return self.coordinator.data.get(KEY_CURRENT)

    @property
    def target_temperature(self) -> float | None:
        return self.coordinator.data.get(self._target_reg.key)

    @property
    def current_operation(self) -> str | None:
        value = self.coordinator.data.get(self._boost_reg.key)
        if value is None:
            return None
        return OP_BOOST if value > 0 else OP_NORMAL

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None:
            await self.coordinator.async_write(self._target_reg, temperature)

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        await self.coordinator.async_write(
            self._boost_reg, 1 if operation_mode == OP_BOOST else 0
        )
