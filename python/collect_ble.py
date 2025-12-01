"""
Collect Serve Sense IMU packets over BLE and save to disk.

Usage:
    python collect_ble.py --out data/sessions/serve_001.parquet --label good
"""

import argparse
import asyncio
import datetime as dt
import pathlib
import struct
import sys
from dataclasses import dataclass, asdict
from typing import List, Optional

import pandas as pd
from bleak import BleakClient, BleakScanner

IMU_UUID  = "0000ff01-0000-1000-8000-00805f9b34fb"
CTRL_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"

PACKET_STRUCT = struct.Struct("<IHH6fB3x")


@dataclass
class ServeSample:
    timestamp_ms: int
    session: int
    sequence: int
    ax: float
    ay: float
    az: float
    gx: float
    gy: float
    gz: float
    capture_on: int
    marker_edge: int
    label: Optional[str] = None

    @classmethod
    def from_bytes(cls, payload: bytes, label: Optional[str]) -> "ServeSample":
        millis, session, seq, ax, ay, az, gx, gy, gz, flags = PACKET_STRUCT.unpack(payload)
        return cls(
            timestamp_ms=millis,
            session=session,
            sequence=seq,
            ax=ax, ay=ay, az=az,
            gx=gx, gy=gy, gz=gz,
            capture_on=1 if (flags & 0x01) else 0,
            marker_edge=1 if (flags & 0x02) else 0,
            label=label,
        )


async def find_device(name_hint: str) -> str:
    devices = await BleakScanner.discover(timeout=5.0)
    for dev in devices:
        if dev.name and name_hint.lower() in dev.name.lower():
            return dev.address
    raise RuntimeError(f"No BLE device found matching '{name_hint}'")


async def collect(address: str, duration: Optional[float], label: Optional[str]) -> List[ServeSample]:
    samples: List[ServeSample] = []

    def handle(_, data: bytearray):
        if len(data) != PACKET_STRUCT.size:
            print(f"[WARN] Unexpected payload size {len(data)}", file=sys.stderr)
            return
        samples.append(ServeSample.from_bytes(bytes(data), label))

    async with BleakClient(address) as client:
        if not client.is_connected:
            raise RuntimeError("BLE connection failed")
        print(f"[BLE] Connected to {address}")

        await client.start_notify(IMU_UUID, handle)
        await client.write_gatt_char(CTRL_UUID, bytes([0x01]), response=True)  # start
        print("[BLE] Capture started")

        start = dt.datetime.now()
        try:
            while True:
                await asyncio.sleep(0.1)
                if duration and (dt.datetime.now() - start).total_seconds() > duration:
                    break
        except KeyboardInterrupt:
            print("\n[BLE] KeyboardInterrupt – stopping stream")
        finally:
            await client.write_gatt_char(CTRL_UUID, bytes([0x00]), response=True)
            await client.stop_notify(IMU_UUID)

    return samples


def save_samples(samples: List[ServeSample], out_path: pathlib.Path):
    if not samples:
        print("[WARN] No samples captured; nothing to save")
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([asdict(s) for s in samples])
    if out_path.suffix.lower() == ".csv":
        df.to_csv(out_path, index=False)
    else:
        df.to_parquet(out_path, index=False)
    print(f"[OK] Saved {len(samples)} samples to {out_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve Sense BLE data collector")
    parser.add_argument("--address", help="BLE MAC address (skip auto-discovery)")
    parser.add_argument("--name", default="ServeSense", help="Device name hint for discovery")
    parser.add_argument("--out", required=True, type=pathlib.Path, help="Output file (.parquet or .csv)")
    parser.add_argument("--label", default=None, help="Optional label for the captured serves")
    parser.add_argument("--duration", type=float, default=None, help="Auto-stop after N seconds")
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        address = args.address or asyncio.run(find_device(args.name))
        samples = asyncio.run(collect(address, args.duration, args.label))
        save_samples(samples, args.out)
    except Exception as exc:
        print(f"[ERR] {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

