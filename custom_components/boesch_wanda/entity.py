"""Gemeinsame Entity-Basisklasse."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL_HYDROBOX, MODEL_WANDA
from .coordinator import BoeschCoordinator
from .registers import DeviceKey, Reg

_MODEL_BY_DEVICE = {
    DeviceKey.WANDA: MODEL_WANDA,
    DeviceKey.HYDROBOX: MODEL_HYDROBOX,
}

_DEVICE_NAME = {
    DeviceKey.WANDA: "Bösch WANDA",
    DeviceKey.HYDROBOX: "Bösch Hydrobox",
}


class BoeschEntity(CoordinatorEntity[BoeschCoordinator]):
    """Basis für alle Bösch-Entities.

    Behält den ursprünglichen Namen bei (Entity-ID-Kontinuität) und hängt die
    Entity an das passende Gerät (WANDA oder Hydrobox) im Device-Registry.
    """

    _attr_has_entity_name = False

    def __init__(
        self, coordinator: BoeschCoordinator, reg: Reg, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._reg = reg
        self._attr_unique_id = reg.key
        self._attr_name = reg.name
        if reg.icon:
            self._attr_icon = reg.icon
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{reg.device.value}")},
            name=_DEVICE_NAME[reg.device],
            manufacturer=MANUFACTURER,
            model=_MODEL_BY_DEVICE[reg.device],
        )

    @property
    def _value(self) -> float | int | None:
        """Aktueller dekodierter Registerwert (oder None)."""
        return self.coordinator.data.get(self._reg.key)

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.coordinator.data.get(self._reg.key) is not None
        )
