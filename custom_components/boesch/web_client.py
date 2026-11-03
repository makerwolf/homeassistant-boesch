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
# DeviceId des Wärmepumpenmanagers (IFM) selbst.
MANAGER_DEVICE_ID = _DEST
_COOKIE = "XCenter"
_TIMEOUT = aiohttp.ClientTimeout(total=10)

# DatapointConfigIds sind Firmware-Konstanten: das Kermi-Frontend hat dieselbe
# Tabelle fest eingebaut (wellknown-datapoints.js). Schlüssel = WellKnownName.
DP_HK1_HEATING_WATER_MODE = "a060dbf1-50cc-414c-afb2-89cfc6c086f6"
DP_HK1_FIXED_SETPOINT_HEATING = "588070eb-458c-4fa0-ab40-df3fa4f29887"
DP_HK1_FIXED_SETPOINT_COOLING = "61ef070e-aa66-4803-9fed-8facaeef76b1"
DP_HK1_HEATING_CURVE = "3f89c8ba-bc2e-4889-bd73-daba9afc164c"
DP_HK1_COOLING_CURVE = "b8555de8-2a45-4d7a-bbf4-005104c8c798"
DP_HK1_MIXER_POSITION = "8589b3a8-716c-484b-ba07-6039544b795f"
# Außentemperatur, nach der die Saisonumschaltung (Sommer/Winter/Kühlen) schaltet.
DP_SEASON_OUTDOOR_TEMPERATURE = "e0ed80e9-ec5a-4c5e-941e-f4430448cb27"
# Wärmepumpenmanager
DP_SYSTEM_IS_PRESENT = "55fe1ecb-47f1-4ebf-852f-d9d169042e49"
# WANDA (EcoODU_*): Leistungen in kW mit 0,01 kW Auflösung. Modbus liefert
# dieselben Größen nur auf 0,1 kW abgeschnitten (Register 104-111).
DP_POWER_OUTPUT = "51a1db3b-59cc-4ff8-85b9-2cb596c89f82"
DP_POWER_OUTPUT_HEATING = "122849bf-342c-495c-a430-b422ff7ecf1b"
DP_POWER_OUTPUT_TWE = "56f7839a-24e5-4674-862c-eceda2babffe"
DP_POWER_OUTPUT_COOLING = "2fb83845-661e-4c70-9446-cc29161ba555"
DP_POWER_ELECTRIC = "45111410-984c-4dcf-beab-acc8a81b376e"
DP_POWER_ELECTRIC_HEATING = "db8a9dc7-d764-417c-acac-a9997ac49140"
DP_POWER_ELECTRIC_TWE = "54a9e57b-7739-42cd-bd5d-477d650488ba"
DP_POWER_ELECTRIC_COOLING = "756bd7b5-7871-43a3-9bab-6c26c1d88b5c"

# .NET-Typnamen, die die API zum Deserialisieren von Schreibwerten erwartet.
TYPE_INT32 = "BMS.Shared.DatapointCore.DatapointValue`1[[System.Int32, mscorlib]], BMS.Shared"
TYPE_SINGLE = "BMS.Shared.DatapointCore.DatapointValue`1[[System.Single, mscorlib]], BMS.Shared"
TYPE_BOOLEAN = "BMS.Shared.DatapointCore.DatapointValue`1[[System.Boolean, mscorlib]], BMS.Shared"
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
        if not cookie:
            raise WebError("Login ohne Session-Cookie")
        self._cookie = cookie.value

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

    async def async_get_devices(self) -> list[dict[str, Any]]:
        """Alle Geräte des x-center (Manager, WANDA, Hydrobox).

        Je Gerät u. a. `DeviceId`, `Address` (Modbus-Adresse, beim Manager
        leer), `Name`, `Serial`, `SoftwareVersion`.
        """
        return await self._request("GET", "Device/GetAllDevices") or []

    async def async_get_device_id(self, address: int) -> str:
        """DeviceId (GUID) des Geräts mit der gegebenen Modbus-Adresse."""
        for device in await self.async_get_devices():
            if str(device.get("Address")) == str(address):
                return str(device["DeviceId"])
        raise WebError(f"Kein Gerät mit Adresse {address} im Webinterface")

    async def async_read(self, device_id: str, config_ids: list[str]) -> dict[str, Any]:
        """Werte mehrerer Datenpunkte lesen -> {DatapointConfigId: Value}.

        `IgnoreErrors` wie die Web-Oberfläche: ein gesperrter oder fehlender
        Datenpunkt fehlt dann nur im Ergebnis, statt die ganze Abfrage
        scheitern zu lassen. "NaN" (z. B. COP ohne Betrieb) wird zu None.
        """
        values = await self._request(
            "POST",
            "Datapoint/ReadValues",
            {
                "DatapointValues": [
                    {"DatapointConfigId": cid, "DeviceId": device_id}
                    for cid in config_ids
                ],
                "IgnoreErrors": True,
            },
        )
        return {
            v["DatapointConfigId"]: None if v.get("Value") == "NaN" else v.get("Value")
            for v in values or []
        }

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
