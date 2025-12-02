# Windows BLE Setup Guide

This guide provides detailed instructions for setting up and using Serve Sense on Windows 10/11 with Bluetooth Low Energy (BLE) support.

## Problem Background

Windows has specific requirements for BLE operations that differ from Linux and macOS:

1. **COM Threading**: Windows requires proper COM (Component Object Model) initialization for BLE
2. **Event Loop Policy**: Windows async operations need WindowsProactorEventLoopPolicy
3. **GUI Conflicts**: Threading conflicts can occur between GUI frameworks and BLE operations

The error "Thread is configured for Windows GUI but callbacks are not working" occurs when these requirements are not properly handled.

## Solution

The Serve Sense project now includes comprehensive Windows BLE support through the `ble_utils.py` module.

## Installation

### 1. Install Python Dependencies

```bash
cd python
pip install -r requirements.txt
```

### 2. Install Windows-Specific Dependencies

Install pywin32 for COM threading support:

```bash
pip install pywin32
```

This package provides `pythoncom`, which is used to initialize COM threading in apartment-threaded mode (COINIT_APARTMENTTHREADED).

### 3. Verify Bluetooth Setup

1. Open Windows Settings → Devices → Bluetooth & other devices
2. Ensure Bluetooth is turned on
3. Verify your Bluetooth adapter is working (check Device Manager)
4. Make sure your Serve Sense device is powered on

## Using the Applications

All three interfaces now support Windows properly:

### GUI Application (Recommended)

```bash
python run_gui.py
```

The GUI automatically handles:
- Windows COM initialization
- Event loop policy configuration
- Thread-safe BLE operations
- Automatic retry on connection failures

### Live View (matplotlib-based)

```bash
python live_view.py
```

Features Windows-compatible threading:
- BLE operations run in separate thread with proper event loop
- COM initialization in BLE thread
- Safe matplotlib integration

### Command-Line Data Collection

```bash
python collect_ble.py --out data/sessions/test.parquet
```

Uses robust connection management:
- Automatic device discovery with retry
- Exponential backoff on failures
- Proper cleanup on errors

## Technical Details

### What Was Fixed

#### 1. Event Loop Configuration

Before:
```python
asyncio.run(some_ble_function())  # May fail on Windows
```

After:
```python
from ble_utils import setup_windows_event_loop
setup_windows_event_loop()  # Configures WindowsProactorEventLoopPolicy
asyncio.run(some_ble_function())  # Now works properly
```

#### 2. COM Threading Initialization

Added to all BLE operations:
```python
from ble_utils import init_windows_com_threading
init_windows_com_threading()  # Initializes COM in apartment-threaded mode
```

#### 3. Connection Robustness

New BLEConnectionManager with retry logic:
```python
from ble_utils import BLEConnectionManager

async with BLEConnectionManager(address) as client:
    # Automatic retry on connection failures
    # Proper cleanup on errors
    # Reconnection with exponential backoff
    ...
```

#### 4. Device Discovery

Enhanced discovery with retry:
```python
from ble_utils import discover_device_with_retry

address = await discover_device_with_retry(
    "ServeSense",
    timeout=5.0,
    max_retries=3,
    backoff_factor=2.0
)
```

### Windows-Specific Code Paths

The code automatically detects Windows and applies appropriate settings:

```python
import sys

if sys.platform == "win32":
    # Windows-specific initialization
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    import pythoncom
    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
```

On Linux/macOS, these are no-ops and don't affect functionality.

## Troubleshooting

### Error: "pythoncom module not found"

**Solution**: Install pywin32:
```bash
pip install pywin32
```

### Error: "No BLE device found"

**Solutions**:
1. Ensure Bluetooth is enabled in Windows Settings
2. Power cycle your Serve Sense device
3. Try scanning multiple times (Windows discovery can be slow)
4. Check that device is not connected to another application
5. Verify Bluetooth adapter is working in Device Manager

### Error: "Connection timeout"

**Solutions**:
1. The application now includes automatic retry with exponential backoff
2. If still failing, check Bluetooth signal strength
3. Move closer to the device
4. Restart Windows Bluetooth service:
   ```powershell
   Restart-Service bthserv
   ```

### Slow Device Discovery

Windows BLE discovery can take longer than other platforms:
- Default timeout is 5 seconds per attempt
- Automatic retry up to 3 times
- Each retry uses longer timeout (exponential backoff)
- Total discovery time may be up to 15-30 seconds

This is normal Windows behavior and the application handles it automatically.

### Connection Drops

If connections drop frequently:
1. Update Bluetooth adapter drivers
2. Check for USB power management settings (disable USB selective suspend)
3. Move closer to reduce interference
4. Check Windows power plan settings

### GUI Not Responding During BLE Operations

The application now properly separates BLE operations into background threads:
- GUI should remain responsive during scanning
- GUI should remain responsive during connection
- If frozen, check Task Manager for other issues

## Bluetooth Adapter Compatibility

### Recommended Adapters

Works best with:
- Built-in Bluetooth 4.0+ on modern laptops
- Intel Wireless-AC adapters with Bluetooth
- Qualcomm/Atheros Bluetooth adapters
- Realtek Bluetooth adapters (with updated drivers)

### Potentially Problematic

May have issues with:
- Very old USB Bluetooth dongles (< Bluetooth 4.0)
- Generic Chinese USB adapters (driver issues)
- Adapters with outdated drivers

### Checking Your Adapter

1. Open Device Manager
2. Expand "Bluetooth"
3. Look for your Bluetooth adapter
4. Right-click → Properties → Driver tab
5. Check driver date (should be recent)
6. Update driver if needed

## Advanced Configuration

### Adjusting Retry Parameters

Edit `ble_utils.py` to customize retry behavior:

```python
# In discover_device_with_retry()
timeout=5.0,        # Scan timeout per attempt
max_retries=3,      # Number of retry attempts
backoff_factor=2.0  # Exponential backoff multiplier
```

### Adjusting Logging

Enable debug logging for more details:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Testing

Run the test suite to verify Windows BLE support:

```bash
python test_ble_utils.py
```

All tests should pass on Windows with pywin32 installed.

## Performance Notes

### Expected Performance

- Device discovery: 5-30 seconds (depending on environment)
- Connection establishment: 2-5 seconds
- Data streaming: 100 Hz with minimal latency
- Reconnection: 5-10 seconds with automatic retry

### Optimization Tips

1. Use direct address (`--address XX:YY:...`) to skip discovery
2. Keep device close during initial pairing
3. Minimize Bluetooth interference (turn off other BLE devices)
4. Use latest Windows updates for best BLE stack performance

## Known Limitations

1. Windows BLE discovery is slower than Linux/macOS (OS limitation)
2. Some USB Bluetooth adapters have driver issues (hardware/driver limitation)
3. COM threading requires pywin32 (necessary dependency)

## Support

If you continue to experience issues:

1. Check the GitHub Issues page for known problems
2. Verify all dependencies are installed: `pip list`
3. Test with the included test suite: `python test_ble_utils.py`
4. Include system information when reporting issues:
   - Windows version (Settings → System → About)
   - Python version: `python --version`
   - Bluetooth adapter model (Device Manager)
   - Error messages and logs

## References

- [Windows BLE API Documentation](https://docs.microsoft.com/windows/uwp/devices-sensors/bluetooth-low-energy-overview)
- [Bleak Documentation](https://bleak.readthedocs.io/)
- [Python asyncio on Windows](https://docs.python.org/3/library/asyncio-platforms.html#windows)
- [COM Threading in Python](https://docs.microsoft.com/windows/win32/com/choosing-the-threading-model)
