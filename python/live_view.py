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
  
Windows Compatibility:
  - Uses proper event loop configuration for Windows
  - Handles COM threading initialization
  - Separates BLE operations from matplotlib thread
"""

import argparse
import asyncio
import datetime as dt
import json
import logging
import math
import pathlib
import struct
import sys
import threading
from collections import deque
from typing import Deque, List, Optional, Tuple

import matplotlib
matplotlib.use('TkAgg')  # Use TkAgg backend for better threading support
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from bleak import BleakClient, BleakScanner
from matplotlib.animation import FuncAnimation
from matplotlib.widgets import Button, RadioButtons

from serve_labels import SERVE_LABELS, get_label_display_name
from ble_utils import (
    setup_windows_event_loop,
    init_windows_com_threading,
    discover_device_with_retry,
    BLEConnectionManager
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
    p.add_argument("--out-dir", type=pathlib.Path, default=pathlib.Path("../data/sessions"),
                   help="Directory to save recorded sessions")
    return p.parse_args()


async def find_device(name_hint: str) -> str:
    """Find BLE device with retry logic (Windows-compatible)."""
    logger.info(f"[BLE] Scanning for devices matching '{name_hint}'...")
    return await discover_device_with_retry(name_hint, timeout=5.0, max_retries=3)


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


async def run_viewer(address: str, history: int, out_dir: pathlib.Path):
    # Shared state between BLE callback and matplotlib animation
    accel_hist: Deque[Tuple[float, float, float]] = deque(maxlen=history)
    gyro_hist: Deque[Tuple[float, float, float]] = deque(maxlen=history)
    latest_rpy = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}
    reconnect_flag = {"requested": False}
    
    # Recording state
    recording_state = {
        "active": False,
        "file": None,
        "session_id": 0,
        "samples": [],
        "current_label": SERVE_LABELS[0],  # Default to first label
        "lock": threading.Lock()  # Lock for thread-safe file writing
    }

    filt = OrientationFilter()

    def handle_notify(_, data: bytearray):
        if len(data) != PACKET_STRUCT.size:
            return
        millis, session, seq, ax, ay, az, gx, gy, gz, flags = PACKET_STRUCT.unpack(data)

        # Update orientation estimate
        r, p, y = filt.update(ax, ay, az, gx, gy, gz)
        latest_rpy["roll"], latest_rpy["pitch"], latest_rpy["yaw"] = r, p, y

        accel_hist.append((ax, ay, az))
        gyro_hist.append((gx, gy, gz))
        
        # Record sample if recording is active
        if recording_state["active"]:
            sample = {
                "timestamp_ms": millis,
                "session": session,
                "sequence": seq,
                "ax": float(ax), "ay": float(ay), "az": float(az),
                "gx": float(gx), "gy": float(gy), "gz": float(gz),
                "flags": int(flags),
                "capture_on": bool(flags & 0x01),
                "marker_edge": bool(flags & 0x02),
                "label": recording_state["current_label"]  # Include selected label
            }
            recording_state["samples"].append(sample)
            
            # Write sample-by-sample to file (append JSON lines format, thread-safe)
            with recording_state["lock"]:
                if recording_state["file"] and recording_state["active"]:
                    json_line = json.dumps(sample) + "\n"
                    recording_state["file"].write(json_line)
                    recording_state["file"].flush()

    plt.ion()
    fig = plt.figure(figsize=(10, 7))
    ax3d = fig.add_subplot(221, projection="3d")
    ax_acc = fig.add_subplot(222)
    ax_gyr = fig.add_subplot(212)

    # Reserve area below plots for buttons and label selector
    btn_reconnect_ax = fig.add_axes([0.01, 0.01, 0.12, 0.05])
    btn_record_ax = fig.add_axes([0.14, 0.01, 0.12, 0.05])
    label_display_ax = fig.add_axes([0.27, 0.01, 0.35, 0.05])
    label_display_ax.axis("off")
    
    btn_reconnect = Button(btn_reconnect_ax, "Reconnect")
    btn_record = Button(btn_record_ax, "Record")
    
    # Label selector using radio buttons (compact)
    label_radio_ax = fig.add_axes([0.63, 0.01, 0.36, 0.25])
    label_radio_ax.axis("off")
    
    # Create radio buttons for label selection
    display_labels = [get_label_display_name(label) for label in SERVE_LABELS]
    radio = RadioButtons(label_radio_ax, display_labels, active=0)
    
    def on_label_change(label_display):
        # Find the internal label from display name
        for internal_label, display_name in zip(SERVE_LABELS, display_labels):
            if display_name == label_display:
                recording_state["current_label"] = internal_label
                # Update label display text
                label_display_ax.clear()
                label_display_ax.axis("off")
                label_display_ax.text(0.5, 0.5, f"Label: {label_display}", 
                                     ha="center", va="center", fontsize=9, 
                                     bbox=dict(boxstyle="round", facecolor="lightblue"))
                print(f"[LABEL] Selected: {internal_label} ({label_display})")
                break
    
    radio.on_clicked(on_label_change)
    
    # Initial label display
    label_display_ax.text(0.5, 0.5, f"Label: {display_labels[0]}", 
                         ha="center", va="center", fontsize=9,
                         bbox=dict(boxstyle="round", facecolor="lightblue"))

    def on_reconnect(_event):
        print("[VIEW] Reconnect requested")
        reconnect_flag["requested"] = True

    def on_record(_event):
        if not recording_state["active"]:
            # Start recording
            if not recording_state["current_label"]:
                print("[ERR] Please select a label before recording", file=sys.stderr)
                return
            out_dir.mkdir(parents=True, exist_ok=True)
            timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            label_suffix = recording_state["current_label"].replace("_", "-")
            filename = out_dir / f"serve_{label_suffix}_{timestamp}.jsonl"
            recording_state["file"] = open(filename, "w")
            recording_state["active"] = True
            recording_state["session_id"] += 1
            recording_state["samples"] = []
            label_display = get_label_display_name(recording_state["current_label"])
            btn_record.label.set_text("Stop")
            print(f"[REC] Recording started: {filename}")
            print(f"[REC] Label: {label_display} ({recording_state['current_label']})")
        else:
            # Stop recording (thread-safe)
            with recording_state["lock"]:
                if recording_state["file"]:
                    recording_state["file"].close()
                    recording_state["file"] = None
            recording_state["active"] = False
            btn_record.label.set_text("Record")
            num_samples = len(recording_state["samples"])
            label_display = get_label_display_name(recording_state["current_label"])
            print(f"[REC] Recording stopped: {num_samples} samples saved")
            print(f"[REC] Label: {label_display}")

    btn_reconnect.on_clicked(on_reconnect)
    btn_record.on_clicked(on_record)

    # Initial racket line in body frame: from origin to (0, 0, 1)
    racket_line, = ax3d.plot([0, 0], [0, 0], [0, 1], lw=3)

    for a in (ax_acc, ax_gyr):
        a.grid(True, alpha=0.3)

    ax_acc.set_title("Accel (g)")
    ax_gyr.set_title("Gyro (dps)")

    async def connect_and_stream(current_address: str):
        """Connect and stream with Windows-compatible BLE handling."""
        nonlocal racket_line
        async with BLEConnectionManager(current_address) as client:
            logger.info(f"[BLE] Connected to {current_address}")

            await client.start_notify(IMU_UUID, handle_notify)
            # Turn capture on
            try:
                await client.write_gatt_char(CTRL_UUID, bytes([0x01]), response=True)
            except Exception as e:
                logger.warning(f"Failed to send start command: {e}")

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

            ani = FuncAnimation(fig, update_plot, interval=33, blit=False)  # ~30 FPS

            logger.info("[VIEW] Close the window or use the button to reconnect.")
            try:
                # Use a simpler loop that doesn't block
                while plt.fignum_exists(fig.number) and not reconnect_flag["requested"]:
                    await asyncio.sleep(0.1)  # Check less frequently
            except KeyboardInterrupt:
                logger.info("\n[VIEW] Stopping...")
            finally:
                reconnect_flag["requested"] = reconnect_flag["requested"] and plt.fignum_exists(fig.number)
                # Stop recording if active (thread-safe)
                if recording_state["active"]:
                    recording_state["active"] = False
                    with recording_state["lock"]:
                        if recording_state["file"]:
                            recording_state["file"].close()
                            recording_state["file"] = None
                try:
                    await client.write_gatt_char(CTRL_UUID, bytes([0x00]), response=True)
                except Exception:
                    pass
                await client.stop_notify(IMU_UUID)
                if ani:
                    ani.event_source.stop()

    # Run async BLE loop in a separate thread with Windows-compatible event loop
    async def run_ble_loop():
        """BLE loop with proper Windows event loop handling."""
        # Initialize COM threading for this thread on Windows
        if sys.platform == "win32":
            init_windows_com_threading()
        
        current_address = address
        while plt.fignum_exists(fig.number):
            reconnect_flag["requested"] = False
            try:
                await connect_and_stream(current_address)
            except Exception as e:
                logger.error(f"Connection error: {e}", exc_info=True)
                reconnect_flag["requested"] = False

            if not plt.fignum_exists(fig.number):
                break

            if reconnect_flag["requested"]:
                logger.info("[VIEW] Attempting to reconnect...")
                # Optionally re-discover if original address was not provided
                if not current_address:
                    try:
                        current_address = await find_device("ServeSense")
                    except Exception as e:
                        logger.error(f"Rediscovery failed: {e}")
                        break
            else:
                break
    
    # Start BLE loop in background thread with proper event loop
    def run_async():
        """Run async BLE loop with Windows-compatible event loop."""
        # Set up Windows event loop policy for this thread
        setup_windows_event_loop()
        asyncio.run(run_ble_loop())
    
    ble_thread = threading.Thread(target=run_async, daemon=True)
    ble_thread.start()
    
    # Show the plot (this blocks until window is closed)
    plt.show()


def main():
    """Main entry point with Windows BLE support."""
    # Initialize Windows-compatible event loop for main thread
    setup_windows_event_loop()
    
    # Initialize COM threading on Windows (safe on other platforms)
    init_windows_com_threading()
    
    args = parse_args()
    try:
        if args.address:
            address = args.address
        else:
            address = asyncio.run(find_device(args.name))
        run_viewer(address, args.history, args.out_dir)
    except Exception as e:
        logger.error(f"{e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()


