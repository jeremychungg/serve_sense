"""
Live 3D visualization of Serve Sense IMU data over BLE.

Usage:
  python live_view.py            # auto-discovers 'ServeSense'
  python live_view.py --address XX:YY:...  # connect directly

This script:
  - Connects to the ServeSense logger over BLE using Bleak.
  - Subscribes to the IMU notify characteristic.
  - Runs a simple complementary filter to estimate orientation.
  - Renders a live 3D 'racket' and time-series plots of accel/gyro.
"""

import argparse
import asyncio
import math
import struct
import sys
from collections import deque
from typing import Deque, Tuple

import matplotlib.pyplot as plt
import numpy as np
from bleak import BleakClient, BleakScanner
from matplotlib.animation import FuncAnimation

IMU_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
CTRL_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"

PACKET_STRUCT = struct.Struct("<IHH6fB3x")
SAMPLE_DT = 0.01  # 100 Hz, keep in sync with firmware
ALPHA = 0.02      # accel contribution in complementary filter


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ServeSense live 3D IMU viewer")
    p.add_argument("--address", help="BLE MAC address (skip discovery)")
    p.add_argument("--name", default="ServeSense", help="Name hint for discovery")
    p.add_argument("--history", type=int, default=300, help="Samples of history to plot")
    return p.parse_args()


async def find_device(name_hint: str) -> str:
    print(f"[BLE] Scanning for devices matching '{name_hint}'...")
    devices = await BleakScanner.discover(timeout=5.0)
    for d in devices:
        if d.name and name_hint.lower() in d.name.lower():
            print(f"[BLE] Found {d.name} @ {d.address}")
            return d.address
    raise RuntimeError(f"No BLE device found matching '{name_hint}'")


class OrientationFilter:
    """Very simple complementary filter (good enough for demo)."""

    def __init__(self):
        self.roll = 0.0
        self.pitch = 0.0

    def update(self, ax: float, ay: float, az: float, gx: float, gy: float, gz: float) -> Tuple[float, float, float]:
        # Integrate gyro (deg/s -> rad)
        gx_r = math.radians(gx)
        gy_r = math.radians(gy)
        gz_r = math.radians(gz)

        self.roll += gx_r * SAMPLE_DT
        self.pitch += gy_r * SAMPLE_DT
        yaw = gz_r * SAMPLE_DT  # we don't integrate yaw strongly; used only for display

        # Accel-based roll/pitch
        norm = math.sqrt(ax * ax + ay * ay + az * az) + 1e-6
        ax_n, ay_n, az_n = ax / norm, ay / norm, az / norm
        roll_acc = math.atan2(ay_n, az_n)
        pitch_acc = math.atan2(-ax_n, math.sqrt(ay_n * ay_n + az_n * az_n))

        self.roll = (1 - ALPHA) * self.roll + ALPHA * roll_acc
        self.pitch = (1 - ALPHA) * self.pitch + ALPHA * pitch_acc

        return self.roll, self.pitch, yaw


