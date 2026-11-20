"""Number-Plattform: schreibbare numerische Sollwerte (R/W)."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BoeschConfigEntry
from .coordinator import BoeschCoordinator, BoeschWebCoordinator
from .entity import BoeschEntity, BoeschWebEntity, FineCurveEntity, assign_entity_ids
from .fine_curve import (
    CURVE_X,
    FIXED_SETPOINT_STEP,
    FineCurveCoordinator,
    round_setpoint,
)
from .registers import Kind, Reg
from .web_client import (
    DP_HK1_COOLING_CURVE,
    DP_HK1_FIXED_SETPOINT_COOLING,
    DP_HK1_FIXED_SETPOINT_HEATING,
    DP_HK1_HEATING_CURVE,
    TYPE_SINGLE,
)

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
                web, entry, "boesch_hb_hk1_festwert",
                DP_HK1_FIXED_SETPOINT_HEATING, 0.0, 100.0,
            )
        )
        entities.append(
            BoeschWebFixedSetpoint(
                web, entry, "boesch_hb_hk1_festwert_kuehlen",
                DP_HK1_FIXED_SETPOINT_COOLING, 5.0, 30.0,
            )
        )
        entities.extend(
            BoeschWebCurvePoint(web, entry, DP_HK1_HEATING_CURVE, "heizkurve", x)
            for x in CURVE_X
        )
        # Kühlkurve: Grenzen wie beim Festwert Kühlen (5-30 °C).
        entities.extend(
            BoeschWebCurvePoint(
                web, entry, DP_HK1_COOLING_CURVE, "kuehlkurve", x,
                5.0, 30.0,
            )
            for x in COOLING_CURVE_X
        )
    if fine := entry.runtime_data.fine:
        entities.extend(
            FineCurvePoint(fine, entry, i, x) for i, x in enumerate(CURVE_X)
        )
        entities.append(FineCurveParallel(fine, entry))
        entities.append(FineCurveZuschlag(fine, entry))
        entities.append(FineCurveBoost(fine, entry))
    assign_entity_ids(entry, entities, "number")
    async_add_entities(entities)


def _suffix(x: int) -> str:
    """Außentemperatur im Entity-Namen: -20 -> m20, 0 -> 0, 5 -> p5."""
    return f"m{-x}" if x < 0 else f"p{x}" if x > 0 else "0"


class BoeschNumber(BoeschEntity, NumberEntity):
    """Schreibbarer Sollwert."""

    _attr_mode = NumberMode.BOX

    def __init__(
        self, coordinator: BoeschCoordinator, reg: Reg, entry: ConfigEntry
    ) -> None:
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
    # Das Gerät übernimmt Zehntelgrad (33.2 geschrieben -> 33.2 gelesen,
    # getestet 2026-11-19), auch wenn die Web-UI selbst ganze Grad schickt.
    _attr_native_step = FIXED_SETPOINT_STEP

    def __init__(
        self, coordinator: BoeschWebCoordinator, entry: ConfigEntry, key: str,
        config_id: str,
        min_value: float, max_value: float,
    ) -> None:
        super().__init__(coordinator, entry, key, config_id)
        # Grenzen wie in der Web-Oberfläche.
        self._attr_native_min_value = min_value
        self._attr_native_max_value = max_value

    @property
    def native_value(self) -> float | None:
        value = self._value
        return None if value is None else float(value)

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_write(
            self._config_id, TYPE_SINGLE, round_setpoint(value)
        )


class BoeschWebCurvePoint(BoeschWebEntity, NumberEntity):
    """Ein Stützpunkt einer Kurve HK1: Vorlauf-Sollwert bei Außentemperatur x."""

    _attr_mode = NumberMode.BOX
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    # Wie die Web-Oberfläche: ganze Grad (feiner geht es nur über die
    # Option "Feine Heizkurve", siehe fine_curve.py).
    _attr_native_step = 1.0
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, coordinator: BoeschWebCoordinator, entry: ConfigEntry,
        config_id: str, slug: str, x: int,
        min_value: float = 0.0, max_value: float = 65.0,
    ) -> None:
        suffix = _suffix(x)
        super().__init__(
            coordinator, entry, f"boesch_hb_hk1_{slug}_{suffix}", config_id
        )
        # Ein Name für alle Stützpunkte, die Temperatur als Platzhalter.
        self._attr_translation_key = f"hb_hk1_{slug}"
        self._attr_translation_placeholders = {"temperature": str(x)}
        self._x = x
        # Grenzen: Heizkurve wie der Kurven-Editor der Web-Oberfläche (0-65 °C).
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


class _FineCurveNumber(FineCurveEntity, NumberEntity):
    """Gemeinsames der Einstellwerte der feinen Heizkurve (0,1 K)."""

    _attr_mode = NumberMode.BOX
    _attr_native_step = FIXED_SETPOINT_STEP


class FineCurvePoint(_FineCurveNumber):
    """Stützpunkt der feinen Heizkurve bei Außentemperatur x."""

    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 10.0
    _attr_native_max_value = 65.0

    def __init__(
        self, coordinator: FineCurveCoordinator, entry: ConfigEntry, index: int, x: int
    ) -> None:
        super().__init__(coordinator, entry, f"boesch_hb_hk1_feinkurve_{_suffix(x)}")
        self._attr_translation_key = "hb_hk1_feinkurve"
        self._attr_translation_placeholders = {"temperature": str(x)}
        self._index = index

    @property
    def native_value(self) -> float | None:
        points = self.coordinator.points
        return None if points is None else points[self._index]

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_point(self._index, value)


class FineCurveParallel(_FineCurveNumber):
    """Feine Parallelverschiebung der feinen Kurve (gespeichert)."""

    _attr_native_unit_of_measurement = UnitOfTemperature.KELVIN
    _attr_native_min_value = -5.0
    _attr_native_max_value = 5.0

    def __init__(self, coordinator: FineCurveCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "boesch_hb_hk1_fein_parallel")

    @property
    def native_value(self) -> float:
        return self.coordinator.parallel

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_parallel(value)


class FineCurveZuschlag(_FineCurveNumber):
    """Zuschlag für Automationen; läuft durch die Rampe, nach Neustart 0."""

    _attr_native_unit_of_measurement = UnitOfTemperature.KELVIN
    _attr_native_min_value = -5.0
    _attr_native_max_value = 5.0

    def __init__(self, coordinator: FineCurveCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "boesch_hb_hk1_zuschlag")

    @property
    def native_value(self) -> float:
        return self.coordinator.zuschlag

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.set_zuschlag(value)


class FineCurveBoost(_FineCurveNumber):
    """Sofort-Anhebung (WP-Anlaufhilfe): an Rampe und Filter vorbei, nach Neustart 0."""

    _attr_native_unit_of_measurement = UnitOfTemperature.KELVIN
    _attr_native_min_value = 0.0
    _attr_native_max_value = 12.0

    def __init__(self, coordinator: FineCurveCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "boesch_hb_hk1_sofort_anhebung")

    @property
    def native_value(self) -> float:
        return self.coordinator.boost

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_boost(value)
