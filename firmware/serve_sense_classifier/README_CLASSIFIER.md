# ServeSense Classifier

Real-time tennis serve classification using TensorFlow Lite on Xiao ESP32S3.

## Overview

This classifier runs a trained machine learning model on the Xiao ESP32S3 to identify different types of tennis serves and provide instant feedback via haptic vibration and LED patterns. The system classifies 4 distinct serve types based on technique quality.

### Serve Classifications

- ✅ **Good Serve** - Proper mechanics and execution
- ⚠️ **Jerky Motion** - Inconsistent or rough movement
- ⚠️ **Lacks Pronation** - Insufficient wrist pronation during contact
- ⚠️ **Short Swing** - Abbreviated or incomplete swing path

## Hardware Requirements

- **Xiao ESP32S3** with built-in IMU (ICM-20600)
- Physical switch connected to **D1 pin** (ON = LOW/closed to GND, OFF = HIGH/open)
- Vibration motor connected to **A0 pin** (for haptic feedback)
- USB cable for power and programming

## Software Requirements

- PlatformIO (for firmware upload)
- Chrome/Edge browser with Web Bluetooth support
- Trained TensorFlow Lite model (in `serve_model_data.cpp`)

## Setup Instructions

### 1. Flash Firmware to Xiao

```bash
cd firmware/serve_sense_classifier
pio run --target upload
```

### 2. Open Web Interface

**Option A: Web GUI (Recommended)**
1. Open `ServeSenseClassifier.html` in Chrome or Edge
2. Click "Connect to ServeSense"
3. Select your ServeSense device from the Bluetooth popup
4. Wait for connection confirmation

**Option B: Python GUI**
```bash
python classifier_gui.py
```

### 3. Record and Classify a Serve

1. **Start Recording**: Flip the switch to **ON** position (D1 → GND)
   - LED turns on solid
   - Vibration motor activates
   
2. **Perform Motion**: Execute your tennis serve

3. **Stop Recording**: Flip the switch to **OFF** position
   - LED turns off
   - Device processes classification (~1 second)

4. **Get Feedback**: 
   - **Haptic Pattern**: Distinctive vibration sequence
   - **LED Pattern**: Synchronized blink pattern
   - **Web Display**: Classification with confidence scores

### Feedback Patterns

**Good Serve** 🎾
- 3 quick pulses (100ms on, 100ms off)
- Feels celebratory!

**Jerky Motion** ⚡
- 2 long pulses (400ms on, 200ms off)
- Mimics the rough motion

**Lacks Pronation** ⚠️
- 1 long + 2 short pulses (500ms, then 2×100ms)
- Warning pattern

**Short Swing** 🔄
- 4 very short rapid pulses (80ms on, 80ms off)
- Feels quick and abbreviated

**Startup** ✅
- 1 second continuous pulse on boot
- Confirms hardware is working

## How It Works

### Firmware (Xiao ESP32S3)

1. **IMU Data Collection**: Reads 6-axis sensor data at ~40 Hz (ax, ay, az, gx, gy, gz)
2. **Buffer Management**: Stores 160 samples (4 seconds @ 40Hz) in memory
3. **Data Quantization**: Converts float32 IMU data to int8 for model input
4. **ML Inference**: Runs TensorFlow Lite Micro model on device
5. **Classification**: Outputs probabilities for all 4 serve types
6. **Multi-Modal Feedback**:
   - BLE transmission to web/Python GUI
   - Haptic vibration patterns via motor
   - Visual LED blink patterns
   - Serial output for debugging

### Web Interface

1. **BLE Connection**: Connects via Web Bluetooth API (UUID 0xFF00 service)
2. **Real-time Monitoring**: Tracks switch state and recording status
3. **Result Display**: Shows classification with color-coded prediction
4. **Confidence Bars**: Displays all 4 class probabilities visually
5. **Statistics**: Tracks total classifications and timestamps

## BLE Protocol

The classifier uses the same BLE protocol as ServeSense Logger for compatibility.

| UUID | Name | Type | Description |
|------|------|------|-------------|
| `0xFF00` | Service | - | Main BLE service |
| `0xFF01` | IMU Data | Notify | IMU packet stream (compatible with logger) |
| `0xFF02` | Control | Write | Start/stop commands (0x00=stop, 0x01=start) |
| `0xFF04` | Switch State | Notify | Recording state (0=idle, 1=recording) |
| `0xFF05` | Result | Notify | Classification results with all probabilities |

