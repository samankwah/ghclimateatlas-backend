"""
Pre-compute per-district yearly timeseries JSON files.

The original approach loaded the entire climate_yearly_values.csv.gz (45 MB / 307 MB
uncompressed, ~3.17M rows) into memory on every cold start. This does not fit within
Vercel serverless function limits (memory, cold-start time), so the /timeseries
endpoint would hang indefinitely.

This script pre-computes one gzipped JSON file per district containing all
(variable, scenario) yearly points with p10/p50/p90 values. At request time,
the endpoint reads only the single file for the requested district — fast and
memory-efficient.

Run once after `climate_yearly_values.csv.gz` is updated:
    python scripts/precompute_district_timeseries.py
"""
from __future__ import annotations

import csv
import gzip
import io
import json
from collections import defaultdict
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
YEARLY_CSV = BACKEND_ROOT / "app" / "data" / "processed" / "climate_yearly_values.csv.gz"
OUTPUT_DIR = BACKEND_ROOT / "app" / "data" / "processed" / "district_timeseries"


def _write_json_gzip(path: Path, payload: dict) -> None:
    """Write reproducible gzip output so identical data has identical bytes."""
    with path.open("wb") as raw_handle:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw_handle, mtime=0) as gzip_handle:
            with io.TextIOWrapper(gzip_handle, encoding="utf-8") as text_handle:
                json.dump(payload, text_handle, separators=(",", ":"))


def build_district_timeseries(yearly_csv: Path, output_dir: Path) -> set[str]:
    """Build all per-district API payloads and return the generated district IDs."""
    if not yearly_csv.exists():
        raise FileNotFoundError(f"Missing input: {yearly_csv}")

    output_dir.mkdir(parents=True, exist_ok=True)

    # district_id -> variable -> scenario -> year -> {p10, p50, p90, district_name, unit}
    per_district: dict[str, dict[str, dict[str, dict[int, dict]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(dict))
    )
    district_names: dict[str, str] = {}

    print(f"Reading {yearly_csv}...")
    with gzip.open(yearly_csv, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for i, row in enumerate(reader):
            if i % 500_000 == 0:
                print(f"  processed {i:,} rows")
            district_id = row["district_id"]
            district_names[district_id] = row["district_name"]
            variable = row["variable"]
            scenario = row["scenario"].lower()
            percentile = row["percentile"].lower()
            if percentile not in {"p10", "p50", "p90"}:
                continue
            try:
                year = int(row["year"])
                value = float(row["value"])
            except (TypeError, ValueError):
                continue
            unit = row["unit"]
            point = per_district[district_id][variable][scenario].setdefault(
                year, {"year": year, "unit": unit}
            )
            point[percentile] = value

    print(f"Found {len(per_district)} districts. Writing output...")

    for district_id, variables in per_district.items():
        payload: dict = {
            "district_id": district_id,
            "district_name": district_names[district_id],
            "variables": {},
        }
        for variable, scenarios in variables.items():
            payload["variables"][variable] = {}
            for scenario, year_map in scenarios.items():
                points = []
                for year in sorted(year_map):
                    p = year_map[year]
                    if {"p10", "p50", "p90"}.issubset(p):
                        points.append(
                            {
                                "year": year,
                                "p10": p["p10"],
                                "p50": p["p50"],
                                "p90": p["p90"],
                                "unit": p["unit"],
                            }
                        )
                if points:
                    payload["variables"][variable][scenario] = points

        out_path = output_dir / f"{district_id}.json.gz"
        _write_json_gzip(out_path, payload)

    total_bytes = sum(p.stat().st_size for p in output_dir.glob("*.json.gz"))
    print(
        f"Wrote {len(per_district)} files to {output_dir} "
        f"({total_bytes / 1024 / 1024:.1f} MB total)"
    )
    return set(per_district)


def main() -> None:
    try:
        build_district_timeseries(YEARLY_CSV, OUTPUT_DIR)
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
