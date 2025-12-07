Serve Sense – Tennis Serve Insights
===================================

Serve Sense is a wearable tennis serve analysis system built on the Seeed XIAO ESP32S3. The system includes:

1. **Data Logger** - Captures high-fidelity 6-axis IMU data (100 Hz) during serve motions via BLE
2. **ML Classifier** - Real-time on-device serve classification with TensorFlow Lite Micro
3. **Haptic Feedback** - Vibration motor patterns for each serve type
4. **Web GUI** - Browser-based visualization using Web Bluetooth API

The system classifies serves into 4 categories: good-serve, jerky-motion, lacks-pronation, and short-swing.

Hardware & Sensors
------------------

- **Microcontroller**: Seeed XIAO ESP32S3 Sense (or plain XIAO ESP32S3 + battery board)
- **IMU**: ICM-20600 6-axis sensor (or on-board BMI270)
- **Haptic Feedback**: Vibration motor on pin A0
- **Visual Feedback**: Built-in LED (LED_BUILTIN)
- **User Input**: Physical switch on pin D1
- **Connectivity**: BLE (ArduinoBLE library) for wireless data transmission

Current firmware assumes ICM-20600; adjust `imu_provider.cpp` for other IMU models.

Repository Layout
-----------------

- `firmware/serve_sense_logger/` – PlatformIO project for data collection; streams accel/gyro over BLE at 100 Hz with serve-segment markers. See logger directory for details.
- `firmware/serve_sense_classifier/` – TensorFlow Lite Micro inference app running real-time serve classification with haptic and LED feedback. Includes web-based GUI for visualization (see `README_CLASSIFIER.md`).
- `python/` – Desktop tooling:
  - `collect_ble.py` – BLE central logger using `bleak`, writes NDJSON/Parquet.
  - `ble_utils.py` – BLE scanning and connection utilities.
  - `segment_serves.py` – Simple peak/pause segmentation utilities.
  - `serve_labels.py` – Labeling utilities for recorded serves.
  - `combine_recordings.py` – Merge multiple recording sessions.
- `notebooks/` – Jupyter notebooks for data analysis, model training, and prototyping. Includes `ServeSense.ipynb` for end-to-end workflow.
- `models/` – Exported `.tflite` model files and metadata.
- `data/` – Raw and processed recordings (gitignored by default; see `data/.gitkeep`).

Getting Started
---------------

### Classifier GUI (Recommended for Testing)

The classifier includes a web-based GUI for real-time classification visualization:

1. Flash the classifier firmware:
   ```bash
   cd firmware/serve_sense_classifier
   pio run -t upload
   ```

2. Open `ServeSenseClassifier.html` in a Chrome/Edge browser (requires Web Bluetooth API)

3. Connect to your device and view:
   - Real-time serve classification (good-serve, jerky-motion, lacks-pronation, short-swing)
   - Confidence scores for all classes
   - Classification statistics
   - Haptic and LED feedback on the device

For detailed classifier documentation, see `firmware/serve_sense_classifier/README_CLASSIFIER.md`.

### Data Collection

1. Install Python dependencies:
   ```bash
   cd python
   pip install -r requirements.txt
   ```

2. Flash the logger firmware:
   ```bash
   cd firmware/serve_sense_logger
   pio run -t upload
   ```

3. Use the BLE collection script:
   ```bash
   cd python
   python collect_ble.py --out ../data/sessions/serve_001.parquet
   ```

4. Label and process data using notebooks in `notebooks/`

Choosing the First Model
------------------------

The current classifier uses a TensorFlow Lite Micro model with:
- **Input**: (160, 6) - 160 samples of 6-axis IMU data (3-axis accel + 3-axis gyro)
- **Output**: 4 classes - good-serve, jerky-motion, lacks-pronation, short-swing
- **Quantization**: int8 for efficient on-device inference
- **Threshold**: 35% confidence minimum for classification

The model was trained using data collected from the logger and processed in notebooks. To improve or retrain:
1. Collect more labeled serves using the logger
2. Process and augment data in `notebooks/ServeSense.ipynb`
3. Export the trained model as `.tflite` and convert to C array
4. Update `firmware/serve_sense_classifier/src/serve_model_data.cpp`

Roadmap
-------

- [x] Build working classifier with haptic and LED feedback
- [x] Create web-based GUI for classification visualization
- [x] Implement 4-class serve classification (good-serve, jerky-motion, lacks-pronation, short-swing)
- [ ] Improve racket attachment + vibration damping to reduce IMU noise
- [ ] Capture ≥100 labeled serves per class from multiple players
- [ ] Experiment with data augmentation techniques
- [ ] Benchmark feature pipelines: raw window vs. FFT vs. quaternion space
- [ ] Add battery monitoring and power management

Publishing to GitHub
--------------------

Project repository: https://github.com/jeremychungg/serve_sense

To clone and set up:
```bash
git clone https://github.com/jeremychungg/serve_sense
cd serve_sense
pip install -r python/requirements.txt
```

Questions / Next Steps
----------------------

For specific documentation:
- **Classifier firmware**: See `firmware/serve_sense_classifier/README_CLASSIFIER.md`
- **Logger firmware**: See `firmware/serve_sense_logger/` directory
- **Data processing**: See notebooks in `notebooks/`

For issues and feature requests, visit the GitHub repository.

