import argparse
import asyncio
import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Tuple, Any, List

from bleak import BleakClient, BleakScanner

HR_SERVICE = "0000180d-0000-1000-8000-00805f9b34fb"
HR_CHAR    = "00002a37-0000-1000-8000-00805f9b34fb"
BAT_CHAR   = "00002a19-0000-1000-8000-00805f9b34fb"


def parse_hr(data: bytearray) -> Optional[int]:
    """Parse BLE Heart Rate Measurement (0x2A37)."""
    if not data or len(data) < 2:
        return None
    flags = data[0]
    is_u16 = (flags & 0x01) != 0
    if not is_u16:
        return int(data[1])
    if len(data) < 3:
        return None
    return int(data[1] | (data[2] << 8))


@dataclass
class LogState:
    battery: Optional[int] = None


async def scan(timeout: float) -> Dict[str, Tuple[Any, Any]]:
    """
    Returns dict[address] = (device, advertisement_data_or_None)
    Works across bleak backends without using device.metadata.
    """
    found: Dict[str, Tuple[Any, Any]] = {}

    def cb(device, adv_data):
        # device.address exists; adv_data may be None depending on backend
        found[device.address] = (device, adv_data)

    scanner = BleakScanner(detection_callback=cb)
    await scanner.start()
    try:
        await asyncio.sleep(timeout)
    finally:
        await scanner.stop()

    return found


def service_uuids_lower(adv: Any) -> List[str]:
    if adv is None:
        return []
    uuids = getattr(adv, "service_uuids", None) or []
    return [u.lower() for u in uuids]


async def find_device(name_hint: Optional[str], address: Optional[str], timeout: float):
    print("Scanning... (wear the strap so H64 is awake)")
    found = await scan(timeout=timeout)

    # If user provided exact address - prefer it
    if address:
        addr = address.strip()
        if addr in found:
            return found[addr][0]
        # Sometimes case differs
        for a, (dev, _) in found.items():
            if a.lower() == addr.lower():
                return dev
        return None

    # 1) Prefer devices advertising Heart Rate Service
    for _, (dev, adv) in found.items():
        if HR_SERVICE in service_uuids_lower(adv):
            if name_hint and (dev.name or "").lower().find(name_hint.lower()) == -1:
                continue
            return dev

    # 2) Fallback: match by name only
    if name_hint:
        for _, (dev, _) in found.items():
            if (dev.name or "").lower().find(name_hint.lower()) != -1:
                return dev

    # 3) Nothing matched
    return None


def default_out_path() -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("logs") / f"h64_hr_log_{ts}.csv"


async def run_logger(
    name_hint: Optional[str],
    address: Optional[str],
    out_path: Path,
    scan_timeout: float,
) -> None:
    dev = await find_device(name_hint=name_hint, address=address, timeout=scan_timeout)
    if not dev:
        print("Device not found. Tips:")
        print("- Make sure H64 is worn (awake)")
        print("- Ensure H64 is not connected to another app")
        print("- Run with --list to see devices, then use --address or --name")
        return

    print(f"Found: {dev.name} ({dev.address})")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    state = LogState()

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "bpm", "battery_percent"])

        def write_row(bpm: int) -> None:
            now = datetime.now().isoformat(timespec="seconds")
            writer.writerow([now, bpm, "" if state.battery is None else state.battery])
            f.flush()
            print(f"{now}  BPM={bpm}  Battery={state.battery if state.battery is not None else '-'}%")

        async with BleakClient(dev.address) as client:
            # Battery: try read immediately
            try:
                data = await client.read_gatt_char(BAT_CHAR)
                if data:
                    state.battery = int(data[0])
                    print(f"Battery (read): {state.battery}%")
            except Exception as e:
                print(f"Battery read failed (maybe unsupported / not readable): {e}")

            # Battery notify (optional)
            def on_battery(_: int, data: bytearray):
                if data:
                    state.battery = int(data[0])

            try:
                await client.start_notify(BAT_CHAR, on_battery)
            except Exception:
                pass

            # HR notify
            def on_hr(_: int, data: bytearray):
                bpm = parse_hr(data)
                if bpm is not None:
                    write_row(bpm)

            await client.start_notify(HR_CHAR, on_hr)

            print(f"Logging to: {out_path}")
            print("Connected. Receiving HR notifications... Ctrl+C to stop.")
            while True:
                await asyncio.sleep(1)


async def list_devices(scan_timeout: float) -> None:
    print("Scanning... (wear the strap so H64 is awake)")
    found = await scan(timeout=scan_timeout)
    if not found:
        print("No devices found.")
        return

    for addr, (dev, adv) in found.items():
        uuids = service_uuids_lower(adv)
        mark = "  *HR*" if HR_SERVICE in uuids else ""
        name = dev.name or ""
        print(f"{addr}  name={name!r}{mark}")
        if uuids:
            print(f"      services={uuids}")


def main() -> None:
    p = argparse.ArgumentParser(description="Magene H64 BLE logger (BPM + Battery) -> CSV")
    p.add_argument("--list", action="store_true", help="List nearby BLE devices and exit")
    p.add_argument("--name", default=None, help="Name hint for device matching (optional)")
    p.add_argument("--address", default=None, help="Exact BLE address to connect (optional)")
    p.add_argument("--out", default=None, help="Output CSV path (default: logs/h64_hr_log_YYYYMMDD_HHMMSS.csv)")
    p.add_argument("--scan-timeout", type=float, default=12.0, help="BLE scan timeout seconds (default: 12)")
    args = p.parse_args()

    out_path = Path(args.out) if args.out else default_out_path()

    try:
        if args.list:
            asyncio.run(list_devices(scan_timeout=args.scan_timeout))
        else:
            asyncio.run(
                run_logger(
                    name_hint=args.name,
                    address=args.address,
                    out_path=out_path,
                    scan_timeout=args.scan_timeout,
                )
            )
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
