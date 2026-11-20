"""Heizkurven-Karte: Bereitstellung und Laden im Frontend."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant

from custom_components.boesch.card import CARD_FILE, CARD_URL, async_register_card


def test_card_file_bundled() -> None:
    """Die Karte liegt im Paket (HACS lädt nur custom_components/boesch)."""
    assert CARD_FILE.is_file()
    assert "customElements.define('heizkurve-card'" in CARD_FILE.read_text("utf-8")


async def test_card_skipped_without_frontend(hass: HomeAssistant) -> None:
    """Ohne http/frontend (Tests, Minimal-Setup) wird nichts registriert."""
    with patch("homeassistant.components.frontend.add_extra_js_url") as add:
        await async_register_card(hass)
    add.assert_not_called()


async def test_card_registered_once(hass: HomeAssistant) -> None:
    """Statischer Pfad + Frontend-Modul mit Version, nur einmal pro Instanz."""
    hass.http = MagicMock(async_register_static_paths=AsyncMock())
    hass.config.components.add("frontend")
    with patch("homeassistant.components.frontend.add_extra_js_url") as add:
        await async_register_card(hass)
        await async_register_card(hass)

    hass.http.async_register_static_paths.assert_awaited_once()
    (config,) = hass.http.async_register_static_paths.call_args.args[0]
    assert config.url_path == CARD_URL
    assert config.path == str(CARD_FILE)
    add.assert_called_once()
    url = add.call_args.args[1]
    assert url.startswith(f"{CARD_URL}?v=")
    assert url != f"{CARD_URL}?v="
