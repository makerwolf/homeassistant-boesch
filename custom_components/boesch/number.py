"""Number-Plattform: schreibbare numerische Sollwerte (R/W)."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BoeschConfigEntry
from .entity import BoeschEntity, assign_entity_ids
from .registers import Kind, Reg


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BoeschConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Number-Entities aus dem Registermodell erzeugen."""
    entities: list[BoeschNumber] = []
    for coordinator in entry.runtime_data.coordinators.values():
        for reg in coordinator.regs:
            if reg.kind is Kind.NUMBER:
                entities.append(BoeschNumber(coordinator, reg, entry))
    assign_entity_ids(entities, "number")
    async_add_entities(entities)


class BoeschNumber(BoeschEntity, NumberEntity):
    """Schreibbarer Sollwert."""

    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, reg: Reg, entry) -> None:
        super().__init__(coordinator, reg, entry)
        self._attr_native_unit_of_measurement = reg.unit
        if reg.device_class:
            self._attr_device_class = NumberDeviceClass(reg.device_class)
        if reg.min_value is not None:
            self._attr_native_min_value = reg.min_value
        if reg.max_value is not None:
            self._attr_native_max_value = reg.max_value
        # Schrittweite = Geräteauflösung (scale): 0.1 bei Zehntel-Registern, sonst 1.
        self._attr_native_step = reg.scale

    @property
    def native_value(self) -> float | int | None:
        return self._value

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_write(self._reg, value)
