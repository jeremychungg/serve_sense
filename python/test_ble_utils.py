#!/usr/bin/env python3
"""
Test script for BLE utilities with Windows compatibility.

This script validates the BLE utility functions without requiring
actual BLE hardware.
"""

import asyncio
import sys
import unittest
from unittest.mock import Mock, patch, AsyncMock

# Add current directory to path
sys.path.insert(0, str(__file__.rsplit('/', 1)[0]))

from ble_utils import (
    setup_windows_event_loop,
    init_windows_com_threading,
    discover_device_with_retry,
    scan_devices,
    BLEConnectionManager
)


class TestWindowsEventLoop(unittest.TestCase):
    """Test Windows event loop setup."""
    
    def test_setup_windows_event_loop_on_linux(self):
        """Test that setup is safe on Linux."""
        # Should not raise any errors on Linux
        setup_windows_event_loop()
        self.assertTrue(True)  # Made it through without error
    
    def test_init_com_threading_on_linux(self):
        """Test that COM init is safe on Linux."""
        # Should return False on non-Windows
        result = init_windows_com_threading()
        if sys.platform != "win32":
            self.assertFalse(result)


class TestDeviceDiscovery(unittest.IsolatedAsyncioTestCase):
    """Test device discovery with retry logic."""
    
    @patch('ble_utils.BleakScanner.discover')
    async def test_discover_device_with_retry_success(self, mock_discover):
        """Test successful device discovery."""
        # Mock device
        mock_device = Mock()
        mock_device.name = "ServeSense"
        mock_device.address = "AA:BB:CC:DD:EE:FF"
        
        mock_discover.return_value = [mock_device]
        
        # Should find device on first attempt
        address = await discover_device_with_retry("ServeSense", timeout=1.0, max_retries=1)
        
        self.assertEqual(address, "AA:BB:CC:DD:EE:FF")
        self.assertEqual(mock_discover.call_count, 1)
    
    @patch('ble_utils.BleakScanner.discover')
    async def test_discover_device_with_retry_not_found(self, mock_discover):
        """Test device not found after retries."""
        # Mock no devices found
        mock_discover.return_value = []
        
        # Should raise RuntimeError after all retries
        with self.assertRaises(RuntimeError) as context:
            await discover_device_with_retry("ServeSense", timeout=0.5, max_retries=2)
        
        self.assertIn("No BLE device found", str(context.exception))
        # Should have tried max_retries times
        self.assertEqual(mock_discover.call_count, 2)
    
    @patch('ble_utils.BleakScanner.discover')
    async def test_discover_device_case_insensitive(self, mock_discover):
        """Test case-insensitive device name matching."""
        mock_device = Mock()
        mock_device.name = "servesense"  # lowercase
        mock_device.address = "AA:BB:CC:DD:EE:FF"
        
        mock_discover.return_value = [mock_device]
        
        # Should find device regardless of case
        address = await discover_device_with_retry("SERVESENSE", timeout=1.0, max_retries=1)
        self.assertEqual(address, "AA:BB:CC:DD:EE:FF")
    
    @patch('ble_utils.BleakScanner.discover')
    async def test_scan_devices(self, mock_discover):
        """Test scanning for all devices."""
        # Mock multiple devices
        dev1 = Mock()
        dev1.name = "ServeSense"
        dev1.address = "AA:BB:CC:DD:EE:FF"
        
        dev2 = Mock()
        dev2.name = "OtherDevice"
        dev2.address = "11:22:33:44:55:66"
        
        dev3 = Mock()
        dev3.name = None  # Device without name
        dev3.address = "99:88:77:66:55:44"
        
        mock_discover.return_value = [dev1, dev2, dev3]
        
        devices = await scan_devices(timeout=1.0)
        
        # Should only return devices with names
        self.assertEqual(len(devices), 2)
        self.assertIn(("AA:BB:CC:DD:EE:FF", "ServeSense"), devices)
        self.assertIn(("11:22:33:44:55:66", "OtherDevice"), devices)


