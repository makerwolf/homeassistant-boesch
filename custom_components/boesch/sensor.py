"""Sensor-Plattform: numerische Messwerte und Enum-Klartext-Sensoren."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BoeschConfigEntry
from .const import CONF_AI_INPUTS
from .energy import build_energy_entities
from .entity import BoeschEntity, BoeschWebEntity, assign_entity_ids
from .registers import Kind, Reg
from .web_client import DP_HK1_MIXER_POSITION, DP_SEASON_OUTDOOR_TEMPERATURE

# Quellregister, an dem der LIVE-Coordinator für die Energiezähler erkannt wird.
_ENERGY_SOURCE_KEY = "boesch_wanda_el_leistung"

_STATE_CLASS = {
    "measurement": SensorStateClass.MEASUREMENT,
    "total_increasing": SensorStateClass.TOTAL_INCREASING,
}


# Nur lesend; die Coordinators übernehmen das Pollen.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BoeschConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Sensor-Entities aus dem Registermodell erzeugen."""
    ai_names: dict[str, str] = entry.options.get(CONF_AI_INPUTS, {})
    entities: list[SensorEntity] = []
    for coordinator in entry.runtime_data.coordinators.values():
        for reg in coordinator.regs:
            if reg.kind is Kind.SENSOR:
                if reg.configurable:
                    # Frei belegbarer Eingang: nur anlegen, wenn benannt/aktiviert.
                    name = ai_names.get(reg.key)
                    if not name:
                        continue
                    entities.append(BoeschSensor(coordinator, reg, entry, name=name))
                else:
                    entities.append(BoeschSensor(coordinator, reg, entry))
            elif reg.kind is Kind.ENUM:
                entities.append(BoeschEnumSensor(coordinator, reg, entry))

    # Abgeleitete Energie- + JAZ-Sensoren an den Coordinator mit den Leistungen.
    for coordinator in entry.runtime_data.coordinators.values():
        if any(r.key == _ENERGY_SOURCE_KEY for r in coordinator.regs):
            entities.extend(build_energy_entities(coordinator, entry))
            break

    if web := entry.runtime_data.web:
        entities.append(BoeschWebMixer(web, entry))
        entities.append(BoeschWebSeasonTemperature(web, entry))

    assign_entity_ids(entities, "sensor")
    async_add_entities(entities)


class BoeschSensor(BoeschEntity, SensorEntity):
    """Numerischer Messwert."""

    def __init__(self, coordinator, reg: Reg, entry, name: str | None = None) -> None:
        super().__init__(coordinator, reg, entry, name=name)
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


class BoeschWebMixer(BoeschWebEntity, SensorEntity):
    """Mischer-Öffnung HK1 (nur im Webinterface, nicht in der Modbus-Liste)."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:valve"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(
            coordinator,
            entry,
            "boesch_hb_hk1_mischer",
            "HB HK1 Mischer-Öffnung",
            DP_HK1_MIXER_POSITION,
        )

    @property
    def native_value(self) -> float | None:
        return self._value


class BoeschWebSeasonTemperature(BoeschWebEntity, SensorEntity):
    """Saison-Außentemperatur: Grundlage der Sommer-/Winter-/Kühl-Umschaltung."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator, entry) -> None:
        super().__init__(
            coordinator,
            entry,
            "boesch_hb_saison_aussentemperatur",
            "HB Saison-Außentemperatur",
            DP_SEASON_OUTDOOR_TEMPERATURE,
        )

    @property
    def native_value(self) -> float | None:
        # Kommt als ungerundeter Float (z. B. 4.716547).
        value = self._value
        return None if value is None else round(value, 2)
