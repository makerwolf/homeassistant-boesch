#!/usr/bin/env python3
"""Read-only Register-Scanner für WANDA (unit 40) / Hydrobox (unit 50).

Findet undokumentierte Register per Snapshot-Diff:

  scan_registers.py scan --host <IP> --unit 50 --start 100 --end 200 --out a.json
  # ... in der Bösch-UI genau EINEN Wert ändern ...
  scan_registers.py scan --host <IP> --unit 50 --start 100 --end 200 --out b.json
  scan_registers.py diff a.json b.json

Tipp: vorher zwei Snapshots ohne Änderung (a0, a1) nehmen und mit
`diff a0 a1` die Live-Register (Temperaturen, Zähler) erkennen; mit
`diff a b --ignore a0 a1` werden diese ausgeblendet.

Schreibt NIE auf das Gerät. Home-Assistant-Integration währenddessen
deaktivieren (gemeinsame TCP-Verbindung).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import datetime

def _signed(v: int) -> int:
    return v - 0x10000 if v >= 0x8000 else v


async def _read_one(client, addr: int, unit: int, fc: int = 3):
    """Rohwert oder None. Nicht vorhandene Adressen beantwortet das Gerät mit
    einem defekten Frame (pymodbus wirft ModbusIOException) -> als n/a werten."""
    read = client.read_input_registers if fc == 4 else client.read_holding_registers
    try:
        try:
            res = await read(addr, count=1, device_id=unit)
        except TypeError:  # ältere pymodbus-Versionen
            res = await read(addr, count=1, slave=unit)
    except Exception:
        return None
    return None if res is None or res.isError() else res.registers[0]


async def cmd_scan(args) -> None:
    logging.disable(logging.CRITICAL)  # pymodbus loggt jeden defekten Frame
    from pymodbus.client import AsyncModbusTcpClient

    client = AsyncModbusTcpClient(args.host, port=args.port, timeout=2, retries=0)
    if not await client.connect():
        raise SystemExit(f"Verbindung zu {args.host}:{args.port} fehlgeschlagen")
    regs: dict[str, int | None] = {}
    try:
        if args.only_from:
            addrs = sorted({int(k) for f in args.only_from for k, v in _load(f).items() if v is not None})
        else:
            addrs = range(args.start, args.end + 1)
        for addr in addrs:
            regs[str(addr)] = await _read_one(client, addr, args.unit, args.fc)
            await asyncio.sleep(args.delay)
    finally:
        client.close()
    ok = sum(v is not None for v in regs.values())  # bei --only-from ~ alle
    with open(args.out, "w") as f:
        json.dump(
            {"unit": args.unit, "fc": args.fc, "time": datetime.now().isoformat(timespec="seconds"), "regs": regs},
            f, indent=1,
        )
    print(f"{ok}/{len(regs)} Register lesbar -> {args.out}")


def _load(path: str) -> dict:
    with open(path) as f:
        return json.load(f)["regs"]


def cmd_diff(args) -> None:
    a, b = _load(args.a), _load(args.b)
    ignore: set[str] = set()
    if args.ignore:
        i0, i1 = _load(args.ignore[0]), _load(args.ignore[1])
        ignore = {k for k in i0 if i0[k] != i1.get(k)}
    rows = [k for k in sorted(a, key=int) if a[k] != b.get(k) and k not in ignore]
    if not rows:
        print("Keine Unterschiede.")
    for k in rows:
        va, vb = a[k], b.get(k)
        fmt = lambda v: "n/a" if v is None else f"{v} (s16 {_signed(v)}, x0.1 {_signed(v) / 10:g})"
        print(f"{k:>5}: {fmt(va)}  ->  {fmt(vb)}")
    if ignore:
        print(f"({len(ignore)} Live-Register ausgeblendet)")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("--host", required=True, help="IP-Adresse der Wärmepumpe")
    s.add_argument("--port", type=int, default=502)
    s.add_argument("--unit", type=int, default=50)
    s.add_argument("--start", type=int, default=100)
    s.add_argument("--end", type=int, default=200)
    s.add_argument("--fc", type=int, choices=(3, 4), default=3,
                   help="3 = Holding-, 4 = Input-Register")
    s.add_argument("--only-from", nargs="+", metavar="SNAP",
                   help="nur Register lesen, die in diesen Snapshots geantwortet haben (schnell)")
    s.add_argument("--delay", type=float, default=0.05, help="Pause zwischen Reads (s)")
    s.add_argument("--out", required=True)
    d = sub.add_parser("diff")
    d.add_argument("a")
    d.add_argument("b")
    d.add_argument("--ignore", nargs=2, metavar=("A0", "A1"),
                   help="zwei Snapshots ohne UI-Änderung; deren Unterschiede werden ausgeblendet")
    args = p.parse_args()
    if args.cmd == "scan":
        asyncio.run(cmd_scan(args))
    else:
        cmd_diff(args)


if __name__ == "__main__":
    main()
