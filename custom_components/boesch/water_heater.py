"""Water-Heater-Plattform: Trinkwassererwärmung (TWE).

Bündelt die TWE-Register zu einer Entity:
- native_current_temperature = TWE Ist (100)
- native_target_temperature  = TWE konstanter Sollwert (102, schreibbar 0-85 °C)
- operation mode       = Einmalladung (103): "normal" / "one_time_charge"

Der Einmalladungs-Zielwert (104) bleibt eine separate number-Entity daneben.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.water_heater import WaterHeaterEntity
from homeassistant.components.water_heater.const import WaterHeaterEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BoeschConfigEntry
from .coordinator import BoeschCoordinator
from .entity import BoeschEntity, assign_entity_ids
from .registers import Reg

# Register-Keys, die die water_heater-Entity bündelt.
KEY_CURRENT = "boesch_hb_twe_ist"          # 100
KEY_TARGET = "boesch_hb_twe_konst_soll"    # 102 (Anker)
KEY_BOOST = "boesch_hb_twe_einmalladung"   # 103

OP_NORMAL = "normal"
OP_BOOST = "one_time_charge"


# Schreibzugriffe nacheinander (eine gemeinsame Modbus-/Web-Verbindung).
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BoeschConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Die TWE-water_heater-Entity erzeugen (an ihren Coordinator gebunden)."""
    for coordinator in entry.runtime_data.coordinators.values():
        regs_by_key = {r.key: r for r in coordinator.regs}
        if KEY_TARGET in regs_by_key:
            entities = [BoeschWaterHeater(coordinator, regs_by_key[KEY_TARGET], entry)]
            assign_entity_ids(entry, entities, "water_heater")
            async_add_entities(entities)
            return


class BoeschWaterHeater(BoeschEntity, WaterHeaterEntity):
    """Trinkwassererwärmung als water_heater-Entity."""

    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        WaterHeaterEntityFeature.TARGET_TEMPERATURE
        | WaterHeaterEntityFeature.OPERATION_MODE
    )

    def __init__(
        self, coordinator: BoeschCoordinator, target_reg: Reg, entry: ConfigEntry
    ) -> None:
        # Anker = Zielwert-Register (102) — liefert device_info + Verfügbarkeit.
        super().__init__(coordinator, target_reg, entry)
        self._attr_unique_id = "boesch_hb_twe"
        self._attr_operation_list = [OP_NORMAL, OP_BOOST]
        self._attr_translation_key = "hb_twe"
        self._target_reg = target_reg
        self._boost_reg = {r.key: r for r in coordinator.regs}[KEY_BOOST]
        if target_reg.min_value is not None:
            self._attr_min_temp = target_reg.min_value
        if target_reg.max_value is not None:
            self._attr_max_temp = target_reg.max_value
        self._attr_target_temperature_step = target_reg.scale

    @property
    def native_current_temperature(self) -> float | None:
        return self.coordinator.data.get(KEY_CURRENT)

    @property
    def native_target_temperature(self) -> float | None:
        return self.coordinator.data.get(self._target_reg.key)

    @property
    def current_operation(self) -> str | None:
        value = self.coordinator.data.get(self._boost_reg.key)
        if value is None:
            return None
        return OP_BOOST if value > 0 else OP_NORMAL

    # HA < 2026.11 kennt die native_*-Namen noch nicht. Der Block läuft dort
    # nur, damit 2026.9/2026.10 weiter funktionieren; ab 2026.11 wird er
    # übersprungen (sonst gäbe es dort die Deprecation-Warnung).
    if not hasattr(WaterHeaterEntity, "native_temperature_unit"):
        _attr_temperature_unit = UnitOfTemperature.CELSIUS  # type: ignore[misc, unused-ignore]
        current_temperature = property(  # type: ignore[misc, assignment, unused-ignore]
            lambda self: self.native_current_temperature
        )
        target_temperature = property(  # type: ignore[misc, assignment, unused-ignore]
            lambda self: self.native_target_temperature
        )

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None:
            await self.coordinator.async_write(self._target_reg, temperature)

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        await self.coordinator.async_write(
            self._boost_reg, 1 if operation_mode == OP_BOOST else 0
        )
