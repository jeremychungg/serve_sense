#!/usr/bin/env python3
"""
Quick BLE diagnostic test for Windows.
Tests if we can discover the ServeSense device.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from ble_utils import setup_windows_event_loop, init_windows_com_threading, scan_devices

async def test_scan():
    """Test BLE scanning."""
    print("=" * 60)
    print("BLE Diagnostic Test")
    print("=" * 60)
    print(f"Platform: {sys.platform}")
    print()
    
    # Initialize COM threading
    if sys.platform == "win32":
        print("Initializing Windows COM threading...")
        init_windows_com_threading()
        print("✓ COM threading initialized")
        print()
    
    print("Scanning for BLE devices (5 seconds)...")
    print("Make sure your Xiao ESP32S3 is powered on!")
    print()
    
    try:
        devices = await scan_devices(timeout=5.0)
        
        print(f"\nFound {len(devices)} BLE devices:")
        print("-" * 60)
        
        servesense_found = False
        for address, name in devices:
            is_target = "ServeSense" in name or "Serve" in name
            marker = " ← TARGET!" if is_target else ""
            print(f"  {name:30s} ({address}){marker}")
            if is_target:
                servesense_found = True
        
        print("-" * 60)
        print()
        
        if servesense_found:
            print("✓ SUCCESS: ServeSense device found!")
            print("\nYou can now try connecting with the GUI:")
            print("  python run_gui.py")
        else:
            print("✗ WARNING: ServeSense device NOT found")
            print("\nTroubleshooting:")
            print("  1. Check that your Xiao ESP32S3 is powered on")
            print("  2. Check the device's serial output for 'Advertising as ServeSense'")
            print("  3. Verify Windows Bluetooth is enabled (Settings → Bluetooth)")
            print("  4. Try scanning again (BLE discovery can be slow on Windows)")
            print("  5. Power cycle the device and try again")
        
    except Exception as e:
        print(f"✗ ERROR: Scan failed: {e}")
        print("\nTroubleshooting:")
        print("  1. Verify Windows Bluetooth is enabled")
        print("  2. Check that Bluetooth driver is working (Device Manager)")
        print("  3. Try restarting the Bluetooth service:")
        print("     Restart-Service bthserv")
        return 1
    
    return 0

def main():
    """Main entry point."""
    # Setup Windows event loop
    setup_windows_event_loop()
    
    # Run the test
    result = asyncio.run(test_scan())
    
    print()
    print("=" * 60)
    print("Test complete!")
    print("=" * 60)
    
    return result

if __name__ == "__main__":
    sys.exit(main())
