"""Energiezähler (Trapez-Integration) und Arbeitszahl, ohne laufendes HA."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

from custom_components.boesch import energy
from custom_components.boesch.energy import BoeschEnergySensor, BoeschSCOPSensor


class Clock:
    def __init__(self) -> None:
        self.now = energy.dt_util.utcnow()

    def tick(self, **kwargs) -> None:
        self.now += timedelta(**kwargs)


@pytest.fixture
def clock():
    c = Clock()
    with patch.object(energy.dt_util, "utcnow", lambda: c.now):
        yield c


@pytest.fixture
def coordinator() -> MagicMock:
    coord = MagicMock()
    coord.data = {"p": 0.0}
    coord.last_update_success = True
    return coord


def _sensor(coordinator: MagicMock) -> BoeschEnergySensor:
    sensor = BoeschEnergySensor(coordinator, MagicMock(entry_id="e"), "k", "n", "p")
    sensor.async_write_ha_state = lambda: None
    return sensor


def _poll(sensor, coordinator, power=None, *, ok=True) -> None:
    coordinator.last_update_success = ok
    if ok:
        coordinator.data = {"p": power}
    sensor._handle_coordinator_update()


def test_trapezoid(clock, coordinator) -> None:
    sensor = _sensor(coordinator)
    _poll(sensor, coordinator, 1.0)
    clock.tick(hours=1)
    _poll(sensor, coordinator, 3.0)  # Mittel 2 kW über 1 h
    assert sensor.native_value == 2.0


def test_outage_not_integrated(clock, coordinator) -> None:
    """Fehlgeschlagene Polls: die Ausfallzeit zählt nicht mit.

    HA ruft die Listener nur beim ersten Fehler auf, danach erst wieder beim
    Erfolg; `data` enthält bis dahin die alten Werte.
    """
    sensor = _sensor(coordinator)
    _poll(sensor, coordinator, 2.0)
    clock.tick(seconds=15)
    _poll(sensor, coordinator, 2.0)               # +2 kW * 15 s
    clock.tick(seconds=15)
    _poll(sensor, coordinator, ok=False)          # erster Fehler, data bleibt alt
    clock.tick(hours=1)                           # weitere Fehler ohne Listener
    _poll(sensor, coordinator, 2.0)               # Erholung: nur Neustart der Zeitbasis
    clock.tick(seconds=15)
    _poll(sensor, coordinator, 2.0)               # +2 kW * 15 s
    assert sensor.native_value == pytest.approx(2.0 * 30 / 3600, abs=1e-3)


def test_unavailable_source_skips_gap(clock, coordinator) -> None:
    sensor = _sensor(coordinator)
    _poll(sensor, coordinator, 2.0)
    clock.tick(hours=1)
    _poll(sensor, coordinator, None)
    clock.tick(hours=1)
    _poll(sensor, coordinator, 2.0)
    assert sensor.native_value == 0.0


def test_scop(coordinator) -> None:
    thermal = _sensor(coordinator)
    electrical = _sensor(coordinator)
    scop = BoeschSCOPSensor(coordinator, MagicMock(entry_id="e"), "j", "n", thermal, electrical)
    electrical._energy = 0.01  # unter der Mindest-Datenbasis
    thermal._energy = 0.04
    assert scop.native_value is None
    electrical._energy = 10.0
    thermal._energy = 42.0
    assert scop.native_value == 4.2
