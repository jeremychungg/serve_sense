#!/usr/bin/env python3
"""
ServeSense Classifier GUI

Real-time GUI for visualizing tennis serve classification results.
Connects to ServeSense Classifier device via BLE and displays:
- Real-time classification results
- Recording status
- Confidence scores for each class
- Live IMU data visualization
"""

import sys
import asyncio
import struct
import datetime as dt
from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QGroupBox, QGridLayout, QComboBox,
    QStatusBar, QMessageBox, QProgressBar
)
from PySide6.QtGui import QFont, QColor, QPalette

from bleak import BleakClient, BleakScanner

# BLE UUIDs matching ServeSense logger protocol
SERVICE_UUID = "0000ff00-0000-1000-8000-00805f9b34fb"
IMU_CHAR_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
CTRL_CHAR_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"
SWITCH_CHAR_UUID = "0000ff04-0000-1000-8000-00805f9b34fb"
RESULT_CHAR_UUID = "0000ff05-0000-1000-8000-00805f9b34fb"

# Serve class labels
SERVE_CLASSES = [
    "good-serve",
    "jerky-motion",
    "lacks-pronation",
    "short-swing"
]

CLASS_COLORS = {
    "good-serve": "#22c55e",        # Green
    "jerky-motion": "#ef4444",      # Red
    "lacks-pronation": "#f59e0b",   # Amber
    "short-swing": "#3b82f6",       # Blue
    "UNKNOWN": "#6b7280"            # Gray
}


class ClassificationDisplay(QWidget):
    """Widget to display classification results with confidence bars."""
    
    def __init__(self):
        super().__init__()
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Title
        title = QLabel("Classification Results")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        
        # Prediction label
        self.prediction_label = QLabel("No prediction yet")
        pred_font = QFont()
        pred_font.setPointSize(16)
        pred_font.setBold(True)
        self.prediction_label.setFont(pred_font)
        self.prediction_label.setAlignment(Qt.AlignCenter)
        self.prediction_label.setStyleSheet(
            "padding: 20px; background-color: #f3f4f6; border-radius: 8px;"
        )
        layout.addWidget(self.prediction_label)
        
        # Confidence bars for each class
        self.confidence_bars = {}
        self.confidence_labels = {}
        
        bars_group = QGroupBox("Confidence Scores")
        bars_layout = QGridLayout()
        
        for i, class_name in enumerate(SERVE_CLASSES):
            # Class label
            label = QLabel(class_name.replace("-", " ").title())
            bars_layout.addWidget(label, i, 0)
            
            # Progress bar
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setTextVisible(True)
            bar.setFormat("%v%")
            self.confidence_bars[class_name] = bar
            bars_layout.addWidget(bar, i, 1)
            
        bars_group.setLayout(bars_layout)
        layout.addWidget(bars_group)
        
        layout.addStretch()
        self.setLayout(layout)
    
    def update_prediction(self, class_name: str, confidence: float):
        """Update the main prediction display."""
        color = CLASS_COLORS.get(class_name, CLASS_COLORS["UNKNOWN"])
        
        display_name = class_name.replace("-", " ").title()
        self.prediction_label.setText(f"{display_name}\n{confidence:.1f}%")
        self.prediction_label.setStyleSheet(
            f"padding: 20px; background-color: {color}; "
            f"color: white; border-radius: 8px; font-weight: bold;"
        )
    
    def update_confidences(self, confidences: dict):
        """Update confidence bars for all classes."""
        for class_name, bar in self.confidence_bars.items():
            confidence = confidences.get(class_name, 0.0)
            bar.setValue(int(confidence))
            
            # Color the bar based on value
            if confidence >= 60:
                color = "#22c55e"  # Green
            elif confidence >= 30:
                color = "#f59e0b"  # Amber
            else:
                color = "#ef4444"  # Red
            
            bar.setStyleSheet(f"""
                QProgressBar {{
                    border: 2px solid #ddd;
                    border-radius: 5px;
                    text-align: center;
                }}
                QProgressBar::chunk {{
                    background-color: {color};
                    border-radius: 3px;
                }}
            """)
    
    def reset(self):
        """Reset display to initial state."""
        self.prediction_label.setText("No prediction yet")
        self.prediction_label.setStyleSheet(
            "padding: 20px; background-color: #f3f4f6; "
            "border-radius: 8px; color: #374151;"
        )
        for bar in self.confidence_bars.values():
            bar.setValue(0)


