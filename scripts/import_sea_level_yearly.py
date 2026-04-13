"""One-off script: append yearly SLR rows to climate_yearly_values.csv and rebuild
the per-district timeseries JSONs.

Use this when you only need to refresh the sea-level yearly chart data without
re-running the full NetCDF importer (which requires the original CMIP6 source dirs).

    python scripts/import_sea_level_yearly.py
"""
from __future__ import annotations

import gzip
import shutil
from pathlib import Path

import geopandas as gpd
import pandas as pd

from import_real_climate_data import (
    SEA_LEVEL_YEARLY_FILE,
    process_sea_level_yearly_file,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = BACKEND_ROOT / "app" / "data" / "processed"
YEARLY_CSV = PROCESSED_DIR / "climate_yearly_values.csv"
YEARLY_CSV_GZ = PROCESSED_DIR / "climate_yearly_values.csv.gz"
DISTRICTS_GEOJSON = PROCESSED_DIR / "districts.geojson"
SEA_LEVEL_DIR = BACKEND_ROOT / "app" / "data" / "raw" / "sea_level" / "SeaLevel_Data"


def main() -> None:
    yearly_path = SEA_LEVEL_DIR / SEA_LEVEL_YEARLY_FILE
    if not yearly_path.exists():
        raise SystemExit(f"Missing input: {yearly_path}")
    if not DISTRICTS_GEOJSON.exists():
        raise SystemExit(f"Missing districts: {DISTRICTS_GEOJSON}")
    if not YEARLY_CSV.exists():
        raise SystemExit(f"Missing yearly CSV: {YEARLY_CSV}")

    print(f"Loading districts from {DISTRICTS_GEOJSON}...")
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
                import json as _json
                return _json.loads(value)
            return list(value)

        districts["centroid"] = districts["centroid"].apply(_coerce_centroid)
    districts = districts[["district_id", "district_name", "region", "geometry", "centroid"]]

    print(f"Processing yearly SLR file {yearly_path.name}...")
    new_rows = process_sea_level_yearly_file(yearly_path, districts)
    if not new_rows:
        raise SystemExit("Sea-level yearly processing produced no rows.")
    new_frame = pd.DataFrame(new_rows)
    print(f"  generated {len(new_frame):,} rows")

    print(f"Reading existing yearly CSV ({YEARLY_CSV.name})...")
    existing = pd.read_csv(YEARLY_CSV)
    print(f"  existing rows: {len(existing):,}")

    existing = existing[existing["variable"] != "sea_level_rise"]
    print(f"  after dropping any prior sea_level_rise rows: {len(existing):,}")

    for column in existing.columns:
        if column not in new_frame.columns:
            new_frame[column] = pd.NA
    new_frame = new_frame[existing.columns]

    combined = pd.concat([existing, new_frame], ignore_index=True)
    combined = combined.sort_values(
        ["variable", "scenario", "year", "percentile", "region", "district_name"]
    )
    print(f"  combined rows: {len(combined):,}")

    print(f"Writing {YEARLY_CSV.name}...")
    combined.to_csv(YEARLY_CSV, index=False)

    print(f"Writing {YEARLY_CSV_GZ.name}...")
    with YEARLY_CSV.open("rb") as src, gzip.open(YEARLY_CSV_GZ, "wb") as dst:
        shutil.copyfileobj(src, dst)

    print("Done. Now run: python scripts/precompute_district_timeseries.py")


if __name__ == "__main__":
    main()
