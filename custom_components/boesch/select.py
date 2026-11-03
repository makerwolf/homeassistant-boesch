"""Select-Plattform: schreibbare Modi/Enums (R/W)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BoeschConfigEntry
from .entity import BoeschEntity, BoeschWebEntity, assign_entity_ids
from .registers import Kind, Reg
from .web_client import DP_HK1_HEATING_WATER_MODE, TYPE_INT32

# Heizmodus HK1 (Texte wie im Webinterface).
HEIZMODUS = {0: "Außentemperaturkurve", 1: "Festwert", 2: "Aus"}


# Schreibzugriffe nacheinander (eine gemeinsame Modbus-/Web-Verbindung).
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BoeschConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Select-Entities aus dem Registermodell erzeugen."""
    entities: list[SelectEntity] = []
    for coordinator in entry.runtime_data.coordinators.values():
        for reg in coordinator.regs:
            if reg.kind is Kind.SELECT:
                entities.append(BoeschSelect(coordinator, reg, entry))
    if web := entry.runtime_data.web:
        entities.append(BoeschWebHeizmodus(web, entry))
    assign_entity_ids(entry, entities, "select")
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


class BoeschWebHeizmodus(BoeschWebEntity, SelectEntity):
    """Heizmodus HK1: Sollwert aus Außentemperaturkurve oder Festwert."""

    _attr_icon = "mdi:home-thermometer"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(
            coordinator,
            entry,
            "boesch_hb_hk1_heizmodus",
            "HB HK1 Heizmodus",
            DP_HK1_HEATING_WATER_MODE,
        )
        self._attr_options = list(HEIZMODUS.values())
        self._code_by_option = {label: code for code, label in HEIZMODUS.items()}

    @property
    def current_option(self) -> str | None:
        value = self._value
        return None if value is None else HEIZMODUS.get(int(value))

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_write(
            self._config_id, TYPE_INT32, self._code_by_option[option]
        )