class ServeSenseClassifierGUI(QMainWindow):
    """Main GUI window for ServeSense Classifier."""
    
    # Signals
    classification_received = Signal(str, float)  # class_name, confidence
    switch_state_changed = Signal(bool)  # recording state
    
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("ServeSense Classifier")
        self.setMinimumSize(800, 600)
        
        # BLE state
        self.client = None
        self.connected = False
        self.device_address = None
        
        # Recording state
        self.is_recording = False
        
        # Setup UI
        self.setup_ui()
        
        # Connect signals
        self.classification_received.connect(self.on_classification)
        self.switch_state_changed.connect(self.on_switch_state)
        
    def setup_ui(self):
        """Setup the user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        
        # Connection controls
        conn_group = QGroupBox("Device Connection")
        conn_layout = QHBoxLayout()
        
        self.scan_btn = QPushButton("Scan for Devices")
        self.scan_btn.clicked.connect(self.scan_devices)
        conn_layout.addWidget(self.scan_btn)
        
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(300)
        conn_layout.addWidget(self.device_combo)
        
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setEnabled(False)
        self.connect_btn.clicked.connect(self.toggle_connection)
        conn_layout.addWidget(self.connect_btn)
        
        self.conn_status = QLabel("Not connected")
        self.conn_status.setStyleSheet("color: red; font-weight: bold;")
        conn_layout.addWidget(self.conn_status)
        
        conn_layout.addStretch()
        conn_group.setLayout(conn_layout)
        main_layout.addWidget(conn_group)
        
        # Recording status
        rec_group = QGroupBox("Recording Status")
        rec_layout = QHBoxLayout()
        
        self.rec_indicator = QLabel("●")
        self.rec_indicator.setStyleSheet("color: gray; font-size: 24pt;")
        rec_layout.addWidget(self.rec_indicator)
        
        self.rec_status = QLabel("Idle - Flip switch on D1 to record")
        rec_font = QFont()
        rec_font.setPointSize(11)
        self.rec_status.setFont(rec_font)
        rec_layout.addWidget(self.rec_status)
        
        rec_layout.addStretch()
        rec_group.setLayout(rec_layout)
        main_layout.addWidget(rec_group)
        
        # Classification display
        self.classification_display = ClassificationDisplay()
        main_layout.addWidget(self.classification_display)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready - Click 'Scan for Devices' to begin")
    
    @Slot()
    def scan_devices(self):
        """Scan for BLE devices."""
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("Scanning...")
        self.device_combo.clear()
        self.status_bar.showMessage("Scanning for devices...")
        
        # Run scan in async
        asyncio.ensure_future(self._scan_devices())
    
    async def _scan_devices(self):
        """Async BLE device scan."""
        try:
            devices = await BleakScanner.discover(timeout=5.0)
            
            servesense_devices = []
            for device in devices:
                if device.name and "ServeSense" in device.name:
                    servesense_devices.append(device)
                    self.device_combo.addItem(
                        f"{device.name} ({device.address})", 
                        device.address
                    )
            
            if servesense_devices:
                self.connect_btn.setEnabled(True)
                self.status_bar.showMessage(
                    f"Found {len(servesense_devices)} ServeSense device(s)"
                )
            else:
                self.status_bar.showMessage(
                    "No ServeSense devices found. Make sure device is powered on."
                )
                QMessageBox.information(
                    self, "No Devices", 
                    "No ServeSense devices found. Please ensure:\n"
                    "1. Device is powered on\n"
                    "2. Device is not connected to another app\n"
                    "3. Bluetooth is enabled on your computer"
                )
        except Exception as e:
            self.status_bar.showMessage(f"Scan error: {e}")
            QMessageBox.critical(self, "Scan Error", f"Failed to scan: {e}")
        finally:
            self.scan_btn.setEnabled(True)
            self.scan_btn.setText("Scan for Devices")
    
    @Slot()
    def toggle_connection(self):
        """Toggle BLE connection."""
        if self.connected:
            asyncio.ensure_future(self._disconnect())
        else:
            self.device_address = self.device_combo.currentData()
            if self.device_address:
                asyncio.ensure_future(self._connect())
    
    async def _connect(self):
        """Async BLE connection."""
        self.connect_btn.setEnabled(False)
        self.status_bar.showMessage(f"Connecting to {self.device_address}...")
        
        try:
            self.client = BleakClient(self.device_address)
            await self.client.connect()
            
            # Subscribe to switch characteristic
            await self.client.start_notify(
                SWITCH_CHAR_UUID,
                self._switch_notification_handler
            )
            
            # Subscribe to result characteristic
            await self.client.start_notify(
                RESULT_CHAR_UUID,
                self._result_notification_handler
            )
            
            # Send start stream command (matching logger protocol)
            try:
                await self.client.write_gatt_char(CTRL_CHAR_UUID, bytes([0x01]))
            except Exception as e:
                print(f"Warning: Could not send start-stream: {e}")
            
            self.connected = True
            self.conn_status.setText("Connected")
            self.conn_status.setStyleSheet("color: green; font-weight: bold;")
            self.connect_btn.setText("Disconnect")
            self.connect_btn.setEnabled(True)
            self.status_bar.showMessage(f"Connected to {self.device_address}")
            
        except Exception as e:
            self.status_bar.showMessage(f"Connection failed: {e}")
            QMessageBox.critical(
                self, "Connection Error", 
                f"Failed to connect to device:\n{e}"
            )
            self.connect_btn.setEnabled(True)
    
    async def _disconnect(self):
        """Async BLE disconnection."""
        if self.client:
            try:
                # Send stop stream command (matching logger protocol)
                await self.client.write_gatt_char(CTRL_CHAR_UUID, bytes([0x00]))
            except:
                pass
            try:
                await self.client.disconnect()
            except:
                pass
            self.client = None
        
        self.connected = False
        self.conn_status.setText("Not connected")
        self.conn_status.setStyleSheet("color: red; font-weight: bold;")
        self.connect_btn.setText("Connect")
        self.status_bar.showMessage("Disconnected")
        self.classification_display.reset()
        self.rec_indicator.setStyleSheet("color: gray; font-size: 24pt;")
        self.rec_status.setText("Idle - Flip switch on D1 to record")
    
    def _switch_notification_handler(self, sender, data: bytearray):
        """Handle switch state notifications."""
        state = data[0]
        self.switch_state_changed.emit(state == 1)
    
    def _result_notification_handler(self, sender, data: bytearray):
        """Handle classification result notifications."""
        # Parse result: "class_name:confidence"
        try:
            result_str = data.decode('utf-8').strip()
            if ':' in result_str:
                class_name, conf_str = result_str.split(':', 1)
                confidence = float(conf_str)
                self.classification_received.emit(class_name, confidence)
        except Exception as e:
            print(f"Error parsing result: {e}")
    
    @Slot(bool)
    def on_switch_state(self, recording: bool):
        """Handle switch state change."""
        self.is_recording = recording
        
        if recording:
            self.rec_indicator.setStyleSheet("color: red; font-size: 24pt;")
            self.rec_status.setText("Recording... Flip switch to stop and classify")
            self.status_bar.showMessage("Recording serve data...")
        else:
            self.rec_indicator.setStyleSheet("color: gray; font-size: 24pt;")
            self.rec_status.setText("Processing classification...")
            self.status_bar.showMessage("Stopped recording - classifying...")
    
    @Slot(str, float)
    def on_classification(self, class_name: str, confidence: float):
        """Handle classification result."""
        self.classification_display.update_prediction(class_name, confidence)
        
        # For a real implementation, you'd get all class confidences
        # For now, just show the predicted class with high confidence
        confidences = {cls: 0.0 for cls in SERVE_CLASSES}
        if class_name in SERVE_CLASSES:
            confidences[class_name] = confidence
        
        self.classification_display.update_confidences(confidences)
        
        display_name = class_name.replace("-", " ").title()
        self.status_bar.showMessage(
            f"Classification: {display_name} ({confidence:.1f}%)"
        )
        
        self.rec_status.setText("Idle - Flip switch on D1 to record")
    
    def closeEvent(self, event):
        """Handle window close event."""
        if self.connected:
            asyncio.ensure_future(self._disconnect())
        event.accept()


def main():
    """Main entry point."""
    # Setup asyncio event loop for Qt
    app = QApplication(sys.argv)
    
    # Create and configure event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Create GUI
    gui = ServeSenseClassifierGUI()
    gui.show()
    
    # Run event loop
    with loop:
        try:
            loop.run_until_complete(
                asyncio.create_task(_qt_event_loop(app))
            )
        except KeyboardInterrupt:
            pass
    
    sys.exit(0)


async def _qt_event_loop(app):
    """Run Qt event loop asynchronously."""
    while True:
        app.processEvents()
        await asyncio.sleep(0.01)


if __name__ == "__main__":
    main()
