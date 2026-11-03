"""Gemeinsame Entity-Basisklasse."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL_HYDROBOX, MODEL_MANAGER, MODEL_WANDA
from .coordinator import BoeschCoordinator, BoeschWebCoordinator
from .registers import DeviceKey, Reg

if TYPE_CHECKING:
    from . import BoeschConfigEntry

_MODEL_BY_DEVICE = {
    DeviceKey.WANDA: MODEL_WANDA,
    DeviceKey.HYDROBOX: MODEL_HYDROBOX,
    DeviceKey.MANAGER: MODEL_MANAGER,
}



def translation_key(unique_id: str) -> str:
    """translation_key einer Entity: unique_id ohne "boesch_"-Präfix.

    Namen, Zustände und Icons stehen in translations/*.json bzw. icons.json
    unter diesem Schlüssel (z. B. sensor.wanda_b16_vorlauf).
    """
    return unique_id.removeprefix("boesch_")


def assign_entity_ids(
    entry: BoeschConfigEntry, entities: Iterable[Entity], platform: str
) -> None:
    """entity_id = <platform>.<unique_id> setzen und die Entity vormerken.

    Damit erhalten NEUE Installationen direkt das kompakte boesch_-Schema
    (z. B. sensor.boesch_wanda_b16_vorlauf) statt der aus dem Namen erzeugten
    Standard-ID. Für bereits registrierte Entities gewinnt ohnehin die Registry
    (deren IDs werden per async_migrate_entry umgezogen).

    Vorgemerkte Entities überleben das Aufräumen verwaister Registry-Einträge
    nach dem Setup (siehe __init__._async_remove_stale)."""
    for entity in entities:
        if entity.unique_id:
            entity.entity_id = f"{platform}.{entity.unique_id}"
            entry.runtime_data.entity_keys.add((platform, entity.unique_id))


def build_device_info(entry: ConfigEntry, device: DeviceKey) -> DeviceInfo:
    """DeviceInfo für WANDA bzw. Hydrobox (auch für nicht-register-gebundene
    Entities wie die abgeleiteten Energie-/Effizienzzähler)."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_{device.value}")},
        translation_key=device.value,
        manufacturer=MANUFACTURER,
        model=_MODEL_BY_DEVICE[device],
        configuration_url=f"http://{entry.data[CONF_HOST]}",
    )


class BoeschEntity(CoordinatorEntity[BoeschCoordinator]):
    """Basis für alle Bösch-Entities.

    Hängt die Entity an das passende Gerät (WANDA oder Hydrobox); der Name
    kommt übersetzt aus translation_key, relativ zum Gerät. Ein expliziter
    `name` (frei benannte Fühlereingänge) ersetzt ihn. Die Entity-ID setzt
    assign_entity_ids fest.
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
        if name:
            self._attr_name = name
        else:
            self._attr_translation_key = translation_key(reg.key)
        if reg.entity_category:
            self._attr_entity_category = EntityCategory(reg.entity_category)
        self._attr_entity_registry_enabled_default = reg.enabled_default
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
        config_id: str,
        device: DeviceKey = DeviceKey.HYDROBOX,
    ) -> None:
        super().__init__(coordinator)
        self._config_id = config_id
        self._attr_unique_id = key
        self._attr_translation_key = translation_key(key)
        self._attr_device_info = build_device_info(entry, device)

    @property
    def _value(self) -> Any:
        """Aktueller Rohwert des Datenpunkts (oder None)."""
        return (self.coordinator.data or {}).get(self._config_id)

    @property
    def available(self) -> bool:
        return super().available and self._value is not None
