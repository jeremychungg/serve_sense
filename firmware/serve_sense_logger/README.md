# Serve Sense Logger Firmware

Derived from the Magic Wand data collection sketch, this PlatformIO project streams ICM-20600 accel/gyro data over BLE and USB for tennis-serve capture.

## Build & Flash

```bash
cd firmware/serve_sense_logger
pio run -t upload
pio device monitor -b 115200
```

## Controls

- Press the XIAO BOOT button to toggle capture; the green LED mirrors capture state.
- `CTRL_UUID` commands (write single byte):
  - `0x00` – stop streaming / mark segment end
  - `0x01` – start new session and mark serve boundary
  - `0x02` – inject manual serve marker (e.g., voice cue)

## Packet Layout (36 bytes)

| Field        | Type    |
|--------------|---------|
| millis_ms    | uint32  |
| session      | uint16  |
| sequence     | uint16  |
| ax..gz       | 6 × float32 |
| flags        | uint8 (bit0=capture_on, bit1=marker_edge) |
| reserved     | 3 × uint8 |

The Python collector consumes this payload via `collect_ble.py`.

