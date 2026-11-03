"""Diagnosedaten (Download unter Geräte & Dienste → Bösch → ⋮ → Diagnose).

Enthält neben den dekodierten Werten die rohen Registerblöcke – damit lassen
sich Fragen zur Bösch-Doku (Skalierung, doppelt vergebene Register) direkt
aus einem Download beantworten. Host, Passwort, MAC und Seriennummern werden
geschwärzt.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import BoeschConfigEntry
from .const import CONF_WEB_PASSWORD

TO_REDACT = {CONF_HOST, CONF_WEB_PASSWORD, "unique_id", "Serial", "PortAddress"}


def _status(coordinator: DataUpdateCoordinator[Any]) -> dict[str, Any]:
    return {
        "last_update_success": coordinator.last_update_success,
        "update_interval": coordinator.update_interval.total_seconds()
        if coordinator.update_interval
        else None,
        "last_exception": repr(coordinator.last_exception)
        if coordinator.last_exception
        else None,
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: BoeschConfigEntry
) -> dict[str, Any]:
    """Diagnosedaten für einen Config-Entry."""
    runtime = entry.runtime_data
    result: dict[str, Any] = {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "units": {key.value: unit for key, unit in runtime.unit_by_device.items()},
        "coordinators": {
            group: {
                **_status(coordinator),
                "data": coordinator.data,
                "raw_blocks": coordinator.raw_blocks,
            }
            for group, coordinator in runtime.coordinators.items()
        },
        "web": None,
    }
    if web := runtime.web:
        result["web"] = {
            **_status(web),
            "data": web.data,
            "devices": [
                async_redact_data(
                    {k: v for k, v in device.items() if k != "DeviceOptions"}, TO_REDACT
                )
                for device in web.devices
            ],
        }
    return result
