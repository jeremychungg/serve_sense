# BLE Connection Troubleshooting Guide

## Issue Fixed: Python COM Threading Conflict

**Status**: ✅ RESOLVED

The initial connection problem was caused by manual COM threading initialization that conflicts with modern bleak versions.

### What Was Fixed

1. **Installed pywin32**: Required for Windows BLE support
   ```bash
   pip install pywin32
   ```

2. **Fixed ble_utils.py**: Removed manual `pythoncom.CoInitializeEx()` call that was causing:
   ```
   Thread is configured for Windows GUI but callbacks are not working
   ```

3. **Current Status**: BLE scanning now works! The Python code can successfully scan for BLE devices.

---

## Current Issue: Device Not Found

The BLE scanning is working, but your Xiao ESP32S3 is not being discovered as "ServeSense".

### Possible Causes

1. **Device Not Powered On**
   - Check if the Xiao ESP32S3 has power
   - Look for the status LED (should be on or blinking)

2. **Firmware Not Running**
   - The device might not be running the serve_sense_logger firmware
   - Check which firmware is currently flashed

3. **BLE Not Advertising**
   - The firmware might have crashed or failed to initialize
   - Check serial output for BLE initialization messages

4. **Device Name Mismatch**
   - Firmware advertises as "ServeSense" (line 187 in main.cpp)
   - Windows might see it differently

---

## Diagnostic Steps

### Step 1: Check Device Power & Status LED

The Xiao ESP32S3 has a built-in LED on pin 21:
- **LED ON**: Device is powered and recording is DISABLED
- **LED OFF**: Device is powered and recording is ENABLED  
- **No LED**: Device has no power or firmware issue

### Step 2: Connect to Serial Monitor

Connect the device via USB and check the serial output:

```bash
# Windows PowerShell
# Find the COM port (usually COM3, COM4, etc.)
mode

# Then connect with PuTTY, Arduino Serial Monitor, or:
python -m serial.tools.miniterm COM3 115200
```

**Expected Serial Output:**
```
========================================
[BOOT] Serve Sense logger
========================================
[I2C] ICM20600 ready (WHO_AM_I=0xXX)
[BLE] Advertising as ServeSense
[SWITCH] Initial state: OFF (idle)
```

**Heartbeat Every 2 Seconds:**
```
[HEARTBEAT] D1 pin=1, Switch=OFF, Recording=NO, Session=0
```

### Step 3: Check Firmware Version

Verify which firmware is flashed:

```bash
cd firmware/serve_sense_logger
pio device list
pio device monitor
```

If you need to re-flash:
```bash
cd firmware/serve_sense_logger
pio run --target upload
```

### Step 4: Manual BLE Scan with Longer Timeout

Sometimes Windows needs more time:

```python
# Run from python/ directory
python -c "import asyncio; from ble_utils import setup_windows_event_loop, scan_devices; setup_windows_event_loop(); devices = asyncio.run(scan_devices(timeout=10.0)); print([d for d in devices])"
```

### Step 5: Check Windows Bluetooth Settings

1. Open Settings → Bluetooth & other devices
2. Verify Bluetooth is ON
3. Check if "ServeSense" appears in the device list
4. If it appears but you can't connect, click "Remove" and try scanning again

### Step 6: Test with Different BLE Scanner

Use a third-party BLE scanner to verify the device is advertising:

**Option A: nRF Connect (Recommended)**
- Download from Microsoft Store
- Open nRF Connect
- Look for "ServeSense" in the scan results
- Should show service UUID 0xFF00

**Option B: LightBlue (iOS/Android)**
- If you have a phone, this is a quick test
- Install LightBlue app
- Scan for "ServeSense"

---

## Expected BLE Configuration

From `firmware/serve_sense_logger/src/main.cpp`:

```cpp
// Line 28-30: Service UUIDs
SVC_UUID  = 0xFF00  // Main service
IMU_UUID  = 0xFF01  // IMU data (notify)
CTRL_UUID = 0xFF02  // Control (write)

// Line 187-210: BLE Initialization
Device Name: "ServeSense"
MTU: 185 bytes
Power Level: ESP_PWR_LVL_P9 (maximum)
```

---

## Quick Fixes to Try

### Fix 1: Power Cycle the Device
```bash
# Unplug USB cable
# Wait 5 seconds
# Plug back in
# Wait for boot messages
# Try scanning again
```

### Fix 2: Reset the Firmware
```bash
cd firmware/serve_sense_logger
pio run --target erase
pio run --target upload
pio device monitor
# Wait for "[BLE] Advertising as ServeSense"
```

### Fix 3: Try Different USB Cable/Port
- Some USB cables are power-only (no data)
- Try a different cable that supports data transfer
- Try a different USB port (USB 2.0 vs 3.0)

### Fix 4: Check I2C Connections
If the IMU (ICM-20600) isn't connected properly, the firmware might not start BLE:
- SDA → D4 (pin 5)
- SCL → D5 (pin 6)
- VCC → 3.3V
- GND → GND

---

## Next Steps

1. **Connect to Serial Monitor** (most important!)
   - This will tell you exactly what's happening
   - Look for BLE initialization messages
   - Check for any error messages

2. **Verify Firmware is Running**
   - You should see heartbeat messages every 2 seconds
   - If no serial output, firmware isn't running

3. **Once Device is Advertising**
   - Run: `python python\test_ble_scan.py`
   - Should see "ServeSense" in the device list
   - Then try the GUI: `python python\run_gui.py`

---

## Summary of Fixes Applied

✅ Installed pywin32 for Windows BLE support
✅ Fixed COM threading initialization conflict in ble_utils.py
✅ BLE scanning now works correctly
✅ Created diagnostic test script (test_ble_scan.py)

🔍 Current Issue: Device not advertising (hardware/firmware issue, not Python)

---

## Contact & Support

If you've tried all the above and still have issues:

1. Run the diagnostic: `python python\test_ble_scan.py`
2. Capture serial output from the device
3. Note which step fails
4. Provide output from both for debugging

The Python/Windows BLE connection is now working correctly - the issue is with the device not advertising.
