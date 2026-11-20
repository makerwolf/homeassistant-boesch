"""Sensor-Plattform: numerische Messwerte und Enum-Klartext-Sensoren."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BoeschConfigEntry
from .const import CONF_AI_INPUTS
from .coordinator import BoeschCoordinator, BoeschWebCoordinator, firmware_key
from .energy import build_energy_entities
from .entity import BoeschEntity, BoeschWebEntity, FineCurveEntity, assign_entity_ids
from .fine_curve import FineCurveCoordinator
from .registers import DeviceKey, Kind, Reg
from .web_client import (
    DP_HK1_MIXER_POSITION,
    DP_SEASON_OUTDOOR_TEMPERATURE,
    DP_UPDATE_INFO,
    DP_UPDATE_PROGRESS,
    DP_UPDATE_STATE,
)

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
        entities.append(BoeschWebUpdateState(web, entry))
        entities.append(BoeschWebUpdateProgress(web, entry))
        entities.append(BoeschWebUpdateInfo(web, entry))
        for device, key in _FIRMWARE.items():
            entities.append(BoeschWebFirmware(web, entry, device, key))
    if fine := entry.runtime_data.fine:
        entities.append(FineCurveSetpoint(fine, entry))

    assign_entity_ids(entry, entities, "sensor")
    async_add_entities(entities)


class BoeschSensor(BoeschEntity, SensorEntity):
    """Numerischer Messwert."""

    def __init__(
        self,
        coordinator: BoeschCoordinator,
        reg: Reg,
        entry: ConfigEntry,
        name: str | None = None,
    ) -> None:
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

    def __init__(
        self, coordinator: BoeschCoordinator, reg: Reg, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, reg, entry)
        self._options = reg.options or {}
        self._attr_options = list(self._options.values())

    @property
    def native_value(self) -> str | None:
        value = self._value
        if value is None:
            return None
        return self._options.get(int(value))


class BoeschWebMixer(BoeschWebEntity, SensorEntity):
    """Mischer-Öffnung HK1 (nur im Webinterface, nicht in der Modbus-Liste)."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: BoeschWebCoordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            "boesch_hb_hk1_mischer",
            DP_HK1_MIXER_POSITION,
        )

    @property
    def native_value(self) -> float | None:
        value = self._value
        return None if value is None else float(value)


class BoeschWebSeasonTemperature(BoeschWebEntity, SensorEntity):
    """Saison-Außentemperatur: Grundlage der Sommer-/Winter-/Kühl-Umschaltung."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: BoeschWebCoordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            "boesch_hb_saison_aussentemperatur",
            DP_SEASON_OUTDOOR_TEMPERATURE,
        )

    @property
    def native_value(self) -> float | None:
        # Kommt als ungerundeter Float (z. B. 4.716547).
        value = self._value
        return None if value is None else round(float(value), 2)


# Firmware-Sensor je Gerät: Gerät -> unique_id.
_FIRMWARE = {
    DeviceKey.MANAGER: "boesch_wpm_firmware",
    DeviceKey.WANDA: "boesch_wanda_firmware",
    DeviceKey.HYDROBOX: "boesch_hb_firmware",
}


class BoeschWebFirmware(BoeschWebEntity, SensorEntity):
    """Firmware-Version eines Geräts (Verlauf zeigt vergangene Updates)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: BoeschWebCoordinator,
        entry: ConfigEntry,
        device: DeviceKey,
        key: str,
    ) -> None:
        super().__init__(coordinator, entry, key, firmware_key(device), device)

    @property
    def native_value(self) -> str | None:
        value = self._value
        return None if value is None else str(value)


# Softwareupdate-Status (PossibleValues "UpdateState" der Firmware IFM 1.6.5.44).
UPDATE_STATES = {
    0: "up_to_date",
    1: "update_available",
    2: "downloading",
    3: "download_finished",
    4: "no_connection",
    5: "update_error",
    6: "version_not_found",
    7: "unpacking",
    8: "os_update",
    9: "checking",
}


class BoeschWebUpdateState(BoeschWebEntity, SensorEntity):
    """Softwareupdate-Status des Wärmepumpenmanagers (Seite "Update")."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_options = list(UPDATE_STATES.values())

    def __init__(self, coordinator: BoeschWebCoordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            "boesch_wpm_update_status",
            DP_UPDATE_STATE,
            DeviceKey.MANAGER,
        )

    @property
    def native_value(self) -> str | None:
        value = self._value
        return None if value is None else UPDATE_STATES.get(int(value))


class BoeschWebUpdateProgress(BoeschWebEntity, SensorEntity):
    """Download-Fortschritt eines laufenden Softwareupdates."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: BoeschWebCoordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            "boesch_wpm_update_fortschritt",
            DP_UPDATE_PROGRESS,
            DeviceKey.MANAGER,
        )

    @property
    def native_value(self) -> int | None:
        value = self._value
        return None if value is None else int(value)


class BoeschWebUpdateInfo(BoeschWebEntity, SensorEntity):
    """Infotext während eines Updates (sonst leer -> unbekannt)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: BoeschWebCoordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            "boesch_wpm_update_info",
            DP_UPDATE_INFO,
            DeviceKey.MANAGER,
        )

    @property
    def native_value(self) -> str | None:
        return self._value or None


class FineCurveSetpoint(FineCurveEntity, SensorEntity):
    """Berechneter Festwert der feinen Heizkurve (was geschrieben wird/würde)."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: FineCurveCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "boesch_hb_hk1_fein_festwert")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.output

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.coordinator.attributes()