### Result Format

Classification results are sent as:
```
<label>:<conf1>,<conf2>,<conf3>,<conf4>
```

Where:
- `label` = predicted class name or "UNKNOWN"
- `conf1-4` = confidence percentages for [good-serve, jerky-motion, lacks-pronation, short-swing]

Example:
```
good-serve:87.3,5.2,4.1,3.4
```

## Confidence Thresholds

- **Minimum Confidence**: 35% (if below, result is "UNKNOWN")

This ensures the model only reports results when reasonably confident.

## Model Details

**Architecture:**
- Input: (160, 6) int8 tensor - 160 time steps × 6 IMU axes
- Output: (4,) int8 tensor - probabilities for 4 serve types
- Quantization: int8 post-training quantization for efficiency
- Size: ~80KB model + 80KB tensor arena

**Training:**
- Dataset: Tennis serve IMU recordings from multiple players
- Classes: good-serve, jerky-motion, lacks-pronation, short-swing
- Framework: TensorFlow → TensorFlow Lite → TFLite Micro

The model expects raw IMU data (ax, ay, az, gx, gy, gz) sampled at ~40Hz.

## Troubleshooting

### "Not Connected" in Web App
- Ensure Xiao is powered on and firmware is uploaded
- Use Chrome or Edge (Safari doesn't support Web Bluetooth)
- Check that device is advertising as "ServeSense"
- Try refreshing the page and reconnecting

### "UNKNOWN" Classifications
- Ensure you're performing a full serve motion (4 seconds)
- Record the entire swing from start to finish
- Check that motion has sufficient speed and rotation
- Verify the model file is correctly flashed

### No Haptic/LED Feedback
- Check vibration motor connection to A0
- Verify motor ground is connected
- Test motor by touching wires to 3.3V briefly
- LED should always blink on startup (1 second pulse)

### Switch Not Responding
- Verify switch is connected to D1 pin and GND
- Check that switch closes to GND when ON
- Test with multimeter: should read LOW (~0V) when ON
- LED should turn on solid when recording

### Serial Monitor Errors
Common messages:
- `ERROR: IMU initialization failed!` - Check I2C connections
- `ERROR: Inference failed!` - Model may be corrupted, re-upload firmware
- `Tensor allocation failed!` - Increase kTensorArenaSize in code

## Model Training

The TensorFlow Lite model is trained on labeled serve data and converted to C array format for embedded deployment.

**Training Pipeline:**
1. Collect serve data using ServeSense Logger
2. Label and preprocess IMU sequences
3. Train model in TensorFlow/Keras
4. Convert to TensorFlow Lite with int8 quantization
5. Generate C array using `xxd` or similar tool
6. Replace contents in `serve_model_data.cpp`

See the main ServeSense repository for training notebooks and scripts.

## Project Structure

```
serve_sense_classifier/
├── src/
│   ├── main.cpp                    # Main classification firmware
│   ├── imu_provider.cpp/h          # IMU interface (ICM-20600)
│   ├── constants.h                 # Configuration constants
│   ├── serve_model_data.cpp/h      # TFLite model (C array)
│   └── tflm_esp32_port.cpp         # TFLite Micro ESP32 port
├── lib/
│   └── Arduino_TensorFlowLite/     # TFLite Micro library
├── ServeSenseClassifier.html       # Web-based GUI
├── classifier_gui.py               # Python GUI (optional)
├── platformio.ini                  # Build configuration
└── README_CLASSIFIER.md            # This file
```

## Future Improvements

- [x] Add haptic feedback patterns
- [x] Add synchronized LED patterns
- [x] Display all class probabilities in web GUI
- [ ] Add real-time IMU visualization during recording
- [ ] Export classification history to CSV
- [ ] Add confidence calibration settings
- [ ] Multi-serve session analysis with statistics
- [ ] Battery percentage indicator

## Credits

Based on TensorFlow Lite Micro, adapted for real-time tennis serve classification with multi-modal feedback.

**Key Technologies:**
- TensorFlow Lite Micro for embedded ML
- ArduinoBLE for wireless communication
- ESP32 I2C for IMU interface
- ICM-20600 6-axis IMU sensor

---

**For training data collection, use the ServeSense Logger firmware. For model training and evaluation, see the main repository notebooks.**
