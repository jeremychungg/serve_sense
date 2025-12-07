# ServeSense Classifier

Real-time tennis serve classification using TensorFlow Lite on Xiao ESP32S3.

## Overview

This classifier runs a trained machine learning model on the Xiao ESP32S3 to identify different types of tennis serves and provide feedback on technique. The system detects 9 different serve classifications:

### Serve Types & Mechanics

**Flat Serves:**
- ✅ Flat – Good Mechanics
- ⚠️ Flat – Low Toss
- ⚠️ Flat – Low Racket Speed

**Slice Serves:**
- ✅ Slice – Good Mechanics
- ⚠️ Slice – Low Toss
- ⚠️ Slice – Low Racket Speed

**Kick Serves:**
- ✅ Kick – Good Mechanics
- ⚠️ Kick – Low Toss
- ⚠️ Kick – Low Racket Speed

## Hardware Requirements

- **Xiao ESP32S3** with IMU (ICM-20600)
- Physical switch connected to **D1 pin** (for recording control)
- USB cable for power and programming

## Software Requirements

- PlatformIO (for firmware upload)
- Chrome/Edge browser (for Web Bluetooth)
- Trained TensorFlow Lite model (must be in `magic_wand_model_data.cpp`)

## Setup Instructions

### 1. Flash Firmware to Xiao

```bash
cd firmware/serve_sense_classifier
pio run --target upload
```

### 2. Open Web Interface

1. Open `web/ServeSenseClassifier.html` in Chrome or Edge
2. Click "🔌 Connect to ServeSense"
3. Select your BLESense device from the popup

### 3. Record and Classify a Serve

**Using Physical Switch (Recommended):**
1. Flip the switch to **ON** position (connects D1 to GND)
2. Perform your tennis serve motion
3. Flip the switch to **OFF** position
4. Wait for classification result

**Using Serial Commands (Alternative):**
1. Open Serial Monitor (115200 baud)
2. Press `r` to start recording
3. Perform your tennis serve motion
4. Press `s` to stop and classify

## How It Works

### Firmware (Xiao ESP32S3)

1. **IMU Data Collection**: Reads accelerometer and gyroscope data at ~104 Hz
2. **Motion Integration**: Converts gyro data (gy, gz) into a 2D stroke path
3. **Rasterization**: Transforms the stroke into a 32×32×3 image (like Magic Wand)
4. **ML Inference**: Runs TensorFlow Lite model to classify the serve
5. **BLE Transmission**: Sends classification result to web app

### Web Interface

1. **BLE Connection**: Connects to Xiao via Web Bluetooth API
2. **Switch Monitoring**: Listens for switch state changes (ON/OFF)
3. **Result Display**: Shows classification with confidence score
4. **History Tracking**: Maintains log of previous classifications

## BLE Characteristics

| UUID Suffix | Name | Type | Description |
|-------------|------|------|-------------|
| `300a` | Stroke | Read | Raw stroke points (for debugging) |
| `300b` | Switch | Read/Notify | Switch state (0=OFF, 1=ON) |
| `300c` | Result | Read/Notify | Classification result string |

## Result Format

The classification result is sent as a string:
```
<label>:<confidence>%
```

Examples:
- `flat_good_mechanics:87.3%`
- `kick_low_toss:62.1%`
- `UNKNOWN:25.4%`

## Confidence Thresholds

- **Minimum Confidence**: 35% (if below, result is "UNKNOWN")
- **Minimum Margin**: 8% (top prediction must beat #2 by this amount)

These ensure the model only reports results it's confident about.

## Troubleshooting

### "Not Connected" in Web App
- Ensure Xiao is powered on and BLE is working
- Check that you're using Chrome/Edge (Safari doesn't support Web Bluetooth)
- Try refreshing the page and reconnecting

### "UNKNOWN" Classifications
- Ensure you're performing a full serve motion
- Check that the switch toggles during the entire motion
- Verify the model file is correctly flashed

### No Response After Recording
- Check Serial Monitor for error messages
- Ensure the gesture has enough data points (>4 required)
- Verify IMU is working (should see motion data in Serial)

### Switch Not Detected
- Verify switch is connected to D1 pin and GND
- Check that switch is configured as INPUT_PULLUP
- Test switch with multimeter (should be LOW when ON)

## Model Training

The TensorFlow Lite model must be trained on serve data and converted to C array format. See `notebooks/` for training scripts.

The model expects:
- **Input**: 32×32×3 int8 rasterized image
- **Output**: 9 class probabilities (int8 quantized)

## Files

```
serve_sense/
├── firmware/serve_sense_classifier/
│   ├── src/
│   │   ├── main.cpp                    # Main classification firmware
│   │   ├── imu_provider.cpp/h          # IMU interface
│   │   ├── rasterize_stroke.cpp/h      # Stroke → image converter
│   │   └── magic_wand_model_data.cpp/h # TFLite model
│   └── platformio.ini
├── web/
│   └── ServeSenseClassifier.html       # Web-based UI
└── README_CLASSIFIER.md                # This file
```

## Future Improvements

- [ ] Add real-time IMU visualization during recording
- [ ] Display top-3 predictions with probabilities
- [ ] Add confidence calibration settings
- [ ] Export classification history to CSV
- [ ] Add vibration feedback on Xiao after classification
- [ ] Multi-serve session analysis

## Credits

Based on TensorFlow Lite Micro Magic Wand example, adapted for tennis serve classification.

---

**Note**: Make sure your model file (`magic_wand_model_data.cpp`) is trained on the 9 serve classes listed above. Using a different model (like the digit recognition model) will give incorrect results.
