"""Schlanker async-Client für das Webinterface (Kermi x-center).

Das Bösch-Webinterface ist ein Kermi x-center ("Wärmepumpenmanager RW60").
Es bietet Einstellungen, die per Modbus fehlen (z. B. Heizmodus Kurve/Festwert,
Stützpunkte der Heizkurve). Die API ist inoffiziell; Format abgeleitet aus
einem HAR-Mitschnitt der Web-Oberfläche (Firmware IFM 1.6.5.44).

Bewusst ohne Home-Assistant-Imports, damit `scripts/web_probe.py` den Client
auch standalone nutzen kann.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

# Ziel-ID im API-Pfad; lokal immer die Null-GUID (= Wärmepumpenmanager selbst).
_DEST = "00000000-0000-0000-0000-000000000000"
_COOKIE = "XCenter"
_TIMEOUT = aiohttp.ClientTimeout(total=10)

# DatapointConfigIds sind Firmware-Konstanten: das Kermi-Frontend hat dieselbe
# Tabelle fest eingebaut (wellknown-datapoints.js). Schlüssel = WellKnownName.
DP_HK1_HEATING_WATER_MODE = "a060dbf1-50cc-414c-afb2-89cfc6c086f6"
DP_HK1_FIXED_SETPOINT_HEATING = "588070eb-458c-4fa0-ab40-df3fa4f29887"
DP_HK1_FIXED_SETPOINT_COOLING = "61ef070e-aa66-4803-9fed-8facaeef76b1"
DP_HK1_HEATING_CURVE = "3f89c8ba-bc2e-4889-bd73-daba9afc164c"

# .NET-Typnamen, die die API zum Deserialisieren von Schreibwerten erwartet.
TYPE_INT32 = "BMS.Shared.DatapointCore.DatapointValue`1[[System.Int32, mscorlib]], BMS.Shared"
TYPE_SINGLE = "BMS.Shared.DatapointCore.DatapointValue`1[[System.Single, mscorlib]], BMS.Shared"
TYPE_CURVE = (
    "BMS.Shared.DatapointCore.DatapointValue`1"
    "[[BMS.Shared.Model.System.Curve2d, BMS.Shared]], BMS.Shared"
)
_TYPE_CURVE_VALUE = "BMS.Shared.Model.System.Curve2d, BMS.Shared"


class WebError(Exception):
    """Fehler bei der Kommunikation mit dem Webinterface."""


class WebAuthError(WebError):
    """Anmeldung abgelehnt (falsches Passwort)."""


class BoeschWebClient:
    """Session-basierter Client: Login per Passwort, danach Cookie `XCenter`.

    Der Cookie wird manuell mitgeschickt, weil aiohttps CookieJar Cookies von
    IP-Adressen standardmäßig verwirft. Läuft die Session ab (laut Doku nach
    ~30 min Inaktivität; das Gerät liefert dann HTML statt JSON), wird einmal
    neu angemeldet und der Request wiederholt.
    """

    def __init__(
        self, session: aiohttp.ClientSession, host: str, password: str
    ) -> None:
        self._session = session
        self._base = f"http://{host}/api"
        self._password = password
        self._cookie: str | None = None
        self._lock = asyncio.Lock()

    async def async_login(self) -> None:
        """Anmelden; wirft WebAuthError bei falschem Passwort."""
        try:
            async with self._session.post(
                f"{self._base}/Security/Login",
                json={"Password": self._password, "UserId": ""},
                timeout=_TIMEOUT,
            ) as resp:
                resp.raise_for_status()
                data = await resp.json(content_type=None)
                cookie = resp.cookies.get(_COOKIE)
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise WebError(f"Login fehlgeschlagen: {err}") from err
        if not data.get("isValid"):
            raise WebAuthError("Passwort abgelehnt")
        self._cookie = cookie.value if cookie else None

    async def _request(self, method: str, path: str, payload: Any = None) -> Any:
        """API-Aufruf mit Auto-Login; gibt `ResponseData` zurück."""
        async with self._lock:
            for attempt in (1, 2):
                if self._cookie is None:
                    await self.async_login()
                try:
                    async with self._session.request(
                        method,
                        f"{self._base}/{path}/{_DEST}",
                        json=payload,
                        headers={"Cookie": f"{_COOKIE}={self._cookie}"},
                        timeout=_TIMEOUT,
                    ) as resp:
                        is_json = resp.content_type == "application/json"
                        if resp.status in (401, 403) or (resp.ok and not is_json):
                            # Session abgelaufen -> neu anmelden, einmal wiederholen.
                            self._cookie = None
                            if attempt == 1:
                                continue
                            raise WebError(f"{path}: keine gültige Session")
                        resp.raise_for_status()
                        data = await resp.json()
                except (aiohttp.ClientError, TimeoutError, ValueError) as err:
                    raise WebError(f"{path}: {err}") from err
                if data.get("StatusCode") != 0:
                    raise WebError(
                        f"{path}: {data.get('DisplayText') or data.get('StatusCode')}"
                    )
                return data.get("ResponseData")
        raise WebError(f"{path}: keine gültige Session")  # pragma: no cover

    async def async_get_device_id(self, address: int) -> str:
        """DeviceId (GUID) des Geräts mit der gegebenen Modbus-Adresse."""
        devices = await self._request("GET", "Device/GetAllDevices")
        for device in devices or []:
            if str(device.get("Address")) == str(address):
                return device["DeviceId"]
        raise WebError(f"Kein Gerät mit Adresse {address} im Webinterface")

    async def async_read(self, device_id: str, config_ids: list[str]) -> dict[str, Any]:
        """Werte mehrerer Datenpunkte lesen -> {DatapointConfigId: Value}."""
        values = await self._request(
            "POST",
            "Datapoint/ReadValues",
            {
                "DatapointValues": [
                    {"DatapointConfigId": cid, "DeviceId": device_id}
                    for cid in config_ids
                ]
            },
        )
        return {v["DatapointConfigId"]: v.get("Value") for v in values or []}

    async def async_write(
        self, device_id: str, config_id: str, value_type: str, value: Any
    ) -> None:
        """Einen Datenpunkt schreiben (Format wie die Web-Oberfläche)."""
        if value_type == TYPE_SINGLE:
            # Die Web-Oberfläche schickt Kommazahlen als String ("34", "34.5").
            value = f"{float(value):g}"
        elif value_type == TYPE_CURVE:
            value = {"$type": _TYPE_CURVE_VALUE, **value}
        await self._request(
            "POST",
            "Datapoint/WriteValues",
            {
                "DatapointValues": [
                    {
                        "$type": value_type,
                        "DatapointConfigId": config_id,
                        "DeviceId": device_id,
                        "Flags": 0,
                        "Value": value,
                    }
                ]
            },
        )
