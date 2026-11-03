"""Web-Entities (Kermi x-center), hochauflösende Leistung und Reauth-Auslöser."""

from __future__ import annotations

import pytest
from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.boesch.const import CONF_WEB_PASSWORD, CONF_WEB_POWER
from custom_components.boesch.web_client import (
    DP_HK1_COOLING_CURVE,
    DP_HK1_FIXED_SETPOINT_HEATING,
    DP_HK1_HEATING_CURVE,
    DP_HK1_HEATING_WATER_MODE,
    DP_HK1_MIXER_POSITION,
    DP_POWER_ELECTRIC,
    DP_SEASON_OUTDOOR_TEMPERATURE,
    DP_SYSTEM_IS_PRESENT,
    MANAGER_DEVICE_ID,
    TYPE_BOOLEAN,
    TYPE_CURVE,
    TYPE_INT32,
    TYPE_SINGLE,
)

from .conftest import WANDA

HB = "dev50"
WP = "dev40"


def _curve(xs, y=35.0) -> dict:
    return {"CurveValues": [{"XValue": x, "YValue": y} for x in xs], "Info": 0}


@pytest.fixture
def web_values(fake_web):
    fake_web.values.update({
        (HB, DP_HK1_HEATING_WATER_MODE): 1,
        (HB, DP_HK1_FIXED_SETPOINT_HEATING): 34.5,
        (HB, DP_HK1_HEATING_CURVE): _curve(range(-20, 25, 5)),
        (HB, DP_HK1_COOLING_CURVE): _curve((15, 25, 30, 35, 40), 18.0),
        (HB, DP_HK1_MIXER_POSITION): 42.0,
        (HB, DP_SEASON_OUTDOOR_TEMPERATURE): 4.716547,
        (MANAGER_DEVICE_ID, DP_SYSTEM_IS_PRESENT): True,
    })
    return fake_web


async def _setup(hass: HomeAssistant, entry, **options) -> None:
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry, options={CONF_WEB_PASSWORD: "pw", **options}
    )
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _state(hass, entity_id: str) -> str:
    return hass.states.get(entity_id).state


async def test_web_entities(hass, fake_modbus, web_values, config_entry) -> None:
    await _setup(hass, config_entry)
    assert _state(hass, "select.boesch_hb_hk1_heizmodus") == "Festwert"
    assert _state(hass, "number.boesch_hb_hk1_festwert") == "34.5"
    assert _state(hass, "number.boesch_hb_hk1_heizkurve_m20") == "35.0"
    assert _state(hass, "number.boesch_hb_hk1_kuehlkurve_p40") == "18.0"
    assert _state(hass, "sensor.boesch_hb_hk1_mischer") == "42.0"
    assert _state(hass, "sensor.boesch_hb_saison_aussentemperatur") == "4.72"
    assert _state(hass, "switch.boesch_wpm_anwesenheit") == "on"
    # Anwesenheit hängt am eigenen Gerät "Wärmepumpenmanager".
    attrs = hass.states.get("switch.boesch_wpm_anwesenheit").attributes
    assert attrs["friendly_name"] == "Bösch Wärmepumpenmanager Anwesenheit"


async def test_web_writes(hass, fake_modbus, web_values, config_entry) -> None:
    await _setup(hass, config_entry)
    client = web_values.instances[0]

    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": "select.boesch_hb_hk1_heizmodus", "option": "Außentemperaturkurve"},
        blocking=True,
    )
    await hass.services.async_call(
        "number", "set_value",
        {"entity_id": "number.boesch_hb_hk1_festwert", "value": 36},
        blocking=True,
    )
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.boesch_wpm_anwesenheit"}, blocking=True
    )
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.boesch_wpm_anwesenheit"}, blocking=True
    )

    assert (HB, DP_HK1_HEATING_WATER_MODE, TYPE_INT32, 0) in client.writes
    assert (HB, DP_HK1_FIXED_SETPOINT_HEATING, TYPE_SINGLE, 36.0) in client.writes
    # Anwesenheit wird an den Manager (Null-GUID) geschrieben, nicht an die Hydrobox.
    assert (MANAGER_DEVICE_ID, DP_SYSTEM_IS_PRESENT, TYPE_BOOLEAN, False) in client.writes
    assert (MANAGER_DEVICE_ID, DP_SYSTEM_IS_PRESENT, TYPE_BOOLEAN, True) in client.writes


