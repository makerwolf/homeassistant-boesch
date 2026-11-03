"""Abgeleitete Energie- und Effizienzsensoren (nicht register-gebunden).

- Energiezähler: integrieren eine Leistung (kW) trapezförmig über die Zeit zu
  kWh. Kumulativ (`total_increasing`), neustartfest via RestoreSensor —
  geeignet fürs Energy Dashboard (KEIN täglicher Reset; das Dashboard
  periodisiert selbst, siehe README/utility_meter).
- JAZ/Arbeitszahl: laufendes Verhältnis Wärmemenge_kWh / Stromenergie_kWh.

Alle Quellregister (Leistungen 104–111) liegen in der LIVE-Poll-Gruppe, also
in EINEM Coordinator — daran werden die Sensoren gebunden.
"""

from __future__ import annotations

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .coordinator import BoeschCoordinator
from .entity import build_device_info, short_name
from .registers import DeviceKey

# (Zähler-key, Name, Quell-Leistungsregister-key)
ELECTRICAL_ENERGY: list[tuple[str, str, str]] = [
    ("boesch_wanda_energie_el_gesamt", "WP Stromverbrauch gesamt", "boesch_wanda_el_leistung"),
    ("boesch_wanda_energie_el_heizen", "WP Stromverbrauch Heizen", "boesch_wanda_el_leistung_heizen"),
    ("boesch_wanda_energie_el_twe", "WP Stromverbrauch TWE", "boesch_wanda_el_leistung_twe"),
    ("boesch_wanda_energie_el_kuehlen", "WP Stromverbrauch Kühlen", "boesch_wanda_el_leistung_kuehlen"),
]
THERMAL_ENERGY: list[tuple[str, str, str]] = [
    ("boesch_wanda_energie_th_gesamt", "WP Wärmemenge gesamt", "boesch_wanda_leistung"),
    ("boesch_wanda_energie_th_heizen", "WP Wärmemenge Heizen", "boesch_wanda_leistung_heizen"),
    ("boesch_wanda_energie_th_twe", "WP Wärmemenge TWE", "boesch_wanda_leistung_twe"),
    ("boesch_wanda_energie_th_kuehlen", "WP Wärmemenge Kühlen", "boesch_wanda_leistung_kuehlen"),
]
# (JAZ-key, Name, Wärmemenge-key, Stromenergie-key)
SCOP: list[tuple[str, str, str, str]] = [
    ("boesch_wanda_jaz_gesamt", "WP Arbeitszahl gesamt", "boesch_wanda_energie_th_gesamt", "boesch_wanda_energie_el_gesamt"),
    ("boesch_wanda_jaz_heizen", "WP Arbeitszahl Heizen", "boesch_wanda_energie_th_heizen", "boesch_wanda_energie_el_heizen"),
    ("boesch_wanda_jaz_twe", "WP Arbeitszahl TWE", "boesch_wanda_energie_th_twe", "boesch_wanda_energie_el_twe"),
    ("boesch_wanda_jaz_kuehlen", "WP Arbeitszahl Kühlen", "boesch_wanda_energie_th_kuehlen", "boesch_wanda_energie_el_kuehlen"),
]

# Ab dieser Stromenergie liefern die JAZ-Sensoren einen Wert (genug Datenbasis).
_SCOP_MIN_KWH = 0.05


class BoeschEnergySensor(CoordinatorEntity[BoeschCoordinator], RestoreSensor):
    """Trapezförmige Zeit-Integration einer Leistung (kW) zu Energie (kWh)."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2
    _attr_has_entity_name = True
    _attr_icon = "mdi:counter"

    def __init__(
        self,
        coordinator: BoeschCoordinator,
        entry: ConfigEntry,
        key: str,
        name: str,
        source_key: str,
    ) -> None:
        super().__init__(coordinator)
        self._source_key = source_key
        self._attr_unique_id = key
        self._attr_name = short_name(name)
        self._attr_device_info = build_device_info(entry, DeviceKey.WANDA)
        self._energy: float = 0.0
        self._last_power: float | None = None
        self._last_time = None

    @property
    def energy(self) -> float:
        """Aktueller kumulativer Zählerstand in kWh (für JAZ-Sensoren)."""
        return self._energy

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_sensor_data()
        if last is not None and last.native_value is not None:
            try:
                self._energy = float(last.native_value)
            except (TypeError, ValueError):
                self._energy = 0.0
        # Timing initialisieren, ohne die Lücke seit Neustart zu integrieren.
        self._last_power = self.coordinator.data.get(self._source_key)
        self._last_time = dt_util.utcnow()

    @callback
    def _handle_coordinator_update(self) -> None:
        # Nach einem fehlgeschlagenen Poll stehen in `data` noch die alten Werte.
        # Wie "unavailable" behandeln, sonst würde beim nächsten Erfolg die
        # ganze Ausfallzeit mit der alten Leistung mitintegriert.
        power = (
            self.coordinator.data.get(self._source_key)  # kW
            if self.coordinator.last_update_success
            else None
        )
        now = dt_util.utcnow()
        if power is not None:
            if self._last_power is not None and self._last_time is not None:
                hours = (now - self._last_time).total_seconds() / 3600.0
                if hours > 0:
                    self._energy += (self._last_power + power) / 2.0 * hours
            self._last_power = power
            self._last_time = now
        else:
            # Quelle unavailable oder Poll fehlgeschlagen: Lücke nicht integrieren.
            self._last_power = None
            self._last_time = now
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> float:
        return round(self._energy, 3)


class BoeschSCOPSensor(CoordinatorEntity[BoeschCoordinator], SensorEntity):
    """Laufende Arbeitszahl = Wärmemenge / Stromenergie (dimensionslos)."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2
    _attr_has_entity_name = True
    _attr_icon = "mdi:gauge"

    def __init__(
        self,
        coordinator: BoeschCoordinator,
        entry: ConfigEntry,
        key: str,
        name: str,
        thermal: BoeschEnergySensor,
        electrical: BoeschEnergySensor,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = key
        self._attr_name = short_name(name)
        self._attr_device_info = build_device_info(entry, DeviceKey.WANDA)
        self._thermal = thermal
        self._electrical = electrical

    @property
    def native_value(self) -> float | None:
        electrical = self._electrical.energy
        if electrical > _SCOP_MIN_KWH:
            return round(self._thermal.energy / electrical, 2)
        return None


def build_energy_entities(
    coordinator: BoeschCoordinator, entry: ConfigEntry
) -> list[SensorEntity]:
    """Energiezähler + JAZ-Sensoren erzeugen (an den LIVE-Coordinator gebunden)."""
    entities: list[SensorEntity] = []
    by_key: dict[str, BoeschEnergySensor] = {}
    for key, name, source_key in ELECTRICAL_ENERGY + THERMAL_ENERGY:
        sensor = BoeschEnergySensor(coordinator, entry, key, name, source_key)
        by_key[key] = sensor
        entities.append(sensor)
    for key, name, thermal_key, electrical_key in SCOP:
        entities.append(
            BoeschSCOPSensor(
                coordinator, entry, key, name, by_key[thermal_key], by_key[electrical_key]
            )
        )
    return entities
