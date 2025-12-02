#!/usr/bin/env python3
"""
Quick serial monitor to check device output.
Reads serial output from Xiao ESP32S3 to verify firmware is running.
"""

import sys
import time
import serial.tools.list_ports

def list_ports():
    """List all available serial ports."""
    ports = serial.tools.list_ports.comports()
    if not ports:
        print("No serial ports found!")
        return None
    
    print("Available COM ports:")
    print("-" * 60)
    for i, port in enumerate(ports, 1):
        print(f"  {i}. {port.device}")
        if port.description:
            print(f"     Description: {port.description}")
        if port.manufacturer:
            print(f"     Manufacturer: {port.manufacturer}")
        print()
    
    return [port.device for port in ports]

def read_serial(port, baudrate=115200, duration=10):
    """Read serial output for a short duration."""
    try:
        import serial
        print(f"Opening {port} at {baudrate} baud...")
        print(f"Reading for {duration} seconds...")
        print("=" * 60)
        
        ser = serial.Serial(port, baudrate, timeout=1)
        start_time = time.time()
        
        ble_advertising = False
        boot_msg = False
        
        while time.time() - start_time < duration:
            if ser.in_waiting:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    print(line)
                    
                    # Check for key messages
                    if "[BOOT]" in line:
                        boot_msg = True
                    if "Advertising as ServeSense" in line or "[BLE]" in line:
                        ble_advertising = True
        
        ser.close()
        print("=" * 60)
        print()
        
        # Summary
        if boot_msg and ble_advertising:
            print("✅ Device is running correctly and advertising BLE!")
            print("   Try running: python test_ble_scan.py")
            return 0
        elif boot_msg:
            print("⚠️  Device booted but BLE might not be advertising")
            print("   Check for error messages above")
            return 1
        else:
            print("❌ No boot messages detected")
            print("   - Device might be running different firmware")
            print("   - Or device might not be booting properly")
            return 1
            
    except serial.SerialException as e:
        print(f"❌ Error opening port: {e}")
        print("   - Make sure no other program is using this port")
        print("   - Try closing Arduino IDE or other serial monitors")
        return 1
    except ImportError:
        print("❌ pyserial not installed")
        print("   Install with: pip install pyserial")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

def main():
    """Main entry point."""
    print("=" * 60)
    print("Xiao ESP32S3 Serial Monitor")
    print("=" * 60)
    print()
    
    # List available ports
    ports = list_ports()
    if not ports:
        return 1
    
    # If only one port, use it automatically
    if len(ports) == 1:
        port = ports[0]
        print(f"Using {port} (only port available)")
        print()
    else:
        # Let user choose
        try:
            choice = int(input("Select port number: ")) - 1
            port = ports[choice]
        except (ValueError, IndexError):
            print("Invalid selection")
            return 1
    
    # Read serial output
    return read_serial(port, duration=10)

if __name__ == "__main__":
    sys.exit(main())
