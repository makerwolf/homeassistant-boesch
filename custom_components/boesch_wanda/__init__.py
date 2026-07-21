"""Bösch WANDA 10 + Hydrobox — Modbus-TCP-Integration für Home Assistant."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_ENABLE_HK2,
    CONF_ENABLE_WEZ,
    CONF_HYDROBOX_ADDRESS,
    CONF_WANDA_ADDRESS,
    DEFAULT_HYDROBOX_ADDRESS,
    DEFAULT_WANDA_ADDRESS,
    SCAN_DEFAULT_BY_GROUP,
    SCAN_OPTION_BY_GROUP,
)
from .coordinator import BoeschCoordinator
from .modbus_client import BoeschModbusClient
from .registers import DeviceKey, registers_for

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SWITCH,
]

type BoeschConfigEntry = ConfigEntry[BoeschRuntimeData]


@dataclass
class BoeschRuntimeData:
    """Laufzeit-Objekte, am Config-Entry gehalten."""

    client: BoeschModbusClient
    coordinators: dict[str, BoeschCoordinator]
    unit_by_device: dict[DeviceKey, int]


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

    enable_hk2 = entry.options.get(CONF_ENABLE_HK2, True)
    enable_wez = entry.options.get(CONF_ENABLE_WEZ, True)
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

    entry.runtime_data = BoeschRuntimeData(client, coordinators, unit_by_device)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
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
