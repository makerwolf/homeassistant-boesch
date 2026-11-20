"""Heizkurven-Karte (Lovelace) mit der Integration ausliefern.

Die Karte liegt in `frontend/heizkurve-card.js`, wird unter einer festen URL
bereitgestellt und als Frontend-Modul geladen – keine Dashboard-Ressource
nötig. Die Versionsnummer in der URL sorgt nach Updates für frisches Laden.
"""

from __future__ import annotations

from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration
from homeassistant.util.hass_dict import HassKey

from .const import DOMAIN

CARD_FILE = Path(__file__).parent / "frontend" / "heizkurve-card.js"
CARD_URL = f"/{DOMAIN}_static/heizkurve-card.js"

_REGISTERED: HassKey[bool] = HassKey(f"{DOMAIN}_card_registered")


async def async_register_card(hass: HomeAssistant) -> None:
    """Karte einmal pro HA-Instanz bereitstellen und im Frontend laden.

    Ohne http/frontend (z. B. in Tests oder minimalen Setups) passiert nichts.
    """
    if hass.data.get(_REGISTERED):
        return
    if hass.http is None or "frontend" not in hass.config.components:
        return
    # Lazy imports: frontend/http sind nur after_dependencies.
    from homeassistant.components.frontend import add_extra_js_url
    from homeassistant.components.http.server import StaticPathConfig

    integration = await async_get_integration(hass, DOMAIN)
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(CARD_FILE), cache_headers=True)]
    )
    add_extra_js_url(hass, f"{CARD_URL}?v={integration.version}")
    hass.data[_REGISTERED] = True
