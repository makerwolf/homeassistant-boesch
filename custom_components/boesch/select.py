"""Select-Plattform: schreibbare Modi/Enums (R/W)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
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
    """Select-Entities aus dem Registermodell erzeugen."""
    entities: list[BoeschSelect] = []
    for coordinator in entry.runtime_data.coordinators.values():
        for reg in coordinator.regs:
            if reg.kind is Kind.SELECT:
                entities.append(BoeschSelect(coordinator, reg, entry))
    assign_entity_ids(entities, "select")
    async_add_entities(entities)


class BoeschSelect(BoeschEntity, SelectEntity):
    """Schreibbarer Modus (Klartext ↔ Registercode)."""

    def __init__(self, coordinator, reg: Reg, entry) -> None:
        super().__init__(coordinator, reg, entry)
        self._attr_options = list(reg.options.values())
        # Rückabbildung Klartext -> Registercode.
        self._code_by_option = {label: code for code, label in reg.options.items()}

    @property
    def current_option(self) -> str | None:
        value = self._value
        if value is None:
            return None
        return self._reg.options.get(int(value))

    async def async_select_option(self, option: str) -> None:
        code = self._code_by_option[option]
        await self.coordinator.async_write(self._reg, code)
