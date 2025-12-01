"""
Annotate serve_id segments in a raw Serve Sense parquet/csv log.

Example:
  python segment_serves.py --in data/raw/session01.parquet \
      --out data/processed/session01_segmented.parquet
"""

import argparse
import pathlib

import pandas as pd


def assign_serve_ids(df: pd.DataFrame) -> pd.DataFrame:
    serve_id = -1
    ids = []
    for _, row in df.iterrows():
        if row.get("marker_edge", 0) == 1:
            serve_id += 1
        ids.append(serve_id if row.get("capture_on", 0) else -1)
    df = df.copy()
    df["serve_id"] = ids
    return df


def parse_args():
    parser = argparse.ArgumentParser(description="Segment Serve Sense logs into serves")
    parser.add_argument("--in", dest="input_path", required=True, type=pathlib.Path)
    parser.add_argument("--out", dest="output_path", required=True, type=pathlib.Path)
    return parser.parse_args()


def main():
    args = parse_args()
    if args.input_path.suffix == ".csv":
        df = pd.read_csv(args.input_path)
    else:
        df = pd.read_parquet(args.input_path)
    df = assign_serve_ids(df)
    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    if args.output_path.suffix == ".csv":
        df.to_csv(args.output_path, index=False)
    else:
        df.to_parquet(args.output_path, index=False)
    print(f"[OK] Wrote segmented dataset to {args.output_path}")


if __name__ == "__main__":
    main()

