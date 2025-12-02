#!/usr/bin/env python3
"""
Find ServeSense by service UUID instead of name.
This works around Windows BLE name discovery issues.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from ble_utils import setup_windows_event_loop, init_windows_com_threading
from bleak import BleakScanner, BleakClient

# ServeSense service UUID
SERVICE_UUID = "0000ff00-0000-1000-8000-00805f9b34fb"

async def find_by_service():
    """Find device by checking services."""
    print("=" * 70)
    print("ServeSense Finder (by Service UUID)")
    print("=" * 70)
    print()
    print(f"Looking for service UUID: {SERVICE_UUID}")
    print("This may take a few minutes as we check each device...")
    print()
    
    # Initialize
    if sys.platform == "win32":
        init_windows_com_threading()
    
    # Scan for all devices
    print("Step 1: Scanning for all BLE devices...")
    devices = await BleakScanner.discover(timeout=10.0)
    print(f"Found {len(devices)} devices")
    print()
    
    # Check each device for the service
    print("Step 2: Checking each device for ServeSense service...")
    print("(This is slow but thorough)")
    print()
    
    for i, dev in enumerate(devices, 1):
        name = dev.name if dev.name else "(no name)"
        print(f"[{i}/{len(devices)}] Checking {name:30s} ({dev.address})...", end=" ", flush=True)
        
        try:
            async with BleakClient(dev.address, timeout=5.0) as client:
                services = client.services
                
                # Check if our service is present
                for service in services:
                    if service.uuid.lower() == SERVICE_UUID.lower():
                        print("✅ FOUND!")
                        print()
                        print("=" * 70)
                        print(f"🎉 SUCCESS! Found ServeSense device!")
                        print("=" * 70)
                        print()
                        print(f"Device Name:    {name}")
                        print(f"MAC Address:    {dev.address}")
                        print(f"Service UUID:   {SERVICE_UUID}")
                        print()
                        print("You can now connect with:")
                        print(f"  python run_gui.py --address {dev.address}")
                        print()
                        
                        # Save address to file for easy access
                        address_file = Path(__file__).parent / "servesense_address.txt"
                        address_file.write_text(dev.address)
                        print(f"Address saved to: {address_file}")
                        print()
                        return 0
                
                print("no")
                        
        except Exception as e:
            print(f"error ({e})")
            continue
    
    print()
    print("=" * 70)
    print("❌ ServeSense device not found")
    print("=" * 70)
    print()
    print("Troubleshooting:")
    print("  1. Make sure device is powered on and BLE is advertising")
    print("  2. Check serial output for '[BLE] Advertising as ServeSense'")
    print("  3. Try power cycling the device")
    print("  4. Some devices may be unreachable due to security settings")
    print()
    
    return 1

def main():
    """Main entry point."""
    setup_windows_event_loop()
    result = asyncio.run(find_by_service())
    return result

if __name__ == "__main__":
    sys.exit(main())