async def test_curve_point_write(hass, fake_modbus, web_values, config_entry) -> None:
    """Kurve wird frisch gelesen und als Ganzes geschrieben."""
    await _setup(hass, config_entry)
    # Zwischenzeitliche Änderung in der Web-UI an einem anderen Stützpunkt.
    curve = web_values.values[(HB, DP_HK1_HEATING_CURVE)]
    curve["CurveValues"][0]["YValue"] = 40.0

    await hass.services.async_call(
        "number", "set_value",
        {"entity_id": "number.boesch_hb_hk1_heizkurve_p20", "value": 25.5},
        blocking=True,
    )
    _, config_id, value_type, written = web_values.instances[0].writes[-1]
    assert (config_id, value_type) == (DP_HK1_HEATING_CURVE, TYPE_CURVE)
    points = {p["XValue"]: p["YValue"] for p in written["CurveValues"]}
    assert points[20] == 25.5
    assert points[-20] == 40.0  # nicht mit altem Poll-Stand überschrieben


async def test_curve_point_missing(hass, fake_modbus, web_values, config_entry) -> None:
    await _setup(hass, config_entry)
    web_values.values[(HB, DP_HK1_HEATING_CURVE)] = _curve((0,))
    with pytest.raises(HomeAssistantError, match="Stützpunkt"):
        await hass.services.async_call(
            "number", "set_value",
            {"entity_id": "number.boesch_hb_hk1_heizkurve_p20", "value": 25},
            blocking=True,
        )


async def test_web_write_error(hass, fake_modbus, web_values, config_entry) -> None:
    await _setup(hass, config_entry)
    web_values.error = True
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "number", "set_value",
            {"entity_id": "number.boesch_hb_hk1_festwert", "value": 36},
            blocking=True,
        )
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "number", "set_value",
            {"entity_id": "number.boesch_hb_hk1_heizkurve_p20", "value": 30},
            blocking=True,
        )


async def test_web_unreachable_at_setup(hass, fake_modbus, web_values, config_entry) -> None:
    """Web-Fehler blockieren das Setup nicht; nur die Web-Entities fehlen."""
    web_values.error = True
    await _setup(hass, config_entry)
    assert config_entry.state.name == "LOADED"
    assert _state(hass, "select.boesch_hb_hk1_heizmodus") == "unavailable"
    assert _state(hass, "sensor.boesch_wanda_b16_vorlauf") != "unavailable"


async def test_web_auth_failure_starts_reauth(hass, fake_modbus, web_values, config_entry) -> None:
    web_values.auth_error = True
    await _setup(hass, config_entry)
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == SOURCE_REAUTH for f in flows)


async def test_web_power(hass, fake_modbus, web_values, config_entry) -> None:
    """Hochauflösende Leistung ersetzt den abgeschnittenen Modbus-Wert."""
    fake_modbus.registers[(WANDA, 108)] = 11  # Modbus: 1,1 kW
    web_values.values[(WP, DP_POWER_ELECTRIC)] = 1.17
    await _setup(hass, config_entry, **{CONF_WEB_POWER: True})
    assert _state(hass, "sensor.boesch_wanda_el_leistung") == "1.17"


async def test_web_power_falls_back_to_modbus(hass, fake_modbus, web_values, config_entry) -> None:
    fake_modbus.registers[(WANDA, 108)] = 11
    web_values.error = True
    await _setup(hass, config_entry, **{CONF_WEB_POWER: True})
    assert _state(hass, "sensor.boesch_wanda_el_leistung") == "1.1"
