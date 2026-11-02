#!/usr/bin/env python3
"""Read-only Test des Webinterface-Clients (Kermi x-center) ohne Home Assistant.

  web_probe.py --host 192.168.0.18 [--unit 50]

Fragt das Web-Passwort verdeckt ab, meldet sich an, sucht die Hydrobox über
ihre Modbus-Adresse und liest Heizmodus, Festwert und Heizkurve HK1.
Schreibt NIE auf das Gerät. Braucht nur aiohttp.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import importlib.util
import json
from pathlib import Path

import aiohttp

# web_client.py hat keine HA-Abhängigkeiten und wird direkt per Dateipfad
# geladen (nicht über sys.path: select.py der Integration würde sonst das
# gleichnamige Stdlib-Modul verdecken).
_spec = importlib.util.spec_from_file_location(
    "web_client",
    Path(__file__).resolve().parent.parent / "custom_components" / "boesch" / "web_client.py",
)
wc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wc)

_NAMES = {
    wc.DP_HK1_HEATING_WATER_MODE: "Heizmodus HK1 (0 Kurve / 1 Festwert / 2 Aus)",
    wc.DP_HK1_FIXED_SETPOINT_HEATING: "Konstanter Sollwert Heizkreis HK1",
    wc.DP_HK1_HEATING_CURVE: "Stützpunkte Heizkurve HK1",
}


async def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--host", required=True, help="IP-Adresse des Webinterfaces")
    p.add_argument("--unit", type=int, default=50, help="Modbus-Adresse Hydrobox")
    args = p.parse_args()
    password = getpass.getpass("Web-Passwort: ")

    async with aiohttp.ClientSession() as session:
        client = wc.BoeschWebClient(session, args.host, password)
        await client.async_login()
        print("Login ok")
        device_id = await client.async_get_device_id(args.unit)
        print(f"Hydrobox (Adresse {args.unit}): DeviceId {device_id}")
        values = await client.async_read(device_id, list(_NAMES))
        for cid, name in _NAMES.items():
            print(f"{name}: {json.dumps(values.get(cid), ensure_ascii=False)}")


if __name__ == "__main__":
    asyncio.run(main())
