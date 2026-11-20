"""Switch-Plattform: schreibbare 0/1-Flags (R/W)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BoeschConfigEntry
from .coordinator import BoeschCoordinator, BoeschWebCoordinator
from .entity import BoeschEntity, BoeschWebEntity, FineCurveEntity, assign_entity_ids
from .fine_curve import FineCurveCoordinator
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
    if fine := entry.runtime_data.fine:
        entities.append(FineCurveActive(fine, entry))
    assign_entity_ids(entry, entities, "switch")
    async_add_entities(entities)


class BoeschSwitch(BoeschEntity, SwitchEntity):
    """Schreibbares 0/1-Flag."""

    def __init__(
        self, coordinator: BoeschCoordinator, reg: Reg, entry: ConfigEntry
    ) -> None:
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

    def __init__(self, coordinator: BoeschWebCoordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            "boesch_wpm_anwesenheit",
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


class FineCurveActive(FineCurveEntity, SwitchEntity):
    """Feine Heizkurve aktiv: an = Heizmodus "fixed", aus = zurück auf "curve"."""

    def __init__(self, coordinator: FineCurveCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "boesch_hb_hk1_feinkurve_aktiv")

    @property
    def is_on(self) -> bool:
        return self.coordinator.active

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_activate()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_deactivate()
