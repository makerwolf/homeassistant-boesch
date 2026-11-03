"""Binary-Sensor-Plattform: 0/1-Flags (ersetzt die Template-Binary-Sensoren).

Zusätzlich wird aus dem numerischen AlarmCode (Register 250) eine
Problem-Binary abgeleitet — beide teilen sich denselben Modbus-Read.
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.binary_sensor.const import BinarySensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BoeschConfigEntry
from .coordinator import BoeschCoordinator
from .entity import BoeschEntity, assign_entity_ids
from .registers import Kind, Reg

# Abgeleitete Binaries teilen sich den Read eines bestehenden Sensor-Registers.
_ALARM_SOURCE_KEY = "boesch_wanda_alarmcode"
# "Verdichter läuft" aus el. Leistung: Register 152 ist die Laufzeit seit Start,
# kein Flag (steht im TWE-Betrieb auf 0). el. Leistung > 0 gilt über alle Betriebsarten.
_COMPRESSOR_SOURCE_KEY = "boesch_wanda_el_leistung"
_COMPRESSOR_ON_KW = 0.1


# Nur lesend; die Coordinators übernehmen das Pollen.
PARALLEL_UPDATES = 0


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
            if reg.key == _COMPRESSOR_SOURCE_KEY:
                entities.append(BoeschCompressorBinarySensor(coordinator, reg, entry))
    assign_entity_ids(entry, entities, "binary_sensor")
    async_add_entities(entities)


class BoeschBinarySensor(BoeschEntity, BinarySensorEntity):
    """0/1-Flag als Binary-Sensor (is_on = value > on_threshold)."""

    def __init__(
        self, coordinator: BoeschCoordinator, reg: Reg, entry: ConfigEntry
    ) -> None:
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

    def __init__(
        self, coordinator: BoeschCoordinator, reg: Reg, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, reg, entry)
        # Eigene unique_id/Name, nicht die des Quell-Sensors.
        self._attr_unique_id = "boesch_wanda_alarm_bs"
        self._attr_translation_key = "wanda_alarm_bs"

    @property
    def is_on(self) -> bool | None:
        value = self._value
        if value is None:
            return None
        return value > 0


class BoeschCompressorBinarySensor(BoeschEntity, BinarySensorEntity):
    """Verdichter läuft, abgeleitet aus der el. Leistung (>0)."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(
        self, coordinator: BoeschCoordinator, reg: Reg, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, reg, entry)
        # Eigene unique_id/Name, nicht die des Quell-Sensors (el. Leistung).
        self._attr_unique_id = "boesch_wanda_verdichter_laeuft"
        self._attr_translation_key = "wanda_verdichter_laeuft"

    @property
    def is_on(self) -> bool | None:
        value = self._value  # el. Leistung akt (kW)
        if value is None:
            return None
        return value > _COMPRESSOR_ON_KW
