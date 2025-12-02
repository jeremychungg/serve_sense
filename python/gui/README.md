# Serve Sense GUI

Modern PySide6-based graphical user interface for the Serve Sense tennis serve analysis project.

## Overview

The Serve Sense GUI provides a professional, user-friendly interface for:
- Real-time BLE device connection and management
- Live 3D racket orientation visualization
- Real-time accelerometer and gyroscope data plotting
- Serve type labeling and data recording
- Session management and data export

## Features

### 1. Device Connection Management
- **BLE Device Scanning**: Automatically discover nearby Serve Sense devices
- **Connection Status**: Visual indicators for connection state
- **Device Selection**: Choose from discovered devices
- **Auto-reconnection**: Automatically reconnect to devices

### 2. Real-time Visualization
- **3D Orientation Display**: Live racket orientation using complementary filter
- **Accelerometer Plots**: Real-time plots for ax, ay, az (±4g range)
- **Gyroscope Plots**: Real-time plots for gx, gy, gz (±500 dps range)
- **Configurable History**: 300 samples of history by default

### 3. Data Collection
- **Serve Type Labeling**: Select from 9 predefined serve types:
  - Flat (Good Mechanics / Low Toss / Low Racket Speed)
  - Slice (Good Mechanics / Low Toss / Low Racket Speed)
  - Kick (Good Mechanics / Low Toss / Low Racket Speed)
- **Recording Controls**: Start/stop recording with visual feedback
- **Sample Counter**: Real-time count of recorded samples
- **File Output**: JSON Lines (.jsonl) format for easy processing

### 4. User Interface
- **Menu Bar**: Organized menus for file, connection, recording, and help
- **Keyboard Shortcuts**:
  - `Ctrl+S`: Scan for devices
  - `Ctrl+C`: Connect/disconnect
  - `Ctrl+R`: Start/stop recording
  - `Ctrl+L`: Clear plots
  - `Ctrl+Q`: Quit application
- **Status Bar**: Connection status and sample rate display
- **Responsive Design**: Adjustable window size and splitters

## Installation

### Requirements

Install the required dependencies:

```bash
cd python
pip install -r requirements.txt
```

Key dependencies:
- PySide6 >= 6.6.0
- PySide6-Addons >= 6.6.0
- matplotlib >= 3.8.0
- bleak == 0.22.2
- numpy >= 1.26.0

## Usage

### Basic Usage

Launch the GUI application:

```bash
cd python/gui
python serve_sense_gui.py
```

### Command Line Options

```bash
# Specify BLE device address (skip scanning)
python serve_sense_gui.py --address XX:YY:ZZ:AA:BB:CC

# Specify output directory for recordings
python serve_sense_gui.py --out-dir /path/to/output
```

### Workflow

1. **Connect to Device**
   - Click "Scan" to discover nearby Serve Sense devices
   - Select a device from the dropdown menu
   - Click "Connect" to establish BLE connection

2. **Monitor Live Data**
   - Observe real-time 3D racket orientation
   - View live accelerometer and gyroscope plots
   - Data automatically streams when connected

3. **Record Serves**
   - Select serve type from the dropdown menu
   - Click "Start Recording" (or press Ctrl+R)
   - Perform serves while recording
   - Click "Stop Recording" when finished
   - Files are saved as `serve_<label>_<timestamp>.jsonl`

4. **Manage Sessions**
   - Use File → Change Output Directory to set save location
   - Use Recording → Clear Plots to reset visualizations
   - Connection status shown in status bar

## File Format

Recorded data is saved in JSON Lines format (.jsonl), with one JSON object per line:

```json
{
  "timestamp_ms": 12345,
  "session": 1,
  "sequence": 42,
  "ax": 0.123, "ay": -0.456, "az": 0.987,
  "gx": 12.34, "gy": -45.67, "gz": 78.90,
  "flags": 1,
  "capture_on": true,
  "marker_edge": false,
  "label": "flat_good_mechanics"
}
```

This format is compatible with the existing `collect_ble.py` data structure and can be easily loaded for analysis:

```python
import json

samples = []
with open('serve_flat_good_mechanics_20241202_120000.jsonl', 'r') as f:
    for line in f:
        samples.append(json.loads(line))
```

## Architecture

### Component Structure

```
python/gui/
├── __init__.py              # Package initialization
└── serve_sense_gui.py       # Main GUI application
```

### Key Classes

- **`ServeSenseGUI`**: Main window and application coordinator
- **`BLEWorker`**: Async BLE operations in separate thread
- **`OrientationFilter`**: Complementary filter for orientation estimation
- **`OrientationCanvas`**: 3D matplotlib canvas for racket visualization
- **`TimeSeriesCanvas`**: 2D matplotlib canvas for IMU data plots

### Threading Model

The application uses Qt's threading model:
- **Main Thread**: UI updates and user interactions
- **BLE Thread**: Async BLE operations using asyncio
- **Signals/Slots**: Thread-safe communication between threads

### Integration with Existing Code

The GUI reuses key components from the existing codebase:
- **BLE Communication**: Based on `collect_ble.py` and `live_view.py`
- **Orientation Filter**: Copied from `live_view.py`
- **Packet Format**: Uses same `PACKET_STRUCT` as firmware
- **Serve Labels**: Imports from `serve_labels.py`
- **Data Format**: Compatible with existing analysis pipeline

## Comparison with matplotlib-based Interface

### Advantages of PySide6 GUI:

1. **Better Threading**: Async BLE operations don't block UI
2. **Professional Look**: Native widgets and modern styling
3. **Responsive**: Smooth interaction even during data streaming
4. **Organized Layout**: Proper grouping and splitters
5. **Menu System**: Organized access to all features
6. **Keyboard Shortcuts**: Efficient workflow
7. **Status Indicators**: Clear connection and recording state
8. **Error Handling**: User-friendly error messages

### Retained Features:

- All visualization capabilities from `live_view.py`
- Same orientation filter and 3D display
- Same accelerometer/gyroscope plots
- Same serve labeling system
- Same data recording format
- Compatible output files

## Troubleshooting

### BLE Connection Issues

- Ensure Bluetooth is enabled on your system
- Make sure the Serve Sense device is powered on
- Try scanning again if device is not found
- Check device is not connected to another application

### Plot Performance

- Reduce history length if plots are slow
- Close other applications using graphics resources
- Ensure matplotlib backend is properly configured

### Recording Issues

- Check write permissions for output directory
- Ensure sufficient disk space
- Verify device is connected before recording
- Stop and restart recording if issues occur

## Development

### Adding New Features

The modular design makes it easy to extend:
- Add new visualization canvases
- Implement additional data processing
- Add export formats
- Customize UI appearance

### Customization

Key parameters can be adjusted in the code:
- `SAMPLE_DT`: Sampling interval (default: 0.01s)
- `ALPHA`: Complementary filter alpha (default: 0.02)
- Plot history length (default: 300 samples)
- Y-axis ranges for plots

## License

This GUI is part of the Serve Sense project. See repository root for license information.

## Support

For issues, questions, or contributions, please use the GitHub repository issue tracker.
