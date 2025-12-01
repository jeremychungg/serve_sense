"""
Train a baseline Serve Sense classifier from collected parquet/csv logs.

Example:
  python train_baseline.py --data data/sessions/ --out models/
"""

from __future__ import annotations

import argparse
import pathlib
from typing import List, Tuple

import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.model_selection import train_test_split

FEATURE_COLS = ["ax", "ay", "az", "gx", "gy", "gz"]


def load_sessions(path: pathlib.Path) -> pd.DataFrame:
    files: List[pathlib.Path] = []
    if path.is_file():
        files = [path]
    else:
        files = sorted(path.glob("**/*.parquet")) + sorted(path.glob("**/*.csv"))
    if not files:
        raise FileNotFoundError(f"No parquet/csv files under {path}")
    frames = []
    for f in files:
        if f.suffix == ".csv":
            frames.append(pd.read_csv(f))
        else:
            frames.append(pd.read_parquet(f))
    df = pd.concat(frames, ignore_index=True)
    if "label" not in df.columns:
        raise ValueError("Dataset is missing 'label' column. Add labels before training.")
    return df


def segment_serves(df: pd.DataFrame, window_size: int) -> Tuple[np.ndarray, np.ndarray]:
    segments: List[np.ndarray] = []
    labels: List[str] = []

    current: List[List[float]] = []
    current_label: List[str] = []

    for _, row in df.iterrows():
        if row["marker_edge"] == 1 and current:
            segments.append(resample_segment(np.array(current), window_size))
            labels.append(majority_label(current_label))
            current = []
            current_label = []

        if row["capture_on"] == 0:
            continue

        current.append([row[col] for col in FEATURE_COLS])
        current_label.append(row.get("label", "unknown"))

    if current:
        segments.append(resample_segment(np.array(current), window_size))
        labels.append(majority_label(current_label))

    if not segments:
        raise RuntimeError("No serve segments detected. Check marker_edge values.")

    return np.stack(segments), np.array(labels)


def resample_segment(segment: np.ndarray, window_size: int) -> np.ndarray:
    if len(segment) == window_size:
        return segment
    x_old = np.linspace(0, 1, len(segment))
    x_new = np.linspace(0, 1, window_size)
    resampled = np.stack([np.interp(x_new, x_old, segment[:, i]) for i in range(segment.shape[1])], axis=1)
    return resampled


def majority_label(labels: List[str]) -> str:
    if not labels:
        return "unknown"
    values, counts = np.unique(labels, return_counts=True)
    return values[np.argmax(counts)]


def build_model(window_size: int, feature_dim: int, num_classes: int) -> tf.keras.Model:
    model = tf.keras.Sequential([
        tf.keras.layers.Input(shape=(window_size, feature_dim)),
        tf.keras.layers.Conv1D(32, 5, activation="relu"),
        tf.keras.layers.Conv1D(32, 5, activation="relu"),
        tf.keras.layers.MaxPool1D(2),
        tf.keras.layers.Dropout(0.2),
        tf.keras.layers.Conv1D(64, 3, activation="relu"),
        tf.keras.layers.GlobalAveragePooling1D(),
        tf.keras.layers.Dense(64, activation="relu"),
        tf.keras.layers.Dense(num_classes, activation="softmax"),
    ])
    model.compile(
        optimizer=tf.keras.optimizers.Adam(1e-3),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    return model


def export_tflite(model: tf.keras.Model, out_path: pathlib.Path):
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    tflite_model = converter.convert()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(tflite_model)
    print(f"[OK] Saved TFLite model to {out_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train Serve Sense baseline model")
    parser.add_argument("--data", type=pathlib.Path, required=True, help="Parquet/CSV file or directory")
    parser.add_argument("--window", type=int, default=200, help="Samples per serve window")
    parser.add_argument("--test-split", type=float, default=0.2, help="Test fraction")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch", type=int, default=64)
    parser.add_argument("--out", type=pathlib.Path, default=pathlib.Path("../models/serve_sense_baseline.tflite"))
    return parser.parse_args()


def main():
    args = parse_args()
    df = load_sessions(args.data)
    X, y_raw = segment_serves(df, args.window)

    label_to_id = {label: idx for idx, label in enumerate(sorted(set(y_raw)))}
    y = np.array([label_to_id[label] for label in y_raw])

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=args.test_split, stratify=y, random_state=42
    )

    model = build_model(args.window, len(FEATURE_COLS), len(label_to_id))
    history = model.fit(
        X_train, y_train,
        validation_data=(X_test, y_test),
        epochs=args.epochs,
        batch_size=args.batch,
        verbose=2,
    )

    test_loss, test_acc = model.evaluate(X_test, y_test, verbose=0)
    print(f"[METRIC] test_acc={test_acc:.3f}  test_loss={test_loss:.3f}")

    export_tflite(model, args.out)

    # Save label map for firmware decoding
    label_map_path = args.out.with_suffix(".labels.txt")
    label_map_path.write_text("\n".join(f"{idx},{label}" for label, idx in label_to_id.items()))
    print(f"[OK] Saved label map to {label_map_path}")


if __name__ == "__main__":
    main()

