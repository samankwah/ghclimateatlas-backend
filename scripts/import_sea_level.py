"""Refresh only the sea-level rows in the processed climate data.

Replaces every `sea_level_rise` row in climate_period_values.csv and
climate_yearly_values.csv.gz with fresh aggregates for the coastal districts in
app/data/processed/coastal_districts.json, leaving temperature and rainfall rows
untouched. Use this instead of the full importer (which rewrites both CSVs from
scratch and needs the original CMIP6 source dirs).

    python scripts/extract_coastline.py      # if district boundaries changed
    python scripts/import_sea_level.py --sea-level-dir <dir with SLRprojections*.nc>
    python scripts/precompute_district_timeseries.py
"""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

from import_real_climate_data import (
    SEA_LEVEL_PERIOD_FILE,
    SEA_LEVEL_YEARLY_FILE,
    load_coastal_district_ids,
    process_sea_level_file,
    process_sea_level_yearly_file,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = BACKEND_ROOT / "app" / "data" / "processed"
PERIOD_CSV = PROCESSED_DIR / "climate_period_values.csv"
YEARLY_CSV_GZ = PROCESSED_DIR / "climate_yearly_values.csv.gz"
DISTRICTS_GEOJSON = PROCESSED_DIR / "districts.geojson"
DEFAULT_SEA_LEVEL_DIR = BACKEND_ROOT / "app" / "data" / "raw" / "sea_level" / "SeaLevel_Data"

PERIOD_SORT = ["variable", "scenario", "period", "percentile", "region", "district_name"]
YEARLY_SORT = ["variable", "scenario", "year", "percentile", "region", "district_name"]


def load_districts() -> gpd.GeoDataFrame:
    districts = gpd.read_file(DISTRICTS_GEOJSON)
    if districts.crs is None:
        districts = districts.set_crs("EPSG:4326")
    else:
        districts = districts.to_crs("EPSG:4326")
    districts = districts.rename(columns={"id": "district_id", "name": "district_name"})
    if "centroid" not in districts.columns:
        districts["centroid"] = districts.geometry.representative_point().apply(
            lambda geom: [geom.x, geom.y]
        )
    else:
        def _coerce_centroid(value):
            if isinstance(value, list):
                return value
            if isinstance(value, str):
                return json.loads(value)
            return list(value)

        districts["centroid"] = districts["centroid"].apply(_coerce_centroid)
    return districts[["district_id", "district_name", "region", "geometry", "centroid"]]


def splice_sea_level_rows(lines: list[str], new_rows: list[dict], sort_columns: list[str]) -> list[str]:
    """Replace the sea-level lines of a CSV, copying every other line verbatim.

    Working on text rather than a DataFrame keeps the other rows byte-identical
    (the file mixes number formats from earlier imports, e.g. `81` and `81.0`),
    so the diff only shows sea-level changes.
    """
    header_text = lines[0].rstrip("\r\n")
    header = header_text.split(",")
    newline = lines[0][len(header_text):] or "\n"

    new_frame = pd.DataFrame(new_rows)
    for column in header:
        if column not in new_frame.columns:
            new_frame[column] = pd.NA
    new_frame = new_frame[header].sort_values(sort_columns, kind="stable")
    new_lines = new_frame.to_csv(index=False, header=False, lineterminator=newline).splitlines(keepends=True)

    is_sea_level = [",sea_level_rise," in line for line in lines]
    insert_at = is_sea_level.index(True) if any(is_sea_level) else len(lines)
    print(f"  replacing {sum(is_sea_level):,} sea_level_rise rows with {len(new_lines):,}")
    before = [line for line, sea in zip(lines[:insert_at], is_sea_level[:insert_at]) if not sea]
    after = [line for line, sea in zip(lines[insert_at:], is_sea_level[insert_at:]) if not sea]
    return before + new_lines + after


def check_coverage(rows: list[dict], label: str) -> None:
    covered = {row["district_id"] for row in rows if row["scenario"] != "historical"}
    missing = load_coastal_district_ids() - covered
    if missing:
        raise SystemExit(f"{label}: no projections for coastal districts {sorted(missing)}")
    print(f"  {label}: projections for all {len(covered)} coastal districts")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sea-level-dir", type=Path, default=DEFAULT_SEA_LEVEL_DIR)
    args = parser.parse_args()

    period_path = args.sea_level_dir / SEA_LEVEL_PERIOD_FILE
    yearly_path = args.sea_level_dir / SEA_LEVEL_YEARLY_FILE
    for path in (period_path, yearly_path, DISTRICTS_GEOJSON, PERIOD_CSV, YEARLY_CSV_GZ):
        if not path.exists():
            raise SystemExit(f"Missing input: {path}")

    print(f"Loading districts from {DISTRICTS_GEOJSON}...")
    districts = load_districts()

    # Aggregate both files before writing anything, so a failure leaves the CSVs intact.
    print(f"Processing {period_path.name}...")
    period_rows = process_sea_level_file(period_path, districts)
    check_coverage(period_rows, period_path.name)
    print(f"Processing {yearly_path.name}...")
    yearly_rows = process_sea_level_yearly_file(yearly_path, districts)
    check_coverage(yearly_rows, yearly_path.name)

    print(f"Updating {PERIOD_CSV.name}...")
    with PERIOD_CSV.open("r", encoding="utf-8", newline="") as handle:
        period_lines = splice_sea_level_rows(handle.readlines(), period_rows, PERIOD_SORT)
    with PERIOD_CSV.open("w", encoding="utf-8", newline="") as handle:
        handle.writelines(period_lines)

    print(f"Updating {YEARLY_CSV_GZ.name}...")
    with gzip.open(YEARLY_CSV_GZ, "rt", encoding="utf-8", newline="") as handle:
        yearly_lines = splice_sea_level_rows(handle.readlines(), yearly_rows, YEARLY_SORT)
    with gzip.open(YEARLY_CSV_GZ, "wt", encoding="utf-8", newline="") as handle:
        handle.writelines(yearly_lines)

    print("Done. Now run: python scripts/precompute_district_timeseries.py")


if __name__ == "__main__":
    main()
