"""Geräteinfo, Entity-Kategorien, Aufräumen verwaister Einträge, Diagnostics."""

from __future__ import annotations

from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.boesch import async_remove_config_entry_device
from custom_components.boesch.const import CONF_ENABLE_HK2, CONF_WEB_PASSWORD, DOMAIN
from custom_components.boesch.diagnostics import async_get_config_entry_diagnostics

from .conftest import WANDA


async def _setup(hass: HomeAssistant, entry, **options) -> None:
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(entry, options=options)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _set_options(hass: HomeAssistant, entry, **options) -> None:
    """Optionen ändern; der Update-Listener lädt den Entry neu."""
    hass.config_entries.async_update_entry(entry, options={**entry.options, **options})
    await hass.async_block_till_done()


def _device(hass: HomeAssistant, entry, key: str) -> dr.DeviceEntry | None:
    return dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, f"{entry.entry_id}_{key}"), entry.entry_id
    )


async def test_entity_categories(hass, fake_modbus, config_entry) -> None:
    await _setup(hass, config_entry)
    registry = er.async_get(hass)
    alarm = registry.async_get("sensor.boesch_wanda_alarmcode")
    assert alarm.entity_category is EntityCategory.DIAGNOSTIC
    threshold = registry.async_get("number.boesch_hb_hk1_sommer_aus")
    assert threshold.entity_category is EntityCategory.CONFIG
    # Selten gebraucht: angelegt, aber deaktiviert.
    runtime = registry.async_get("sensor.boesch_wanda_laufzeit_seit_start")
    assert runtime.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get("sensor.boesch_wanda_laufzeit_seit_start") is None


async def test_device_info_from_web(hass, fake_modbus, fake_web, config_entry) -> None:
    await _setup(hass, config_entry, **{CONF_WEB_PASSWORD: "pw"})
    hydrobox = _device(hass, config_entry, "hydrobox")
    assert hydrobox.serial_number == "S-HB"
    assert hydrobox.sw_version == "1.1.1.20"
    assert hydrobox.configuration_url == "http://192.0.2.10"
    assert _device(hass, config_entry, "manager").serial_number == "S-WPM"
    assert _device(hass, config_entry, "wanda").name == "Bösch WANDA"


async def test_disabled_feature_removes_entities(hass, fake_modbus, config_entry) -> None:
    await _setup(hass, config_entry, **{CONF_ENABLE_HK2: True})
    registry = er.async_get(hass)
    assert registry.async_get("sensor.boesch_hb_hk2_status") is not None

    await _set_options(hass, config_entry, **{CONF_ENABLE_HK2: False})
    assert registry.async_get("sensor.boesch_hb_hk2_status") is None
    # Bleibende Entities sind unberührt, auch deaktivierte.
    assert registry.async_get("sensor.boesch_hb_hk1_status") is not None
    assert registry.async_get("sensor.boesch_wanda_laufzeit_seit_start") is not None


async def test_web_off_removes_manager(hass, fake_modbus, fake_web, config_entry) -> None:
    await _setup(hass, config_entry, **{CONF_WEB_PASSWORD: "pw"})
    assert _device(hass, config_entry, "manager") is not None

    await _set_options(hass, config_entry, **{CONF_WEB_PASSWORD: ""})
    assert _device(hass, config_entry, "manager") is None
    assert er.async_get(hass).async_get("switch.boesch_wpm_anwesenheit") is None
    assert _device(hass, config_entry, "hydrobox") is not None


async def test_remove_device(hass, fake_modbus, config_entry) -> None:
    await _setup(hass, config_entry)
    wanda = _device(hass, config_entry, "wanda")
    assert not await async_remove_config_entry_device(hass, config_entry, wanda)

    orphan = dr.async_get(hass).async_get_or_create(
        config_entry_id=config_entry.entry_id, identifiers={(DOMAIN, "alt")}
    )
    assert await async_remove_config_entry_device(hass, config_entry, orphan)


async def test_diagnostics(hass, fake_modbus, fake_web, config_entry) -> None:
    fake_modbus.registers[(WANDA, 50)] = 352
    await _setup(hass, config_entry, **{CONF_WEB_PASSWORD: "geheim"})
    diag = await async_get_config_entry_diagnostics(hass, config_entry)

    assert diag["entry"]["data"]["host"] == "**REDACTED**"
    assert diag["entry"]["options"][CONF_WEB_PASSWORD] == "**REDACTED**"
    live = diag["coordinators"]["live"]
    assert live["last_update_success"] is True
    assert live["data"]["boesch_wanda_b16_vorlauf"] == 35.2
    assert 352 in live["raw_blocks"][f"{WANDA}:50"]
    devices = diag["web"]["devices"]
    assert {d["Serial"] for d in devices} == {"**REDACTED**"}
    assert {d["SoftwareVersion"] for d in devices} >= {"1.1.1.20"}
    assert "geheim" not in repr(diag)
