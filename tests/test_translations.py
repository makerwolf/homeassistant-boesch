"""Übersetzungen und Icons passen zu den tatsächlich angelegten Entities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from homeassistant.helpers import entity_platform

from custom_components.boesch.const import (
    CONF_ENABLE_HK2,
    CONF_ENABLE_WEZ,
    CONF_WEB_PASSWORD,
    DOMAIN,
)

ROOT = Path(__file__).parent.parent / "custom_components" / DOMAIN


def _load(name: str) -> dict[str, Any]:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def _keys(data: Any, prefix: str = "") -> set[str]:
    """Alle Schlüsselpfade eines verschachtelten Dicts."""
    if not isinstance(data, dict):
        return {prefix}
    return {k for key, value in data.items() for k in _keys(value, f"{prefix}/{key}")}


def test_languages_complete() -> None:
    """strings.json = de.json; en.json hat exakt dieselben Schlüssel."""
    de = _load("translations/de.json")
    assert _load("strings.json") == de
    assert _keys(_load("translations/en.json")) == _keys(de)


def test_icons_have_translations() -> None:
    entity = _load("translations/en.json")["entity"]
    for platform, keys in _load("icons.json")["entity"].items():
        assert set(keys) <= set(entity[platform]), platform


async def test_every_entity_translated(hass, fake_modbus, fake_web, config_entry) -> None:
    """Jede Entity (alle Features an) hat Name und Zustände in der Übersetzung."""
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry,
        options={CONF_ENABLE_HK2: True, CONF_ENABLE_WEZ: True, CONF_WEB_PASSWORD: "pw"},
    )
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entity = _load("translations/en.json")["entity"]
    used: set[tuple[str, str]] = set()
    platforms = entity_platform.async_get_platforms(hass, DOMAIN)
    for platform in platforms:
        for ent in platform.entities.values():
            key = ent.translation_key
            assert key, ent.entity_id
            assert key in entity[platform.domain], ent.entity_id
            used.add((platform.domain, key))
            options = getattr(ent, "options", None) or getattr(ent, "operation_list", None)
            if options:
                assert set(entity[platform.domain][key]["state"]) == set(options), key

    # Deaktivierte Entities fehlen in platform.entities; sonst nichts Überzähliges.
    unused = {(p, k) for p, keys in entity.items() for k in keys} - used
    assert unused == {("sensor", "wanda_laufzeit_seit_start"), ("sensor", "hb_hkp2_laufzeit")}
