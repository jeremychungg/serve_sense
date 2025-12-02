Serve Sense – Tennis Serve Insights
===================================

Serve Sense is a fast-follow to the Magic Wand demo tailored for the Seeed XIAO ESP32S3 mounted on a tennis racket. The MVP focuses on:

1. Capturing high-fidelity IMU streams for entire serve motions.
2. Labeling + curating examples (good serve, net fault, long, etc.).
3. Training a lightweight classifier that can eventually run fully on-device.

Hardware & Sensors
------------------

- Seeed XIAO ESP32S3 Sense (or plain XIAO ESP32S3 + battery board).
- 6-axis IMU (on-board BMI270 or external ICM-20600/ICM-42688). Current firmware assumes ICM-20600 pinout identical to Magic Wand rig; adjust `pin_config.h` otherwise.
- Optional BLE central (phone or laptop) for untethered logging; USB CDC logging also available for lab bring-up.

Repository Layout
-----------------

- `firmware/serve_sense_logger/` – PlatformIO project derived from `MW_DataCollection`; streams accel/gyro over BLE and/or USB at 100 Hz with serve-segment markers.
- `firmware/serve_sense_classifier/` – Skeleton inference app based on the Magic Wand classifier. Hook in a converted TFLM model once trained.
- `python/` – Desktop tooling:
  - `gui/` – **NEW**: Modern PySide6-based GUI for real-time visualization and data collection (see `python/gui/README.md`)
  - `collect_ble.py` – BLE central logger using `bleak`, writes NDJSON/Parquet.
  - `live_view.py` – Matplotlib-based live IMU visualization (legacy).
  - `segment_serves.py` – Simple peak/pause segmentation utilities.
  - `train_baseline.py` – Scikit-learn + TensorFlow starter for experimenting with classical models before quantization.
- `notebooks/` – Colab-ready exploratory data analysis and model prototyping.
- `models/` – Placeholder for exported `.tflite` files and metadata.
- `docs/` – Architecture notes, experiment logs, schematics.
- `data/` – Raw and processed recordings (gitignored by default; see `data/.gitkeep`).

Getting Started
---------------

### Quick Start with GUI (Recommended)

1. Install Python dependencies:
   ```bash
   cd python
   pip install -r requirements.txt
   ```

2. Launch the GUI application:
   ```bash
   python run_gui.py
   ```
   
3. Use the GUI to:
   - Scan and connect to your Serve Sense device
   - View real-time 3D racket orientation and IMU data
   - Record labeled serve sessions with one-click controls
   - Export data in JSON Lines format for analysis

For detailed GUI documentation, see `python/gui/README.md`.

### Alternative: Command-Line Tools

1. Install PlatformIO Core (`pip install platformio`) and ESP-IDF environment if not already set up for Magic Wand.
2. From `firmware/serve_sense_logger`, run `pio run -t upload` to flash the logger.
3. Use `python/collect_ble.py --out data/sessions/serve_001.parquet` while hitting `start`/`stop` BLE characteristics (or press the on-board button) to capture serves.
4. Label sessions via the provided notebook template (`notebooks/01_labeling.ipynb`) and export to `data/labels.csv`.
5. Train quick baselines with `python/train_baseline.py --config configs/baseline.yaml`. Export the best `.tflite` to `models/serve_sense_int8.tflite` and copy the C array into `firmware/serve_sense_classifier/src/serve_sense_model_data.cpp`.

Choosing the First Model
------------------------

- Start simple: treat each serve as a fixed-length 3-axis accel + gyro window (e.g., 2 s @ 100 Hz → 1,200 features). Classical models (RandomForest, 1D CNN) quickly reveal separability.
- For on-device deployment, aim for an 8–12 class softmax (good, long, wide, net, warmup, idle, etc.). Keep tensor arena ≤128 KB to stay within XIAO limits.
- Quantization-aware training (`tfmot.quantization.keras`) prevents accuracy collapses when converting to int8.

Roadmap
-------

- [ ] Improve racket attachment + vibration damping to reduce IMU noise.
- [ ] Capture ≥100 labeled serves per class from at least 3 players.
- [ ] Benchmark feature pipelines: raw window vs. FFT vs. quaternion space.
- [ ] Port the winning model into the classifier firmware, add OLED / BLE feedback.

Publishing to GitHub
--------------------

1. `cd serve_sense`
2. `git init && git add . && git commit -m "Serve Sense MVP scaffolding"`
3. `gh repo create <yourusername>/serve-sense --source=. --public`
4. `git push -u origin main`

Replace `<yourusername>` with your GitHub handle. If you prefer keeping private, add `--private`.

Questions / Next Steps
----------------------

Open issues and ideas live in `docs/roadmap.md`. Feel free to tag TODOs inline in firmware/Python files to keep track of experimental knobs.

