"""Setup, Entities, Schreiben, Retry und Migration mit Fake-Modbus-Gerät."""

from __future__ import annotations

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.boesch.const import DOMAIN

from .conftest import HYDROBOX, WANDA


async def _setup(hass: HomeAssistant, entry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_decodes_values(hass, fake_modbus, config_entry) -> None:
    fake_modbus.registers.update({
        (WANDA, 50): 352,        # Vorlauf 35,2 °C
        (HYDROBOX, 275): 0xFFCE,  # Außentemperatur −5,0 °C
        (WANDA, 200): 4,          # Status Heizen
    })
    await _setup(hass, config_entry)

    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.boesch_wanda_b16_vorlauf").state == "35.2"
    assert hass.states.get("sensor.boesch_hb_aussentemperatur").state == "-5.0"
    assert hass.states.get("sensor.boesch_wanda_status").state == "Heizen"
    # Energiezähler sind angelegt (an den LIVE-Coordinator gebunden).
    assert hass.states.get("sensor.boesch_wanda_energie_el_gesamt") is not None


async def test_number_write(hass, fake_modbus, config_entry) -> None:
    await _setup(hass, config_entry)
    await hass.services.async_call(
        "number", "set_value",
        {"entity_id": "number.boesch_hb_twe_soll_einmal", "value": 45.5},
        blocking=True,
    )
    assert (HYDROBOX, 104, 455) in fake_modbus.instances[0].writes


async def test_water_heater_write(hass, fake_modbus, config_entry) -> None:
    fake_modbus.registers[(HYDROBOX, 102)] = 480
    await _setup(hass, config_entry)
    state = hass.states.get("water_heater.boesch_hb_twe")
    assert state.attributes["temperature"] == 48.0

    await hass.services.async_call(
        "water_heater", "set_temperature",
        {"entity_id": "water_heater.boesch_hb_twe", "temperature": 52},
        blocking=True,
    )
    assert (HYDROBOX, 102, 520) in fake_modbus.instances[0].writes


async def test_write_error_is_ha_error(hass, fake_modbus, config_entry) -> None:
    """Schreibfehler kommen als verständlicher HomeAssistantError an."""
    await _setup(hass, config_entry)
    fake_modbus.fail = True
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "number", "set_value",
            {"entity_id": "number.boesch_hb_twe_soll_einmal", "value": 45},
            blocking=True,
        )


async def test_connect_failed_retries(hass, fake_modbus, config_entry) -> None:
    fake_modbus.connect_ok = False
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_first_refresh_failed_closes_client(hass, fake_modbus, config_entry) -> None:
    """Sonst bliebe bei jedem Retry eine TCP-Verbindung offen."""
    fake_modbus.fail = True
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    assert fake_modbus.instances
    assert all(client.closed for client in fake_modbus.instances)


async def test_unload_closes_client(hass, fake_modbus, config_entry) -> None:
    await _setup(hass, config_entry)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED
    assert fake_modbus.instances[0].closed


async def test_migration_v1(hass, fake_modbus, config_entry) -> None:
    """v1 -> v2: boesch_wp_* -> boesch_wanda_*, entity_id = <plattform>.<unique_id>."""
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(config_entry, version=1)
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "sensor", DOMAIN, "boesch_wp_b16_vorlauf",
        config_entry=config_entry, suggested_object_id="wp_vorlauftemperatur_b16",
    )

    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.version == 2
    migrated = registry.async_get(old.entity_id) or registry.async_get(
        "sensor.boesch_wanda_b16_vorlauf"
    )
    assert migrated.unique_id == "boesch_wanda_b16_vorlauf"
    assert migrated.entity_id == "sensor.boesch_wanda_b16_vorlauf"


async def test_downgrade_refused(hass, fake_modbus, config_entry) -> None:
    """Entry einer neueren Version (Downgrade): HA lehnt selbst ab."""
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(config_entry, version=3)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.MIGRATION_ERROR