async def run_viewer(address: str, history: int):
    # Shared state between BLE callback and matplotlib animation
    accel_hist: Deque[Tuple[float, float, float]] = deque(maxlen=history)
    gyro_hist: Deque[Tuple[float, float, float]] = deque(maxlen=history)
    latest_rpy = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}

    filt = OrientationFilter()

    def handle_notify(_, data: bytearray):
        if len(data) != PACKET_STRUCT.size:
            return
        _, _, _, ax, ay, az, gx, gy, gz, flags = PACKET_STRUCT.unpack(data)

        # Update orientation estimate
        r, p, y = filt.update(ax, ay, az, gx, gy, gz)
        latest_rpy["roll"], latest_rpy["pitch"], latest_rpy["yaw"] = r, p, y

        accel_hist.append((ax, ay, az))
        gyro_hist.append((gx, gy, gz))

    async with BleakClient(address) as client:
        if not client.is_connected:
            raise RuntimeError("Failed to connect")
        print(f"[BLE] Connected to {address}")

        await client.start_notify(IMU_UUID, handle_notify)
        # Turn capture on
        try:
            await client.write_gatt_char(CTRL_UUID, bytes([0x01]), response=True)
        except Exception as e:
            print(f"[WARN] Failed to send start command: {e}", file=sys.stderr)

        # Set up matplotlib figure
        plt.ion()
        fig = plt.figure(figsize=(8, 6))
        ax3d = fig.add_subplot(221, projection="3d")
        ax_acc = fig.add_subplot(222)
        ax_gyr = fig.add_subplot(212)

        # Initial racket line in body frame: from origin to (0, 0, 1)
        racket_line, = ax3d.plot([0, 0], [0, 0], [0, 1], lw=3)

        for a in (ax_acc, ax_gyr):
            a.grid(True, alpha=0.3)

        ax_acc.set_title("Accel (g)")
        ax_gyr.set_title("Gyro (dps)")

        def update_plot(_frame):
            # 3D orientation
            r, p, y = latest_rpy["roll"], latest_rpy["pitch"], latest_rpy["yaw"]

            # Rotation matrices (ZYX)
            cr, sr = math.cos(r), math.sin(r)
            cp, sp = math.cos(p), math.sin(p)
            cy, sy = math.cos(y), math.sin(y)

            Rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
            Ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
            Rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
            R = Rz @ Ry @ Rx

            body_vec = np.array([0, 0, 1.0])
            world_vec = R @ body_vec

            racket_line.set_data([0, world_vec[0]], [0, world_vec[1]])
            racket_line.set_3d_properties([0, world_vec[2]])

            ax3d.set_xlim(-1, 1)
            ax3d.set_ylim(-1, 1)
            ax3d.set_zlim(-1, 1)
            ax3d.set_xlabel("X")
            ax3d.set_ylabel("Y")
            ax3d.set_zlabel("Z")
            ax3d.set_title("Racket orientation (approx.)")

            # Time-series plots
            if accel_hist:
                arr_a = np.array(accel_hist)
                ax_acc.clear()
                ax_acc.plot(arr_a[:, 0], label="ax")
                ax_acc.plot(arr_a[:, 1], label="ay")
                ax_acc.plot(arr_a[:, 2], label="az")
                ax_acc.legend(loc="upper right")
                ax_acc.set_ylim(-4, 4)
                ax_acc.set_title("Accel (g)")
                ax_acc.grid(True, alpha=0.3)

            if gyro_hist:
                arr_g = np.array(gyro_hist)
                ax_gyr.clear()
                ax_gyr.plot(arr_g[:, 0], label="gx")
                ax_gyr.plot(arr_g[:, 1], label="gy")
                ax_gyr.plot(arr_g[:, 2], label="gz")
                ax_gyr.legend(loc="upper right")
                ax_gyr.set_ylim(-500, 500)
                ax_gyr.set_title("Gyro (dps)")
                ax_gyr.grid(True, alpha=0.3)

            plt.tight_layout()
            return racket_line,

        ani = FuncAnimation(fig, update_plot, interval=33)  # ~30 FPS

        print("[VIEW] Close the window or Ctrl+C in terminal to exit.")
        try:
            while plt.fignum_exists(fig.number):
                plt.pause(0.05)
                await asyncio.sleep(0.05)
        except KeyboardInterrupt:
            print("\n[VIEW] Stopping...")
        finally:
            try:
                await client.write_gatt_char(CTRL_UUID, bytes([0x00]), response=True)
            except Exception:
                pass
            await client.stop_notify(IMU_UUID)


def main():
    args = parse_args()
    try:
        if args.address:
            address = args.address
        else:
            address = asyncio.run(find_device(args.name))
        asyncio.run(run_viewer(address, args.history))
    except Exception as e:
        print(f"[ERR] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()


