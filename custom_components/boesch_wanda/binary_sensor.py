"""Binary-Sensor-Plattform: 0/1-Flags (ersetzt die Template-Binary-Sensoren).

Zusätzlich wird aus dem numerischen AlarmCode (Register 250) eine
Problem-Binary abgeleitet — beide teilen sich denselben Modbus-Read.
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BoeschConfigEntry
from .entity import BoeschEntity
from .registers import Kind, Reg

# Aus dem AlarmCode-Register abgeleitete Problem-Binary. Kein eigenes Register:
# liest denselben Schlüssel wie der AlarmCode-Sensor.
_ALARM_SOURCE_KEY = "boesch_wp_alarmcode"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BoeschConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Binary-Sensor-Entities erzeugen."""
    entities: list[BinarySensorEntity] = []
    for coordinator in entry.runtime_data.coordinators.values():
        for reg in coordinator.regs:
            if reg.kind is Kind.BINARY:
                entities.append(BoeschBinarySensor(coordinator, reg, entry))
            if reg.key == _ALARM_SOURCE_KEY:
                entities.append(BoeschAlarmBinarySensor(coordinator, reg, entry))
    async_add_entities(entities)


class BoeschBinarySensor(BoeschEntity, BinarySensorEntity):
    """0/1-Flag als Binary-Sensor (is_on = value > on_threshold)."""

    def __init__(self, coordinator, reg: Reg, entry) -> None:
        super().__init__(coordinator, reg, entry)
        if reg.device_class:
            self._attr_device_class = BinarySensorDeviceClass(reg.device_class)

    @property
    def is_on(self) -> bool | None:
        value = self._value
        if value is None:
            return None
        return value > self._reg.on_threshold


class BoeschAlarmBinarySensor(BoeschEntity, BinarySensorEntity):
    """Problem-Binary, abgeleitet aus dem AlarmCode (>0 = Alarm)."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:alert"

    def __init__(self, coordinator, reg: Reg, entry) -> None:
        super().__init__(coordinator, reg, entry)
        # Eigene unique_id/Name, nicht die des Quell-Sensors.
        self._attr_unique_id = "boesch_wp_alarm_bs"
        self._attr_name = "WP Alarm"

    @property
    def is_on(self) -> bool | None:
        value = self._value
        if value is None:
            return None
        return value > 0
