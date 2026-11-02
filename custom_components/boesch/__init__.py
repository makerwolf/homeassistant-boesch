"""Bösch WANDA 10 + Hydrobox — Modbus-TCP-Integration für Home Assistant."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_ENABLE_HK2,
    CONF_ENABLE_WEZ,
    CONF_HYDROBOX_ADDRESS,
    CONF_SCAN_SETPOINT,
    CONF_WANDA_ADDRESS,
    CONF_WEB_PASSWORD,
    DEFAULT_ENABLE_HK2,
    DEFAULT_ENABLE_WEZ,
    DEFAULT_HYDROBOX_ADDRESS,
    DEFAULT_SCAN_SETPOINT,
    DEFAULT_WANDA_ADDRESS,
    SCAN_DEFAULT_BY_GROUP,
    SCAN_OPTION_BY_GROUP,
)
from .coordinator import BoeschCoordinator, BoeschWebCoordinator
from .modbus_client import BoeschModbusClient
from .registers import DeviceKey, registers_for
from .web_client import BoeschWebClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SWITCH,
    Platform.WATER_HEATER,
]

type BoeschConfigEntry = ConfigEntry[BoeschRuntimeData]


@dataclass
class BoeschRuntimeData:
    """Laufzeit-Objekte, am Config-Entry gehalten."""

    client: BoeschModbusClient
    coordinators: dict[str, BoeschCoordinator]
    unit_by_device: dict[DeviceKey, int]
    # Nur gesetzt, wenn im Options-Flow ein Web-Passwort hinterlegt ist.
    web: BoeschWebCoordinator | None = None


async def async_setup_entry(hass: HomeAssistant, entry: BoeschConfigEntry) -> bool:
    """Config-Entry einrichten."""
    host: str = entry.data[CONF_HOST]
    port: int = entry.data[CONF_PORT]

    client = BoeschModbusClient(host, port)
    if not await client.async_connect():
        raise ConfigEntryNotReady(f"Verbindung zu {host}:{port} fehlgeschlagen")

    unit_by_device = {
        DeviceKey.WANDA: entry.data.get(CONF_WANDA_ADDRESS, DEFAULT_WANDA_ADDRESS),
        DeviceKey.HYDROBOX: entry.data.get(
            CONF_HYDROBOX_ADDRESS, DEFAULT_HYDROBOX_ADDRESS
        ),
    }

    enable_hk2 = entry.options.get(CONF_ENABLE_HK2, DEFAULT_ENABLE_HK2)
    enable_wez = entry.options.get(CONF_ENABLE_WEZ, DEFAULT_ENABLE_WEZ)
    regs = registers_for(enable_hk2, enable_wez)

    # Ein Coordinator pro Poll-Gruppe, jeweils mit eigenem Intervall.
    coordinators: dict[str, BoeschCoordinator] = {}
    groups = {reg.poll_group for reg in regs}
    for group in groups:
        interval = entry.options.get(
            SCAN_OPTION_BY_GROUP[group], SCAN_DEFAULT_BY_GROUP[group]
        )
        coordinator = BoeschCoordinator(
            hass,
            entry,
            client,
            group,
            interval,
            [r for r in regs if r.poll_group == group],
            unit_by_device,
        )
        await coordinator.async_config_entry_first_refresh()
        coordinators[group] = coordinator

    # Optional: Webinterface (Kermi x-center) für Einstellungen ohne Modbus-Register.
    # Fehler hier blockieren das Setup nicht; die Web-Entities sind dann nur
    # nicht verfügbar, bis ein späterer Poll klappt.
    web: BoeschWebCoordinator | None = None
    if password := entry.options.get(CONF_WEB_PASSWORD):
        web = BoeschWebCoordinator(
            hass,
            entry,
            BoeschWebClient(async_get_clientsession(hass), host, password),
            entry.options.get(CONF_SCAN_SETPOINT, DEFAULT_SCAN_SETPOINT),
            unit_by_device[DeviceKey.HYDROBOX],
        )
        await web.async_refresh()

    entry.runtime_data = BoeschRuntimeData(
        client, coordinators, unit_by_device, web
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migration auf das kompakte boesch_-Schema (Entry-Version 1 -> 2).

    Benennt bestehende Registry-Einträge einmalig um:
      - unique_id: boesch_wp_* -> boesch_wanda_* (Hydrobox boesch_hb_* bleibt)
      - entity_id: -> <plattform>.<unique_id>  (z. B. sensor.boesch_wanda_b16_vorlauf)
    HA migriert Historie + Langzeitstatistik beim entity_id-Umzug automatisch mit.
    """
    if entry.version < 2:
        registry = er.async_get(hass)
        for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
            new_uid = reg_entry.unique_id
            if new_uid.startswith("boesch_wp_"):
                new_uid = "boesch_wanda_" + new_uid[len("boesch_wp_"):]
            new_eid = f"{reg_entry.domain}.{new_uid}"
            updates: dict[str, str] = {}
            if new_uid != reg_entry.unique_id:
                updates["new_unique_id"] = new_uid
            if new_eid != reg_entry.entity_id and registry.async_get(new_eid) is None:
                updates["new_entity_id"] = new_eid
            if updates:
                try:
                    registry.async_update_entity(reg_entry.entity_id, **updates)
                except ValueError as err:
                    _LOGGER.warning(
                        "Konnte %s nicht migrieren: %s", reg_entry.entity_id, err
                    )
        hass.config_entries.async_update_entry(entry, version=2)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BoeschConfigEntry) -> bool:
    """Config-Entry entladen."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.client.async_close()
    return unloaded


async def _async_update_listener(
    hass: HomeAssistant, entry: BoeschConfigEntry
) -> None:
    """Bei geänderten Optionen (Intervalle, Features) neu laden."""
    await hass.config_entries.async_reload(entry.entry_id)
