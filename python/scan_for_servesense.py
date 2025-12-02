#!/usr/bin/env python3
"""
Enhanced BLE scanner specifically for ServeSense device.
Uses multiple scans with increasing timeouts to handle Windows BLE discovery issues.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from ble_utils import setup_windows_event_loop, init_windows_com_threading
from bleak import BleakScanner

async def scan_with_retries():
    """Scan for ServeSense with multiple retries and increasing timeouts."""
    print("=" * 70)
    print("Enhanced ServeSense Scanner")
    print("=" * 70)
    print()
    
    # Initialize COM
    if sys.platform == "win32":
        print("Initializing Windows BLE...")
        init_windows_com_threading()
        print()
    
    print("Scanning for ServeSense device...")
    print("This may take up to 30 seconds on Windows.")
    print()
    
    timeouts = [5, 10, 15]  # Try with increasing timeouts
    all_devices = {}
    
    for attempt, timeout in enumerate(timeouts, 1):
        print(f"Scan attempt {attempt}/{len(timeouts)} (timeout: {timeout}s)...")
        
        try:
            devices = await BleakScanner.discover(timeout=timeout)
            
            # Collect all devices
            for dev in devices:
                if dev.address not in all_devices:
                    all_devices[dev.address] = dev
                    if dev.name:
                        marker = " ← ServeSense!" if "ServeSense" in dev.name or "Serve" in dev.name else ""
                        print(f"  Found: {dev.name:30s} ({dev.address}){marker}")
            
            # Check if we found ServeSense
            for addr, dev in all_devices.items():
                if dev.name and ("ServeSense" in dev.name or "Serve" in dev.name):
                    print()
                    print("=" * 70)
                    print(f"✅ SUCCESS! Found ServeSense at {dev.address}")
                    print("=" * 70)
                    print()
                    print("You can now:")
                    print(f"  1. Run the GUI: python run_gui.py")
                    print(f"  2. Or connect directly: python run_gui.py --address {dev.address}")
                    return 0
            
            print(f"  Total devices found so far: {len(all_devices)}")
            print()
            
        except Exception as e:
            print(f"  ⚠️  Scan error: {e}")
            print()
    
    print("=" * 70)
    print("❌ ServeSense NOT found after all attempts")
    print("=" * 70)
    print()
    
    if all_devices:
        print(f"Found {len(all_devices)} other BLE devices:")
        for addr, dev in all_devices.items():
            name = dev.name if dev.name else "(no name)"
            print(f"  - {name:30s} ({addr})")
        print()
    
    print("Possible issues:")
    print()
    print("  1. Windows Bluetooth Stack Limitation")
    print("     - Some BLE devices are not detected by Windows")
    print("     - This is a known Windows limitation, not a Python issue")
    print()
    print("  2. Device Name Not Broadcasting")
    print("     - Device might be advertising but without a name")
    print("     - Check serial output: should show '[BLE] Advertising as ServeSense'")
    print()
    print("  3. Bluetooth Adapter Compatibility")
    print("     - Try updating Bluetooth drivers")
    print("     - Check Device Manager for Bluetooth adapter")
    print()
    print("Solutions to try:")
    print()
    print("  1. Use nRF Connect app from Microsoft Store")
    print("     - It uses a different BLE stack and might work better")
    print("     - Look for 'ServeSense' or UUID 0xFF00")
    print()
    print("  2. Try connecting with MAC address directly")
    print("     - If nRF Connect finds it, note the MAC address")
    print("     - Run: python run_gui.py --address XX:XX:XX:XX:XX:XX")
    print()
    print("  3. Use a different computer/Bluetooth adapter")
    print("     - Some Windows Bluetooth adapters work better than others")
    print()
    
    return 1

def main():
    """Main entry point."""
    setup_windows_event_loop()
    result = asyncio.run(scan_with_retries())
    return result

if __name__ == "__main__":
    sys.exit(main())
