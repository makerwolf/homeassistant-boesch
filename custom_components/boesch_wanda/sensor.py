"""Sensor-Plattform: numerische Messwerte und Enum-Klartext-Sensoren."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BoeschConfigEntry
from .entity import BoeschEntity
from .registers import Kind, Reg

_STATE_CLASS = {
    "measurement": SensorStateClass.MEASUREMENT,
    "total_increasing": SensorStateClass.TOTAL_INCREASING,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BoeschConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Sensor-Entities aus dem Registermodell erzeugen."""
    entities: list[BoeschEntity] = []
    for coordinator in entry.runtime_data.coordinators.values():
        for reg in coordinator.regs:
            if reg.kind is Kind.SENSOR:
                entities.append(BoeschSensor(coordinator, reg, entry))
            elif reg.kind is Kind.ENUM:
                entities.append(BoeschEnumSensor(coordinator, reg, entry))
    async_add_entities(entities)


class BoeschSensor(BoeschEntity, SensorEntity):
    """Numerischer Messwert."""

    def __init__(self, coordinator, reg: Reg, entry) -> None:
        super().__init__(coordinator, reg, entry)
        self._attr_native_unit_of_measurement = reg.unit
        if reg.device_class:
            self._attr_device_class = SensorDeviceClass(reg.device_class)
        if reg.state_class:
            self._attr_state_class = _STATE_CLASS[reg.state_class]
        if reg.precision is not None:
            self._attr_suggested_display_precision = reg.precision

    @property
    def native_value(self) -> float | int | None:
        return self._value


class BoeschEnumSensor(BoeschEntity, SensorEntity):
    """Numerischer Code, als Klartext dargestellt (ersetzt Template-Sensoren)."""

    _attr_device_class = SensorDeviceClass.ENUM

    def __init__(self, coordinator, reg: Reg, entry) -> None:
        super().__init__(coordinator, reg, entry)
        self._attr_options = list(reg.options.values())

    @property
    def native_value(self) -> str | None:
        value = self._value
        if value is None:
            return None
        return self._reg.options.get(int(value))
