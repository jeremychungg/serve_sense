"""
Combine multiple Serve Sense JSONL recordings into a single JSON file for labeling.

This script:
  - Reads multiple .jsonl files (one sample per line)
  - Groups samples by serve_id (using marker_edge flags)
  - Outputs a JSON file with serves that can be labeled

Usage:
  python combine_recordings.py --in data/sessions/*.jsonl --out data/labeling/serves.json
  python combine_recordings.py --in data/sessions --out data/labeling/serves.json

Valid labels (9 classes):
  - flat_good_mechanics, flat_low_toss, flat_low_racket_speed
  - slice_good_mechanics, slice_low_toss, slice_low_racket_speed
  - kick_good_mechanics, kick_low_toss, kick_low_racket_speed
"""

import argparse
import datetime as dt
import json
import pathlib
import sys
from typing import Dict, List

from serve_labels import SERVE_LABELS, get_label_display_name, is_valid_label, normalize_label


def load_jsonl_recording(filepath: pathlib.Path) -> List[Dict]:
    """Load a JSONL file (one JSON object per line)."""
    samples = []
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))
    return samples


def segment_into_serves(samples: List[Dict]) -> List[Dict]:
    """Group samples into serves based on marker_edge flags.
    
    If samples already have 'label' field (from GUI recording), preserves it.
    """
    serves = []
    current_serve = None
    serve_id = 0
    serve_labels = []  # Collect labels from samples in current serve
    
    for sample in samples:
        # Start new serve on marker edge
        if sample.get("marker_edge", False):
            if current_serve is not None:
                # Set label from samples if all samples have the same label
                if serve_labels:
                    # Use majority label or first label if all samples labeled
                    label_counts = {}
                    for lbl in serve_labels:
                        if lbl:  # Skip None labels
                            label_counts[lbl] = label_counts.get(lbl, 0) + 1
                    if label_counts:
                        current_serve["label"] = max(label_counts.items(), key=lambda x: x[1])[0]
                serves.append(current_serve)
            serve_id += 1
            serve_labels = []
            current_serve = {
                "serve_id": serve_id,
                "session": sample.get("session", 0),
                "samples": [],
                "label": None,  # Will be set from samples if available
                "notes": ""
            }
        
        # Only add samples when capture is on
        if sample.get("capture_on", False) and current_serve is not None:
            current_serve["samples"].append({
                "timestamp_ms": sample["timestamp_ms"],
                "sequence": sample["sequence"],
                "ax": sample["ax"], "ay": sample["ay"], "az": sample["az"],
                "gx": sample["gx"], "gy": sample["gy"], "gz": sample["gz"]
            })
            # Collect label from sample if present
            if "label" in sample and sample["label"]:
                serve_labels.append(normalize_label(sample["label"]))
    
    # Add final serve if exists
    if current_serve is not None and current_serve["samples"]:
        # Set label from samples
        if serve_labels:
            label_counts = {}
            for lbl in serve_labels:
                if lbl:
                    label_counts[lbl] = label_counts.get(lbl, 0) + 1
            if label_counts:
                current_serve["label"] = max(label_counts.items(), key=lambda x: x[1])[0]
        serves.append(current_serve)
    
    return serves


def parse_args():
    parser = argparse.ArgumentParser(
        description="Combine Serve Sense JSONL recordings into JSON for labeling"
    )
    parser.add_argument(
        "--in",
        dest="input_paths",
        required=True,
        nargs="+",
        help="Input JSONL files or directory containing JSONL files"
    )
    parser.add_argument(
        "--out",
        dest="output_path",
        required=True,
        type=pathlib.Path,
        help="Output JSON file for labeling"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    
    # Collect all JSONL files
    jsonl_files = []
    for path_str in args.input_paths:
        path = pathlib.Path(path_str)
        if path.is_file() and path.suffix == ".jsonl":
            jsonl_files.append(path)
        elif path.is_dir():
            jsonl_files.extend(path.glob("*.jsonl"))
        else:
            # Try glob pattern
            jsonl_files.extend(pathlib.Path(".").glob(path_str))
    
    if not jsonl_files:
        print("[ERR] No JSONL files found", file=sys.stderr)
        return 1
    
    print(f"[INFO] Found {len(jsonl_files)} JSONL file(s)")
    
    # Load and combine all serves
    all_serves = []
    for jsonl_file in sorted(jsonl_files):
        print(f"[INFO] Loading {jsonl_file.name}...")
        samples = load_jsonl_recording(jsonl_file)
        serves = segment_into_serves(samples)
        all_serves.extend(serves)
        print(f"  -> {len(serves)} serve(s), {len(samples)} sample(s)")
    
    # Validate existing labels and normalize them
    labeled_count = 0
    for serve in all_serves:
        if serve.get("label"):
            label = serve["label"]
            if is_valid_label(label):
                serve["label"] = normalize_label(label)
                labeled_count += 1
            else:
                print(f"[WARN] Serve {serve['serve_id']} has invalid label: {label}", file=sys.stderr)
                serve["label"] = None
    
    # Create output structure
    output = {
        "metadata": {
            "total_serves": len(all_serves),
            "labeled_serves": labeled_count,
            "valid_labels": SERVE_LABELS,
            "source_files": [str(f) for f in jsonl_files],
            "created_at": dt.datetime.now().isoformat()
        },
        "serves": all_serves
    }
    
    # Write JSON file
    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_path, "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"\n[OK] Combined {len(all_serves)} serves into {args.output_path}")
    print(f"[INFO] Ready for labeling. Edit the JSON file and set 'label' for each serve.")
    print(f"\nValid labels (9 classes):")
    for label in SERVE_LABELS:
        print(f"  - {label} ({get_label_display_name(label)})")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

