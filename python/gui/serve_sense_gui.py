"""
Serve Sense GUI - Modern PySide6-based interface for tennis serve analysis.

This application provides:
- BLE device connection management
- Real-time 3D racket orientation visualization
- Live accelerometer and gyroscope data plotting
- Data collection with serve type labeling
- Professional UI with status bar and menu system

Windows Compatibility:
- Uses proper QThread for BLE operations
- Handles Windows COM threading and event loop configuration
- Implements robust error handling for Windows BLE backend

Usage:
    python serve_sense_gui.py
    python serve_sense_gui.py --address XX:YY:ZZ:...
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
from typing import Tuple

import numpy as np
from PySide6.QtCore import (
    Qt, QThread, Signal, Slot, QTimer, QObject
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QStatusBar, QMenuBar, QMenu,
    QMessageBox, QFileDialog, QGroupBox, QGridLayout, QSpinBox,
    QSplitter
)
from PySide6.QtGui import QAction, QKeySequence, QFont
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from bleak import BleakClient, BleakScanner

# Add parent directory to path to import serve_labels and ble_utils
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from serve_labels import SERVE_LABELS, get_label_display_name
from ble_utils import (
    setup_windows_event_loop,
    init_windows_com_threading,
    discover_device_with_retry,
    scan_devices,
    BLEConnectionManager
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# BLE UUIDs
IMU_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
CTRL_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"

# Packet format from firmware
PACKET_STRUCT = struct.Struct("<IHH6fB3x")
SAMPLE_DT = 0.01  # 100 Hz sampling rate
ALPHA = 0.02      # Complementary filter alpha


class OrientationFilter:
    """Simple complementary filter for orientation estimation."""
    
    def __init__(self):
        self.roll = 0.0
        self.pitch = 0.0
    
    def update(self, ax: float, ay: float, az: float, 
               gx: float, gy: float, gz: float) -> Tuple[float, float, float]:
        """Update orientation estimate with new IMU data."""
        # Integrate gyro (deg/s -> rad)
        gx_r = math.radians(gx)
        gy_r = math.radians(gy)
        gz_r = math.radians(gz)
        
        self.roll += gx_r * SAMPLE_DT
        self.pitch += gy_r * SAMPLE_DT
        yaw = gz_r * SAMPLE_DT  # Display only, no integration
        
        # Accel-based roll/pitch
        norm = math.sqrt(ax * ax + ay * ay + az * az) + 1e-6
        ax_n, ay_n, az_n = ax / norm, ay / norm, az / norm
        roll_acc = math.atan2(ay_n, az_n)
        pitch_acc = math.atan2(-ax_n, math.sqrt(ay_n * ay_n + az_n * az_n))
        
        # Complementary filter
        self.roll = (1 - ALPHA) * self.roll + ALPHA * roll_acc
        self.pitch = (1 - ALPHA) * self.pitch + ALPHA * pitch_acc
        
        return self.roll, self.pitch, yaw


class BLEWorker(QObject):
    """Worker thread for BLE operations with Windows compatibility."""
    
    # Signals
    device_found = Signal(str, str)  # address, name
    connected = Signal(str)  # address
    disconnected = Signal()
    connection_error = Signal(str)  # error message
    data_received = Signal(object)  # IMU data dict
    
    def __init__(self):
        super().__init__()
        self.address = None
        self.client = None
        self.running = False
        self.loop = None
        
        # Initialize Windows COM threading for this thread
        if sys.platform == "win32":
            init_windows_com_threading()
        
    def set_address(self, address: str):
        """Set BLE device address."""
        self.address = address
    
    @Slot()
    def scan_devices(self):
        """Scan for BLE devices with Windows-compatible event loop."""
        # Set up event loop for this thread
        setup_windows_event_loop()
        asyncio.run(self._scan_async())
    
    async def _scan_async(self):
        """Async device scanning with retry."""
        try:
            devices_list = await scan_devices(timeout=5.0)
            for address, name in devices_list:
                self.device_found.emit(address, name)
        except Exception as e:
            logger.error(f"Scan error: {e}", exc_info=True)
            self.connection_error.emit(f"Scan error: {str(e)}")
    
    @Slot()
    def connect(self):
        """Connect to BLE device with Windows-compatible event loop."""
        if not self.address:
            self.connection_error.emit("No device address set")
            return
        
        # Set up event loop for this thread
        setup_windows_event_loop()
        asyncio.run(self._connect_async())
    
    async def _connect_async(self):
        """Async BLE connection with robust error handling."""
        try:
            async with BLEConnectionManager(self.address) as client:
                self.client = client
                self.connected.emit(self.address)
                
                # Start notifications
                await client.start_notify(IMU_UUID, self._handle_notify)
                
                # Start capture
                try:
                    await client.write_gatt_char(CTRL_UUID, bytes([0x01]), response=True)
                except Exception as e:
                    logger.warning(f"Failed to start capture: {e}")
                
                self.running = True
                
                # Keep connection alive
                while self.running and client.is_connected:
                    await asyncio.sleep(0.1)
                
                # Stop capture before disconnect
                try:
                    await client.write_gatt_char(CTRL_UUID, bytes([0x00]), response=True)
                    await client.stop_notify(IMU_UUID)
                except Exception as e:
                    logger.warning(f"Error during cleanup: {e}")
                
        except Exception as e:
            logger.error(f"Connection error: {e}", exc_info=True)
            self.connection_error.emit(f"Connection error: {str(e)}")
        finally:
            self.client = None
            self.disconnected.emit()
    
    def _handle_notify(self, _, data: bytearray):
        """Handle BLE notification."""
        if len(data) != PACKET_STRUCT.size:
            return
        
        millis, session, seq, ax, ay, az, gx, gy, gz, flags = PACKET_STRUCT.unpack(data)
        
        imu_data = {
            "timestamp_ms": millis,
            "session": session,
            "sequence": seq,
            "ax": float(ax), "ay": float(ay), "az": float(az),
            "gx": float(gx), "gy": float(gy), "gz": float(gz),
            "flags": int(flags),
            "capture_on": bool(flags & 0x01),
            "marker_edge": bool(flags & 0x02)
        }
        
        self.data_received.emit(imu_data)
    
    @Slot()
    def disconnect(self):
        """Disconnect from BLE device."""
        self.running = False


class OrientationCanvas(FigureCanvas):
    """3D orientation visualization canvas."""
    
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(5, 5))
        self.ax = self.fig.add_subplot(111, projection='3d')
        super().__init__(self.fig)
        
        self.setParent(parent)
        
        # Initialize plot
        self.racket_line, = self.ax.plot([0, 0], [0, 0], [0, 1], 'b-', lw=3)
        self.ax.set_xlim(-1, 1)
        self.ax.set_ylim(-1, 1)
        self.ax.set_zlim(-1, 1)
        self.ax.set_xlabel('X')
        self.ax.set_ylabel('Y')
        self.ax.set_zlabel('Z')
        self.ax.set_title('Racket Orientation')
        self.fig.tight_layout()
    
    def update_orientation(self, roll: float, pitch: float, yaw: float):
        """Update 3D orientation display."""
        # Rotation matrices (ZYX Euler)
        cr, sr = math.cos(roll), math.sin(roll)
        cp, sp = math.cos(pitch), math.sin(pitch)
        cy, sy = math.cos(yaw), math.sin(yaw)
        
        Rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
        Ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
        Rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
        R = Rz @ Ry @ Rx
        
        body_vec = np.array([0, 0, 1.0])
        world_vec = R @ body_vec
        
        self.racket_line.set_data([0, world_vec[0]], [0, world_vec[1]])
        self.racket_line.set_3d_properties([0, world_vec[2]])
        
        self.draw()


class TimeSeriesCanvas(FigureCanvas):
    """Time series plot canvas for IMU data."""
    
    def __init__(self, title: str, ylabel: str, ylim: Tuple[float, float], 
                 labels: Tuple[str, str, str], parent=None):
        self.fig = Figure(figsize=(8, 3))
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)
        
        self.setParent(parent)
        
        self.title = title
        self.ylabel = ylabel
        self.ylim = ylim
        self.labels = labels
        
        # Initialize plot
        self.lines = [
            self.ax.plot([], [], label=labels[0], color='r')[0],
            self.ax.plot([], [], label=labels[1], color='g')[0],
            self.ax.plot([], [], label=labels[2], color='b')[0]
        ]
        
        self.ax.set_title(title)
        self.ax.set_ylabel(ylabel)
        self.ax.set_ylim(ylim)
        self.ax.legend(loc='upper right')
        self.ax.grid(True, alpha=0.3)
        self.fig.tight_layout()
        
        self.data_x = []
        self.data_y = [[], [], []]
    
    def update_data(self, values: Tuple[float, float, float]):
        """Update plot with new data."""
        if len(self.data_x) == 0:
            self.data_x.append(0)
        else:
            self.data_x.append(self.data_x[-1] + 1)
        
        for i, val in enumerate(values):
            self.data_y[i].append(val)
        
        # Keep only recent data
        max_points = 300
        if len(self.data_x) > max_points:
            self.data_x = self.data_x[-max_points:]
            for i in range(3):
                self.data_y[i] = self.data_y[i][-max_points:]
        
        # Update lines
        for i, line in enumerate(self.lines):
            line.set_data(self.data_x, self.data_y[i])
        
        self.ax.set_xlim(max(0, len(self.data_x) - max_points), len(self.data_x))
        self.draw()
    
    def clear_data(self):
        """Clear all data."""
        self.data_x = []
        self.data_y = [[], [], []]
        for line in self.lines:
            line.set_data([], [])
        self.draw()


class ServeSenseGUI(QMainWindow):
    """Main GUI window for Serve Sense application."""
    
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("Serve Sense - Tennis Serve Analysis")
        self.setGeometry(100, 100, 1400, 900)
        
        # BLE worker and thread
        self.ble_thread = QThread()
        self.ble_worker = BLEWorker()
        self.ble_worker.moveToThread(self.ble_thread)
        
        # Connect signals
        self.ble_worker.device_found.connect(self.on_device_found)
        self.ble_worker.connected.connect(self.on_connected)
        self.ble_worker.disconnected.connect(self.on_disconnected)
        self.ble_worker.connection_error.connect(self.on_connection_error)
        self.ble_worker.data_received.connect(self.on_data_received)
        
        self.ble_thread.start()
        
        # State
        self.connected = False
        self.recording = False
        self.recording_file = None
        self.sample_count = 0
        self.output_dir = pathlib.Path("../data/sessions")
        self.orientation_filter = OrientationFilter()
        
        # Setup UI
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the user interface."""
        # Create menu bar
        self.create_menu_bar()
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        
        # Top section: Connection controls
        connection_group = self.create_connection_controls()
        main_layout.addWidget(connection_group)
        
        # Middle section: Visualizations
        viz_splitter = QSplitter(Qt.Horizontal)
        
        # Left: 3D orientation
        self.orientation_canvas = OrientationCanvas()
        viz_splitter.addWidget(self.orientation_canvas)
        
        # Right: Time series plots
        plots_widget = QWidget()
        plots_layout = QVBoxLayout(plots_widget)
        
        self.accel_canvas = TimeSeriesCanvas(
            "Accelerometer", "Acceleration (g)", (-4, 4),
            ("ax", "ay", "az")
        )
        plots_layout.addWidget(self.accel_canvas)
        
        self.gyro_canvas = TimeSeriesCanvas(
            "Gyroscope", "Angular Velocity (dps)", (-500, 500),
            ("gx", "gy", "gz")
        )
        plots_layout.addWidget(self.gyro_canvas)
        
        viz_splitter.addWidget(plots_widget)
        viz_splitter.setSizes([400, 800])
        
        main_layout.addWidget(viz_splitter, 1)
        
        # Bottom section: Recording controls
        recording_group = self.create_recording_controls()
        main_layout.addWidget(recording_group)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready - Not connected")
        
        # Connection status labels
        self.conn_status_label = QLabel("Disconnected")
        self.conn_status_label.setStyleSheet("color: red; font-weight: bold;")
        self.status_bar.addPermanentWidget(self.conn_status_label)
        
        self.sample_rate_label = QLabel("0 samples/s")
        self.status_bar.addPermanentWidget(self.sample_rate_label)
    
    def create_menu_bar(self):
        """Create menu bar."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("&File")
        
        change_output_action = QAction("Change &Output Directory...", self)
        change_output_action.triggered.connect(self.change_output_directory)
        file_menu.addAction(change_output_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Connection menu
        conn_menu = menubar.addMenu("&Connection")
        
        scan_action = QAction("&Scan for Devices", self)
        scan_action.setShortcut("Ctrl+S")
        scan_action.triggered.connect(self.scan_devices)
        conn_menu.addAction(scan_action)
        
        connect_action = QAction("&Connect", self)
        connect_action.setShortcut("Ctrl+C")
        connect_action.triggered.connect(self.toggle_connection)
        conn_menu.addAction(connect_action)
        
        # Recording menu
        rec_menu = menubar.addMenu("&Recording")
        
        self.record_action = QAction("Start &Recording", self)
        self.record_action.setShortcut("Ctrl+R")
        self.record_action.setEnabled(False)
        self.record_action.triggered.connect(self.toggle_recording)
        rec_menu.addAction(self.record_action)
        
        clear_action = QAction("Clear &Plots", self)
        clear_action.setShortcut("Ctrl+L")
        clear_action.triggered.connect(self.clear_plots)
        rec_menu.addAction(clear_action)
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        
        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def create_connection_controls(self) -> QGroupBox:
        """Create connection control panel."""
        group = QGroupBox("BLE Connection")
        layout = QHBoxLayout()
        
        # Device selector
        layout.addWidget(QLabel("Device:"))
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(200)
        layout.addWidget(self.device_combo)
        
        # Scan button
        self.scan_btn = QPushButton("Scan")
        self.scan_btn.clicked.connect(self.scan_devices)
        layout.addWidget(self.scan_btn)
        
        # Connect button
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.toggle_connection)
        self.connect_btn.setEnabled(False)
        layout.addWidget(self.connect_btn)
        
        layout.addStretch()
        
        # Connection info
        self.conn_info_label = QLabel("Not connected")
        layout.addWidget(self.conn_info_label)
        
        group.setLayout(layout)
        return group
    
    def create_recording_controls(self) -> QGroupBox:
        """Create recording control panel."""
        group = QGroupBox("Data Recording")
        layout = QGridLayout()
        
        # Serve label selector
        layout.addWidget(QLabel("Serve Type:"), 0, 0)
        self.label_combo = QComboBox()
        for label in SERVE_LABELS:
            self.label_combo.addItem(get_label_display_name(label), label)
        self.label_combo.setMinimumWidth(250)
        layout.addWidget(self.label_combo, 0, 1)
        
        # Record button
        self.record_btn = QPushButton("Start Recording")
        self.record_btn.setEnabled(False)
        self.record_btn.clicked.connect(self.toggle_recording)
        self.record_btn.setMinimumHeight(40)
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        self.record_btn.setFont(font)
        layout.addWidget(self.record_btn, 0, 2, 2, 1)
        
        # Sample counter
        layout.addWidget(QLabel("Samples:"), 1, 0)
        self.sample_counter_label = QLabel("0")
        self.sample_counter_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        layout.addWidget(self.sample_counter_label, 1, 1)
        
        # Recording status
        self.recording_status_label = QLabel("Not recording")
        self.recording_status_label.setStyleSheet("color: gray;")
        layout.addWidget(self.recording_status_label, 1, 3)
        
        group.setLayout(layout)
        return group
    
    @Slot()
    def scan_devices(self):
        """Scan for BLE devices."""
        self.device_combo.clear()
        self.status_bar.showMessage("Scanning for devices...")
        self.scan_btn.setEnabled(False)
        
        # Run scan in BLE thread
        QTimer.singleShot(0, self.ble_worker.scan_devices)
        
        # Re-enable button after timeout
        QTimer.singleShot(6000, lambda: self.scan_btn.setEnabled(True))
        QTimer.singleShot(6000, lambda: self.status_bar.showMessage("Scan complete"))
    
    @Slot(str, str)
    def on_device_found(self, address: str, name: str):
        """Handle device found during scan."""
        self.device_combo.addItem(f"{name} ({address})", address)
        self.connect_btn.setEnabled(True)
    
    @Slot()
    def toggle_connection(self):
        """Toggle BLE connection."""
        if not self.connected:
            # Connect
            if self.device_combo.count() == 0:
                QMessageBox.warning(self, "No Device", "Please scan for devices first.")
                return
            
            address = self.device_combo.currentData()
            if not address:
                return
            
            self.ble_worker.set_address(address)
            self.status_bar.showMessage(f"Connecting to {address}...")
            self.connect_btn.setEnabled(False)
            
            QTimer.singleShot(0, self.ble_worker.connect)
        else:
            # Disconnect
            self.ble_worker.disconnect()
    
    @Slot(str)
    def on_connected(self, address: str):
        """Handle successful connection."""
        self.connected = True
        self.connect_btn.setText("Disconnect")
        self.connect_btn.setEnabled(True)
        self.record_btn.setEnabled(True)
        self.record_action.setEnabled(True)
        
        self.conn_status_label.setText("Connected")
        self.conn_status_label.setStyleSheet("color: green; font-weight: bold;")
        self.conn_info_label.setText(f"Connected: {address}")
        self.status_bar.showMessage(f"Connected to {address}")
        
        # Reset orientation filter
        self.orientation_filter = OrientationFilter()
    
    @Slot()
    def on_disconnected(self):
        """Handle disconnection."""
        self.connected = False
        self.connect_btn.setText("Connect")
        self.connect_btn.setEnabled(True)
        self.record_btn.setEnabled(False)
        self.record_action.setEnabled(False)
        
        self.conn_status_label.setText("Disconnected")
        self.conn_status_label.setStyleSheet("color: red; font-weight: bold;")
        self.conn_info_label.setText("Not connected")
        self.status_bar.showMessage("Disconnected")
        
        # Stop recording if active
        if self.recording:
            self.stop_recording()
    
    @Slot(str)
    def on_connection_error(self, error: str):
        """Handle connection error."""
        QMessageBox.critical(self, "Connection Error", error)
        self.status_bar.showMessage(f"Error: {error}")
        self.on_disconnected()
    
    @Slot(object)
    def on_data_received(self, data: dict):
        """Handle incoming IMU data."""
        # Update orientation
        r, p, y = self.orientation_filter.update(
            data["ax"], data["ay"], data["az"],
            data["gx"], data["gy"], data["gz"]
        )
        self.orientation_canvas.update_orientation(r, p, y)
        
        # Update time series plots
        self.accel_canvas.update_data((data["ax"], data["ay"], data["az"]))
        self.gyro_canvas.update_data((data["gx"], data["gy"], data["gz"]))
        
        # Record data if recording
        if self.recording and self.recording_file:
            sample = {
                **data,
                "label": self.label_combo.currentData()
            }
            json_line = json.dumps(sample) + "\n"
            self.recording_file.write(json_line)
            self.recording_file.flush()
            
            self.sample_count += 1
            self.sample_counter_label.setText(str(self.sample_count))
    
    @Slot()
    def toggle_recording(self):
        """Toggle recording state."""
        if not self.recording:
            self.start_recording()
        else:
            self.stop_recording()
    
    def start_recording(self):
        """Start recording data."""
        if not self.connected:
            QMessageBox.warning(self, "Not Connected", "Please connect to a device first.")
            return
        
        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate filename
        timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        label = self.label_combo.currentData()
        label_suffix = label.replace("_", "-")
        filename = self.output_dir / f"serve_{label_suffix}_{timestamp}.jsonl"
        
        # Open file
        try:
            self.recording_file = open(filename, "w")
        except Exception as e:
            QMessageBox.critical(self, "File Error", f"Failed to create file: {e}")
            return
        
        # Update UI
        self.recording = True
        self.sample_count = 0
        self.record_btn.setText("Stop Recording")
        self.record_btn.setStyleSheet("background-color: #ff4444; color: white;")
        self.record_action.setText("Stop &Recording")
        self.recording_status_label.setText(f"Recording to: {filename.name}")
        self.recording_status_label.setStyleSheet("color: red; font-weight: bold;")
        self.status_bar.showMessage(f"Recording started: {filename.name}")
        
        # Disable label selection during recording
        self.label_combo.setEnabled(False)
    
    def stop_recording(self):
        """Stop recording data."""
        if self.recording_file:
            self.recording_file.close()
            self.recording_file = None
        
        # Update UI
        self.recording = False
        self.record_btn.setText("Start Recording")
        self.record_btn.setStyleSheet("")
        self.record_action.setText("Start &Recording")
        self.recording_status_label.setText(f"Recording stopped - {self.sample_count} samples saved")
        self.recording_status_label.setStyleSheet("color: green;")
        self.status_bar.showMessage(f"Recording stopped - {self.sample_count} samples saved")
        
        # Re-enable label selection
        self.label_combo.setEnabled(True)
    
    @Slot()
    def clear_plots(self):
        """Clear all plot data."""
        self.accel_canvas.clear_data()
        self.gyro_canvas.clear_data()
        self.status_bar.showMessage("Plots cleared")
    
    @Slot()
    def change_output_directory(self):
        """Change output directory for recordings."""
        dir_path = QFileDialog.getExistingDirectory(
            self, "Select Output Directory", str(self.output_dir)
        )
        if dir_path:
            self.output_dir = pathlib.Path(dir_path)
            self.status_bar.showMessage(f"Output directory: {dir_path}")
    
    @Slot()
    def show_about(self):
        """Show about dialog."""
        about_text = """
        <h2>Serve Sense</h2>
        <p><b>Version 1.0.0</b></p>
        <p>Tennis Serve Analysis Application</p>
        <p>Modern PySide6-based GUI for real-time IMU data visualization 
        and serve technique classification.</p>
        <p>Features:</p>
        <ul>
            <li>BLE device connection and management</li>
            <li>Real-time 3D racket orientation</li>
            <li>Live accelerometer and gyroscope plots</li>
            <li>Serve type labeling and data recording</li>
        </ul>
        <p>© 2024 Serve Sense Project</p>
        """
        QMessageBox.about(self, "About Serve Sense", about_text)
    
    def closeEvent(self, event):
        """Handle window close event."""
        # Stop recording if active
        if self.recording:
            self.stop_recording()
        
        # Disconnect if connected
        if self.connected:
            self.ble_worker.disconnect()
        
        # Stop BLE thread
        self.ble_thread.quit()
        self.ble_thread.wait()
        
        event.accept()


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Serve Sense GUI - Tennis Serve Analysis"
    )
    parser.add_argument(
        "--address",
        help="BLE MAC address (skip device scanning)"
    )
    parser.add_argument(
        "--out-dir",
        type=pathlib.Path,
        default=pathlib.Path("../data/sessions"),
        help="Directory for saving recordings (default: ../data/sessions)"
    )
    return parser.parse_args()


def main():
    """Main application entry point with Windows BLE support."""
    # Initialize Windows-compatible event loop
    setup_windows_event_loop()
    
    # Initialize COM threading on Windows (safe on other platforms)
    init_windows_com_threading()
    
    args = parse_args()
    
    app = QApplication(sys.argv)
    app.setApplicationName("Serve Sense")
    app.setOrganizationName("Serve Sense Project")
    
    window = ServeSenseGUI()
    
    # Set output directory from args
    if args.out_dir:
        window.output_dir = args.out_dir
    
    # Auto-connect if address provided
    if args.address:
        window.device_combo.addItem(f"Device ({args.address})", args.address)
        window.connect_btn.setEnabled(True)
        # Auto-connect after a short delay
        QTimer.singleShot(500, window.toggle_connection)
    
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
