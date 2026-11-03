"""Number-Plattform: schreibbare numerische Sollwerte (R/W)."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BoeschConfigEntry
from .entity import BoeschEntity, BoeschWebEntity, assign_entity_ids
from .registers import Kind, Reg
from .web_client import (
    DP_HK1_COOLING_CURVE,
    DP_HK1_FIXED_SETPOINT_COOLING,
    DP_HK1_FIXED_SETPOINT_HEATING,
    DP_HK1_HEATING_CURVE,
    TYPE_SINGLE,
)

# Außentemperaturen der Kurven-Stützpunkte (fest in der Kermi-Firmware).
CURVE_X = (-20, -15, -10, -5, 0, 5, 10, 15, 20)
COOLING_CURVE_X = (15, 25, 30, 35, 40)


# Schreibzugriffe nacheinander (eine gemeinsame Modbus-/Web-Verbindung).
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BoeschConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Number-Entities aus dem Registermodell erzeugen."""
    entities: list[NumberEntity] = []
    for coordinator in entry.runtime_data.coordinators.values():
        for reg in coordinator.regs:
            if reg.kind is Kind.NUMBER:
                entities.append(BoeschNumber(coordinator, reg, entry))
    if web := entry.runtime_data.web:
        entities.append(
            BoeschWebFixedSetpoint(
                web, entry, "boesch_hb_hk1_festwert", "HB HK1 Festwert Heizen",
                DP_HK1_FIXED_SETPOINT_HEATING, 0.0, 100.0, "mdi:thermometer-lines",
            )
        )
        entities.append(
            BoeschWebFixedSetpoint(
                web, entry, "boesch_hb_hk1_festwert_kuehlen", "HB HK1 Festwert Kühlen",
                DP_HK1_FIXED_SETPOINT_COOLING, 5.0, 30.0, "mdi:snowflake-thermometer",
            )
        )
        entities.extend(
            BoeschWebCurvePoint(web, entry, DP_HK1_HEATING_CURVE, "heizkurve", "Heizkurve", x)
            for x in CURVE_X
        )
        # Kühlkurve: Grenzen wie beim Festwert Kühlen (5-30 °C).
        entities.extend(
            BoeschWebCurvePoint(
                web, entry, DP_HK1_COOLING_CURVE, "kuehlkurve", "Kühlkurve", x,
                5.0, 30.0,
            )
            for x in COOLING_CURVE_X
        )
    assign_entity_ids(entry, entities, "number")
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


class BoeschWebFixedSetpoint(BoeschWebEntity, NumberEntity):
    """Konstanter Vorlauf-Sollwert HK1 Heizen/Kühlen (wirkt bei Heizmodus "Festwert")."""

    _attr_mode = NumberMode.BOX
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_step = 0.5

    def __init__(
        self, coordinator, entry, key: str, name: str, config_id: str,
        min_value: float, max_value: float, icon: str,
    ) -> None:
        super().__init__(coordinator, entry, key, name, config_id)
        # Grenzen wie in der Web-Oberfläche.
        self._attr_native_min_value = min_value
        self._attr_native_max_value = max_value
        self._attr_icon = icon

    @property
    def native_value(self) -> float | None:
        return self._value

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_write(self._config_id, TYPE_SINGLE, value)


class BoeschWebCurvePoint(BoeschWebEntity, NumberEntity):
    """Ein Stützpunkt einer Kurve HK1: Vorlauf-Sollwert bei Außentemperatur x."""

    _attr_mode = NumberMode.BOX
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_step = 0.5
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:chart-bell-curve-cumulative"

    def __init__(
        self, coordinator, entry, config_id: str, slug: str, label: str, x: int,
        min_value: float = 0.0, max_value: float = 100.0,
    ) -> None:
        suffix = f"m{-x}" if x < 0 else f"p{x}" if x > 0 else "0"
        super().__init__(
            coordinator,
            entry,
            f"boesch_hb_hk1_{slug}_{suffix}",
            f"HB HK1 {label} bei {x} °C",
            config_id,
        )
        self._x = x
        # Die Firmware gibt für Kurven keine Grenzen vor -> wie beim Festwert.
        self._attr_native_min_value = min_value
        self._attr_native_max_value = max_value

    @property
    def native_value(self) -> float | None:
        points = (self._value or {}).get("CurveValues") or []
        return next((p["YValue"] for p in points if p.get("XValue") == self._x), None)

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_write_curve_point(self._config_id, self._x, value)
