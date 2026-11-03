"""Bösch WANDA 10 + Hydrobox — Modbus-TCP-Integration für Home Assistant."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_ENABLE_HK2,
    CONF_ENABLE_WEZ,
    CONF_HYDROBOX_ADDRESS,
    CONF_SCAN_SETPOINT,
    CONF_WANDA_ADDRESS,
    CONF_WEB_PASSWORD,
    CONF_WEB_POWER,
    DEFAULT_ENABLE_HK2,
    DEFAULT_ENABLE_WEZ,
    DEFAULT_HYDROBOX_ADDRESS,
    DEFAULT_SCAN_SETPOINT,
    DEFAULT_WANDA_ADDRESS,
    DEFAULT_WEB_POWER,
    POLL_LIVE,
    SCAN_DEFAULT_BY_GROUP,
    SCAN_OPTION_BY_GROUP,
)
from .coordinator import BoeschCoordinator, BoeschWebCoordinator, WebPowerSource
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
    # (Plattform, unique_id) aller angelegten Entities (assign_entity_ids).
    entity_keys: set[tuple[str, str]] = field(default_factory=set)


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

    # Optional: Webinterface (Kermi x-center). Ein gemeinsamer Client (eine
    # Session) für Einstellungen und – per Haken – hochauflösende Leistungen.
    password = entry.options.get(CONF_WEB_PASSWORD)
    web_client = (
        BoeschWebClient(async_get_clientsession(hass), host, password)
        if password
        else None
    )
    web_power = (
        WebPowerSource(web_client, unit_by_device[DeviceKey.WANDA])
        if web_client and entry.options.get(CONF_WEB_POWER, DEFAULT_WEB_POWER)
        else None
    )

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
            # Die Leistungsregister 104-111 liegen in der LIVE-Gruppe.
            web_power if group == POLL_LIVE else None,
        )
        try:
            await coordinator.async_config_entry_first_refresh()
        except Exception:
            # Sonst bliebe bei jedem Setup-Retry eine TCP-Verbindung offen –
            # Modbus-Gateways erlauben oft nur wenige gleichzeitig.
            await client.async_close()
            raise
        coordinators[group] = coordinator

    # Web-Entities für Einstellungen ohne Modbus-Register. Fehler hier
    # blockieren das Setup nicht; die Web-Entities sind dann nur nicht
    # verfügbar, bis ein späterer Poll klappt.
    web: BoeschWebCoordinator | None = None
    if web_client:
        web = BoeschWebCoordinator(
            hass,
            entry,
            web_client,
            entry.options.get(CONF_SCAN_SETPOINT, DEFAULT_SCAN_SETPOINT),
            unit_by_device,
        )
        await web.async_refresh()

    entry.runtime_data = BoeschRuntimeData(
        client, coordinators, unit_by_device, web
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_remove_stale(hass, entry)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


def _async_remove_stale(hass: HomeAssistant, entry: BoeschConfigEntry) -> None:
    """Verwaiste Registry-Einträge entfernen.

    Wer HK2, den externen WEZ, einen Fühlereingang oder das Web-Passwort
    abschaltet, bekommt die zugehörigen Entities nicht mehr angelegt; ohne
    Aufräumen blieben sie als "nicht verfügbar" stehen. Danach fallen Geräte
    ohne Entities weg (z. B. der Wärmepumpenmanager ohne Webinterface).
    """
    keys = entry.runtime_data.entity_keys
    ent_reg = er.async_get(hass)
    for reg_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if (reg_entry.domain, reg_entry.unique_id) not in keys:
            _LOGGER.debug("Entferne verwaiste Entity %s", reg_entry.entity_id)
            ent_reg.async_remove(reg_entry.entity_id)

    dev_reg = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        if not er.async_entries_for_device(
            ent_reg, device.id, include_disabled_entities=True
        ):
            dev_reg.async_update_device(device.id, remove_config_entry_id=entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: BoeschConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Gerät manuell löschen erlauben, solange keine aktive Entity daran hängt."""
    keys = entry.runtime_data.entity_keys
    return not any(
        (reg_entry.domain, reg_entry.unique_id) in keys
        for reg_entry in er.async_entries_for_device(
            er.async_get(hass), device.id, include_disabled_entities=True
        )
    )


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
