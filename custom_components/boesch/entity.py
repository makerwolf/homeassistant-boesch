"""Gemeinsame Entity-Basisklasse."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL_HYDROBOX, MODEL_MANAGER, MODEL_WANDA
from .coordinator import BoeschCoordinator, BoeschWebCoordinator
from .registers import DeviceKey, Reg

_MODEL_BY_DEVICE = {
    DeviceKey.WANDA: MODEL_WANDA,
    DeviceKey.HYDROBOX: MODEL_HYDROBOX,
    DeviceKey.MANAGER: MODEL_MANAGER,
}

_DEVICE_NAME = {
    DeviceKey.WANDA: "Bösch WANDA",
    DeviceKey.HYDROBOX: "Bösch Hydrobox",
    DeviceKey.MANAGER: "Bösch Wärmepumpenmanager",
}


# Gerätekürzel aus den historischen Namen ("WP Vorlauftemperatur B16"). Mit
# has_entity_name stellt HA den Gerätenamen ohnehin voran ("Bösch WANDA …").
_NAME_PREFIXES = ("WP ", "HB ", "WPM ")


def short_name(name: str) -> str:
    """Entity-Name ohne Gerätekürzel."""
    for prefix in _NAME_PREFIXES:
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def assign_entity_ids(entities, platform: str) -> None:
    """entity_id = <platform>.<unique_id> setzen.

    Damit erhalten NEUE Installationen direkt das kompakte boesch_-Schema
    (z. B. sensor.boesch_wanda_b16_vorlauf) statt der aus dem Namen erzeugten
    Standard-ID. Für bereits registrierte Entities gewinnt ohnehin die Registry
    (deren IDs werden per async_migrate_entry umgezogen)."""
    for entity in entities:
        if entity.unique_id:
            entity.entity_id = f"{platform}.{entity.unique_id}"


def build_device_info(entry: ConfigEntry, device: DeviceKey) -> DeviceInfo:
    """DeviceInfo für WANDA bzw. Hydrobox (auch für nicht-register-gebundene
    Entities wie die abgeleiteten Energie-/Effizienzzähler)."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_{device.value}")},
        name=_DEVICE_NAME[device],
        manufacturer=MANUFACTURER,
        model=_MODEL_BY_DEVICE[device],
    )


class BoeschEntity(CoordinatorEntity[BoeschCoordinator]):
    """Basis für alle Bösch-Entities.

    Hängt die Entity an das passende Gerät (WANDA oder Hydrobox); der Name
    ist relativ zum Gerät. Die Entity-ID setzt assign_entity_ids fest.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BoeschCoordinator,
        reg: Reg,
        entry: ConfigEntry,
        name: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._reg = reg
        self._attr_unique_id = reg.key
        self._attr_name = short_name(name or reg.name)
        if reg.icon:
            self._attr_icon = reg.icon
        if reg.entity_category:
            self._attr_entity_category = EntityCategory(reg.entity_category)
        self._attr_device_info = build_device_info(entry, reg.device)

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


class BoeschWebEntity(CoordinatorEntity[BoeschWebCoordinator]):
    """Basis für Entities aus dem Webinterface (Hydrobox oder Wärmepumpenmanager)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BoeschWebCoordinator,
        entry: ConfigEntry,
        key: str,
        name: str,
        config_id: str,
        device: DeviceKey = DeviceKey.HYDROBOX,
    ) -> None:
        super().__init__(coordinator)
        self._config_id = config_id
        self._attr_unique_id = key
        self._attr_name = short_name(name)
        self._attr_device_info = build_device_info(entry, device)

    @property
    def _value(self):
        """Aktueller Rohwert des Datenpunkts (oder None)."""
        return (self.coordinator.data or {}).get(self._config_id)

    @property
    def available(self) -> bool:
        return super().available and self._value is not None
