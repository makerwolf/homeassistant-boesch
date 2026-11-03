#!/usr/bin/env python3
"""Read-only Test des Webinterface-Clients (Kermi x-center) ohne Home Assistant.

  web_probe.py --host <IP> [--unit 50]
  web_probe.py --host <IP> --watch 600   # Leistung der WANDA beobachten
  web_probe.py --host <IP> --watch 600 --twe   # ... inkl. TWE-Werte

Fragt das Web-Passwort verdeckt ab, meldet sich an, sucht die Hydrobox über
ihre Modbus-Adresse und liest Heizmodus, Festwert und Heizkurve HK1.
Mit --watch SEKUNDEN stattdessen alle 2 s die aktuelle (elektrische) Leistung
der WANDA lesen und jede Änderung mit Zeitstempel ausgeben (Update-Rate).
Schreibt NIE auf das Gerät. Braucht nur aiohttp.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import importlib.util
import itertools
import json
import time
from datetime import datetime
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

# WANDA (EcoODU_*): intern als Register 2023/2028 mit Faktor 0,01 gelesen,
# über Modbus TCP aber nicht erreichbar.
_WATCH = {
    "45111410-984c-4dcf-beab-acc8a81b376e": "el. Leistung",
    "51a1db3b-59cc-4ff8-85b9-2cb596c89f82": "Leistung",
}
_WATCH_TWE = {
    "54a9e57b-7739-42cd-bd5d-477d650488ba": "el. Leistung TWE",
    "56f7839a-24e5-4674-862c-eceda2babffe": "Leistung TWE",
    "7a367794-f294-4084-a2a0-41fe7463b382": "COP TWE",
}

# Hydrobox: Mischer HK1 (nur im Webinterface, nicht in der Modbus-Liste).
_MIXER = {
    "8589b3a8-716c-484b-ba07-6039544b795f": "Mischer-Öffnung HK1",
    "c7f95be5-743f-4a49-952f-50829b07ee90": "Mischer-Modus HK1",
    "7200daea-3199-45df-90a3-d2d40f206417": "Mischerkreis konfiguriert HK1",
    "7a686686-9c46-48e1-8380-35bc650ad8ec": "Mischer-Laufzeit HK1",
}

# Wärmepumpenmanager (IFM, DeviceId = Null-GUID).
_IFM = {
    "55fe1ecb-47f1-4ebf-852f-d9d169042e49": "Anwesenheitsstatus",
}

_NAMES = {
    wc.DP_HK1_HEATING_WATER_MODE: "Heizmodus HK1 (0 Kurve / 1 Festwert / 2 Aus)",
    wc.DP_HK1_FIXED_SETPOINT_HEATING: "Konstanter Sollwert Heizkreis HK1",
    wc.DP_HK1_HEATING_CURVE: "Stützpunkte Heizkurve HK1",
}


async def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--host", required=True, help="IP-Adresse des Webinterfaces")
    p.add_argument("--unit", type=int, default=50, help="Modbus-Adresse Hydrobox")
    p.add_argument("--wanda-unit", type=int, default=40, help="Modbus-Adresse WANDA")
    p.add_argument("--watch", type=int, metavar="SEKUNDEN",
                   help="WANDA-Leistung so lange alle 2 s beobachten")
    p.add_argument("--twe", action="store_true",
                   help="bei --watch zusätzlich die TWE-Leistung beobachten")
    args = p.parse_args()
    password = getpass.getpass("Web-Passwort: ")

    async with aiohttp.ClientSession() as session:
        client = wc.BoeschWebClient(session, args.host, password)
        await client.async_login()
        print("Login ok")
        if args.watch:
            watch = {**_WATCH, **_WATCH_TWE} if args.twe else _WATCH
            await _watch(client, args.wanda_unit, args.watch, watch)
            return
        device_id = await client.async_get_device_id(args.unit)
        print(f"Hydrobox (Adresse {args.unit}): DeviceId {device_id}")
        # Einzeln lesen: ein gesperrter Datenpunkt lässt sonst die ganze
        # Sammelabfrage scheitern ("Lesen nicht erlaubt").
        wanda_id = await client.async_get_device_id(args.wanda_unit)
        for dev, names in (
            (device_id, {**_NAMES, **_MIXER}),
            (wanda_id, {**_WATCH, **_WATCH_TWE}),
            (wc._DEST, _IFM),
        ):
            for cid, name in names.items():
                try:
                    value = (await client.async_read(dev, [cid])).get(cid)
                except wc.WebError as err:
                    value = f"FEHLER: {err}"
                print(f"{name}: {json.dumps(value, ensure_ascii=False)}")


async def _watch(client, unit: int, duration: int, watch: dict[str, str]) -> None:
    """Werte alle 2 s lesen, Änderungen mit Zeitstempel ausgeben."""
    device_id = await client.async_get_device_id(unit)
    print(f"WANDA (Adresse {unit}): DeviceId {device_id}; beobachte {duration} s")
    last: dict[str, object] = {}
    changes: dict[str, list[float]] = {cid: [] for cid in watch}
    end = time.monotonic() + duration
    while time.monotonic() < end:
        values = await client.async_read(device_id, list(watch))
        now = time.monotonic()
        changed = [cid for cid in watch if values.get(cid) != last.get(cid)]
        if changed:
            stamp = datetime.now().strftime("%H:%M:%S")
            row = "  ".join(f"{n}={values.get(c)}" for c, n in watch.items())
            print(f"{stamp}  {row}")
            for cid in changed:
                if cid in last:
                    changes[cid].append(now)
            last = values
        await asyncio.sleep(2)
    for cid, name in watch.items():
        t = changes[cid]
        gaps = [b - a for a, b in itertools.pairwise(t)]
        avg = f"{sum(gaps) / len(gaps):.1f} s" if gaps else "-"
        print(f"{name}: {len(t)} Änderungen, mittlerer Abstand {avg}")


if __name__ == "__main__":
    asyncio.run(main())