class TestBLEConnectionManager(unittest.IsolatedAsyncioTestCase):
    """Test BLE connection manager."""
    
    @patch('ble_utils.BleakClient')
    async def test_connection_manager_success(self, mock_client_class):
        """Test successful connection with context manager."""
        # Mock client
        mock_client = AsyncMock()
        mock_client.is_connected = True
        mock_client.connect = AsyncMock()
        mock_client.disconnect = AsyncMock()
        mock_client_class.return_value = mock_client
        
        address = "AA:BB:CC:DD:EE:FF"
        
        # Use context manager
        async with BLEConnectionManager(address) as client:
            self.assertEqual(client, mock_client)
            self.assertTrue(client.is_connected)
        
        # Should have called connect and disconnect
        mock_client.connect.assert_called_once()
        mock_client.disconnect.assert_called_once()
    
    @patch('ble_utils.BleakClient')
    async def test_connection_manager_retry(self, mock_client_class):
        """Test connection retry logic."""
        # Mock client that fails first, succeeds second
        mock_client = AsyncMock()
        mock_client.connect = AsyncMock(side_effect=[
            Exception("Connection failed"),  # First attempt fails
            None  # Second attempt succeeds
        ])
        mock_client.is_connected = True
        mock_client.disconnect = AsyncMock()
        mock_client_class.return_value = mock_client
        
        address = "AA:BB:CC:DD:EE:FF"
        manager = BLEConnectionManager(address, reconnect_attempts=3)
        
        # Should succeed after retry
        await manager.connect()
        
        # Should have tried twice
        self.assertEqual(mock_client.connect.call_count, 2)
    
    @patch('ble_utils.BleakClient')
    async def test_connection_manager_all_retries_fail(self, mock_client_class):
        """Test all connection retries fail."""
        # Mock client that always fails
        mock_client = AsyncMock()
        mock_client.connect = AsyncMock(side_effect=Exception("Connection failed"))
        mock_client.is_connected = False
        mock_client.disconnect = AsyncMock()
        mock_client_class.return_value = mock_client
        
        address = "AA:BB:CC:DD:EE:FF"
        manager = BLEConnectionManager(address, reconnect_attempts=2)
        
        # Should raise RuntimeError after all retries
        with self.assertRaises(RuntimeError) as context:
            await manager.connect()
        
        self.assertIn("Failed to connect", str(context.exception))
        # Should have tried reconnect_attempts times
        self.assertEqual(mock_client.connect.call_count, 2)


class TestAsyncEventLoop(unittest.TestCase):
    """Test async event loop handling."""
    
    def test_event_loop_policy_on_linux(self):
        """Test event loop policy on Linux."""
        # Set up event loop
        setup_windows_event_loop()
        
        # Create a simple async function
        async def simple_task():
            await asyncio.sleep(0.01)
            return "success"
        
        # Should be able to run async code
        result = asyncio.run(simple_task())
        self.assertEqual(result, "success")


def main():
    """Run all tests."""
    print("=" * 60)
    print("BLE Utils - Windows Compatibility Tests")
    print("=" * 60)
    
    # Set up event loop for tests
    setup_windows_event_loop()
    
    # Run all tests
    print("\nRunning All Test Cases")
    print("=" * 60)
    
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestWindowsEventLoop))
    suite.addTests(loader.loadTestsFromTestCase(TestAsyncEventLoop))
    suite.addTests(loader.loadTestsFromTestCase(TestDeviceDiscovery))
    suite.addTests(loader.loadTestsFromTestCase(TestBLEConnectionManager))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    total_run = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    passed = total_run - failures - errors
    
    print(f"\nTotal tests run: {total_run}")
    print(f"Passed: {passed}")
    print(f"Failed: {failures}")
    print(f"Errors: {errors}")
    
    if result.wasSuccessful():
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {failures + errors} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
