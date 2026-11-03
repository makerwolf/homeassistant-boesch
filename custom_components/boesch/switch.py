"""Switch-Plattform: schreibbare 0/1-Flags (R/W)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BoeschConfigEntry
from .entity import BoeschEntity, BoeschWebEntity, assign_entity_ids
from .registers import DeviceKey, Kind, Reg
from .web_client import DP_SYSTEM_IS_PRESENT, TYPE_BOOLEAN

# Schreibzugriffe nacheinander (eine gemeinsame Modbus-/Web-Verbindung).
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BoeschConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Switch-Entities aus dem Registermodell erzeugen."""
    entities: list[SwitchEntity] = []
    for coordinator in entry.runtime_data.coordinators.values():
        for reg in coordinator.regs:
            if reg.kind is Kind.SWITCH:
                entities.append(BoeschSwitch(coordinator, reg, entry))
    if web := entry.runtime_data.web:
        entities.append(BoeschWebPresence(web, entry))
    assign_entity_ids(entry, entities, "switch")
    async_add_entities(entities)


class BoeschSwitch(BoeschEntity, SwitchEntity):
    """Schreibbares 0/1-Flag."""

    def __init__(self, coordinator, reg: Reg, entry) -> None:
        super().__init__(coordinator, reg, entry)

    @property
    def is_on(self) -> bool | None:
        value = self._value
        if value is None:
            return None
        return value > 0

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_write(self._reg, 1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_write(self._reg, 0)


class BoeschWebPresence(BoeschWebEntity, SwitchEntity):
    """Anwesenheitsstatus des Wärmepumpenmanagers (an = anwesend)."""

    _attr_icon = "mdi:home-account"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(
            coordinator,
            entry,
            "boesch_wpm_anwesenheit",
            "WPM Anwesenheit",
            DP_SYSTEM_IS_PRESENT,
            DeviceKey.MANAGER,
        )

    @property
    def is_on(self) -> bool | None:
        value = self._value
        return None if value is None else bool(value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_write(self._config_id, TYPE_BOOLEAN, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_write(self._config_id, TYPE_BOOLEAN, False)
