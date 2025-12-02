"""
BLE utility module with Windows-compatible operations.

This module provides Windows-safe BLE operations including:
- Proper Windows COM threading initialization
- Event loop policy configuration for Windows
- Device discovery with retry mechanisms
- Robust error handling and logging

Usage:
    from ble_utils import setup_windows_event_loop, discover_device_with_retry
    
    # Initialize Windows-compatible event loop
    setup_windows_event_loop()
    
    # Discover device with retry
    address = await discover_device_with_retry("ServeSense")
"""

import asyncio
import logging
import sys
from typing import Optional, List, Tuple

from bleak import BleakScanner, BleakClient

# Configure logging
logger = logging.getLogger(__name__)


def setup_windows_event_loop():
    """
    Configure asyncio event loop for Windows compatibility.
    
    On Windows, sets WindowsProactorEventLoopPolicy for proper BLE operation.
    This must be called before any asyncio.run() calls on Windows.
    
    Safe to call on non-Windows platforms (no-op).
    """
    if sys.platform == "win32":
        # Use WindowsProactorEventLoopPolicy for better BLE compatibility
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        logger.info("Windows event loop policy configured (ProactorEventLoop)")


def init_windows_com_threading():
    """
    Initialize Windows COM threading for BLE operations.
    
    NOTE: Modern versions of bleak (0.20+) handle COM initialization internally.
    Manually calling pythoncom.CoInitializeEx() can cause conflicts with asyncio.
    This function is kept for backward compatibility but is now a no-op.
    
    Safe to call on non-Windows platforms (no-op).
    Returns True if on Windows, False otherwise.
    """
    if sys.platform != "win32":
        return False
    
    # Modern bleak versions handle COM initialization automatically
    # Manual initialization can cause "Thread is configured for Windows GUI but callbacks are not working"
    logger.info("Windows detected - COM initialization handled by bleak")
    return True


async def discover_device_with_retry(
    name_hint: str,
    timeout: float = 5.0,
    max_retries: int = 3,
    backoff_factor: float = 2.0
) -> str:
    """
    Discover BLE device with exponential backoff retry.
    
    Args:
        name_hint: Device name substring to search for
        timeout: Timeout for each discovery attempt (seconds)
        max_retries: Maximum number of retry attempts
        backoff_factor: Multiplier for exponential backoff
        
    Returns:
        Device address (MAC address)
        
    Raises:
        RuntimeError: If device not found after all retries
    """
    attempt = 0
    current_timeout = timeout
    
    while attempt < max_retries:
        try:
            logger.info(
                f"[BLE] Scanning for '{name_hint}' (attempt {attempt + 1}/{max_retries}, "
                f"timeout={current_timeout:.1f}s)..."
            )
            
            devices = await BleakScanner.discover(timeout=current_timeout)
            
            for dev in devices:
                if dev.name and name_hint.lower() in dev.name.lower():
                    logger.info(f"[BLE] Found {dev.name} @ {dev.address}")
                    return dev.address
            
            # Device not found in this scan
            logger.warning(
                f"[BLE] Device '{name_hint}' not found in scan "
                f"(found {len(devices)} devices total)"
            )
            
        except Exception as e:
            logger.error(f"[BLE] Scan error on attempt {attempt + 1}: {e}")
        
        # Prepare for retry
        attempt += 1
        if attempt < max_retries:
            wait_time = backoff_factor ** attempt
            logger.info(f"[BLE] Retrying in {wait_time:.1f} seconds...")
            await asyncio.sleep(wait_time)
            # Increase timeout for next attempt
            current_timeout *= backoff_factor
    
    raise RuntimeError(
        f"No BLE device found matching '{name_hint}' after {max_retries} attempts"
    )


async def scan_devices(timeout: float = 5.0) -> List[Tuple[str, str]]:
    """
    Scan for all available BLE devices.
    
    Args:
        timeout: Scan timeout in seconds
        
    Returns:
        List of (address, name) tuples for discovered devices
    """
    try:
        logger.info(f"[BLE] Scanning for devices (timeout={timeout}s)...")
        devices = await BleakScanner.discover(timeout=timeout)
        
        result = []
        for dev in devices:
            name = dev.name if dev.name else "(unnamed device)"
            result.append((dev.address, name))
        
        logger.info(f"[BLE] Found {len(result)} devices (including unnamed)")
        return result
        
    except Exception as e:
        logger.error(f"[BLE] Device scan failed: {e}")
        raise


class BLEConnectionManager:
    """
    Manages BLE connections with Windows-compatible error handling.
    
    This class provides a robust wrapper around BleakClient with:
    - Automatic reconnection logic
    - Windows-specific error handling
    - Connection state tracking
    - Proper cleanup on errors
    
    Usage:
        async with BLEConnectionManager(address) as client:
            await client.start_notify(uuid, callback)
            # ... use client ...
    """
    
    def __init__(self, address: str, reconnect_attempts: int = 3):
        """
        Initialize connection manager.
        
        Args:
            address: BLE device address
            reconnect_attempts: Number of reconnection attempts on failure
        """
        self.address = address
        self.reconnect_attempts = reconnect_attempts
        self.client: Optional[BleakClient] = None
        self._connected = False
    
    async def __aenter__(self):
        """Connect to device."""
        await self.connect()
        return self.client
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Disconnect from device."""
        await self.disconnect()
        return False
    
    async def connect(self):
        """
        Connect to BLE device with retry logic.
        
        Raises:
            RuntimeError: If connection fails after all retries
        """
        for attempt in range(self.reconnect_attempts):
            try:
                logger.info(
                    f"[BLE] Connecting to {self.address} "
                    f"(attempt {attempt + 1}/{self.reconnect_attempts})..."
                )
                
                self.client = BleakClient(self.address)
                await self.client.connect()
                
                if not self.client.is_connected:
                    raise RuntimeError("Connection failed (client not connected)")
                
                self._connected = True
                logger.info(f"[BLE] Successfully connected to {self.address}")
                return
                
            except Exception as e:
                logger.error(f"[BLE] Connection attempt {attempt + 1} failed: {e}")
                
                if self.client:
                    try:
                        await self.client.disconnect()
                    except:
                        pass
                    self.client = None
                
                if attempt < self.reconnect_attempts - 1:
                    wait_time = 2 ** attempt
                    logger.info(f"[BLE] Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
        
        raise RuntimeError(
            f"Failed to connect to {self.address} after {self.reconnect_attempts} attempts"
        )
    
    async def disconnect(self):
        """Disconnect from device with cleanup."""
        if self.client and self._connected:
            try:
                logger.info(f"[BLE] Disconnecting from {self.address}...")
                await self.client.disconnect()
                logger.info("[BLE] Disconnected successfully")
            except Exception as e:
                logger.error(f"[BLE] Error during disconnect: {e}")
            finally:
                self._connected = False
                self.client = None
    
    @property
    def is_connected(self) -> bool:
        """Check if currently connected."""
        return self._connected and self.client and self.client.is_connected
