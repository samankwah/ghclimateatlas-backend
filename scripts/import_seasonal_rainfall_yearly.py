"""Refresh the MAM, JJA, and SON yearly rainfall chart datasets.

The command imports only the nine seasonal ``202`` NetCDF files under
``chart-source-data/rainfall``. It stages and validates the merged yearly CSV,
the import summary, and every per-district timeseries file before replacing
production artifacts.

Run from the backend repository:

    python scripts/import_seasonal_rainfall_yearly.py
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from import_real_climate_data import (
    PERCENTILE_MAPPING,
    SEASON_LENGTH_DAYS,
    SourceFile,
    build_grid_lookup,
    build_nearest_cell_lookup,
    load_districts,
    process_yearly_file,
)
from precompute_district_timeseries import build_district_timeseries


BACKEND_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = BACKEND_ROOT.parent
PROCESSED_DIR = BACKEND_ROOT / "app" / "data" / "processed"

DEFAULT_RAINFALL_DIR = WORKSPACE_ROOT / "chart-source-data" / "rainfall"
DEFAULT_DISTRICTS = PROCESSED_DIR / "districts.geojson"
DEFAULT_YEARLY_VALUES = PROCESSED_DIR / "climate_yearly_values.csv.gz"
DEFAULT_IMPORT_SUMMARY = PROCESSED_DIR / "import_summary.json"
DEFAULT_TIMESERIES_DIR = PROCESSED_DIR / "district_timeseries"

START_YEAR = 1950
HISTORICAL_END_YEAR = 2020
END_YEAR = 2100
EXPECTED_DISTRICT_COUNT = 259
EXPECTED_PERCENTILES = {10, 50, 90}
EXPECTED_SCENARIOS = ("rcp26", "rcp45", "rcp85")
SEASON_CONFIG = {
    "mam": {"directory": "MAM", "variable": "precipitation_mam", "days": 92},
    "jja": {"directory": "JJA", "variable": "precipitation_jja", "days": 92},
    "son": {"directory": "SON", "variable": "precipitation_sep_oct_nov", "days": 91},
}
TARGET_VARIABLES = frozenset(config["variable"] for config in SEASON_CONFIG.values())
CSV_COLUMNS = (
    "district_id",
    "district_name",
    "region",
    "value",
    "grid_point_count",
    "unit",
    "variable",
    "year",
    "scenario",
    "percentile",
)


@dataclass(frozen=True)
class ValidatedSource:
    source: SourceFile
    years: frozenset[int]


@dataclass
class HistoricalAccumulator:
    row: dict[str, object]
    values: list[float]
    scenarios: set[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh MAM, JJA, and SON yearly district rainfall chart data."
    )
    parser.add_argument("--rainfall-dir", type=Path, default=DEFAULT_RAINFALL_DIR)
    parser.add_argument("--districts", type=Path, default=DEFAULT_DISTRICTS)
    parser.add_argument("--yearly-file", type=Path, default=DEFAULT_YEARLY_VALUES)
    parser.add_argument("--summary-file", type=Path, default=DEFAULT_IMPORT_SUMMARY)
    parser.add_argument("--timeseries-dir", type=Path, default=DEFAULT_TIMESERIES_DIR)
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _guarded_dataset_hashes(processed_dir: Path) -> dict[Path, str]:
    guarded = (
        processed_dir / "climate_period_values.csv",
        processed_dir / "districts.geojson",
        processed_dir / "districts_map.geojson",
    )
    missing = [path for path in guarded if not path.exists()]
    if missing:
        raise ValueError(f"Missing guarded period/map dataset(s): {', '.join(map(str, missing))}")
    return {path: _sha256(path) for path in guarded}


def _assert_hashes_unchanged(expected: dict[Path, str]) -> None:
    changed = [path for path, digest in expected.items() if _sha256(path) != digest]
    if changed:
        raise RuntimeError(f"Period/map dataset changed during import: {', '.join(map(str, changed))}")


def _expected_source_path(rainfall_dir: Path, season: str, scenario: str) -> Path:
    directory = str(SEASON_CONFIG[season]["directory"])
    return rainfall_dir / directory / f"202-qdm_CORDEX_Ghana0p0375_{scenario}_ensstats.nc"


def _years_from_time(data: xr.DataArray, path: Path) -> list[int]:
    try:
        years = pd.DatetimeIndex(data.values).year.tolist()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Could not decode yearly time values in {path}") from exc
    return [int(year) for year in years]


def validate_sources(rainfall_dir: Path) -> list[ValidatedSource]:
    expected_years = set(range(START_YEAR, END_YEAR + 1))
    validated: list[ValidatedSource] = []
    reference_latitudes: np.ndarray | None = None
    reference_longitudes: np.ndarray | None = None

    expected_paths = [
        _expected_source_path(rainfall_dir, season, scenario)
        for season in SEASON_CONFIG
        for scenario in EXPECTED_SCENARIOS
    ]
    missing = [path for path in expected_paths if not path.is_file()]
    if missing:
        raise ValueError(f"Missing required 202 input(s): {', '.join(map(str, missing))}")

    for season, config in SEASON_CONFIG.items():
        if SEASON_LENGTH_DAYS.get(season) != config["days"]:
            raise ValueError(
                f"Configured {season.upper()} duration does not match the shared conversion logic"
            )
        for scenario in EXPECTED_SCENARIOS:
            path = _expected_source_path(rainfall_dir, season, scenario)
            with xr.open_dataset(path) as dataset:
                required_names = {"indicator", "time", "lat", "lon", "percentiles"}
                absent = sorted(required_names.difference(dataset.variables))
                if absent:
                    raise ValueError(f"{path} is missing required variables: {absent}")

                indicator = dataset["indicator"]
                expected_dims = ("time", "lat", "lon", "percentiles")
                if indicator.dims != expected_dims:
                    raise ValueError(
                        f"Unexpected indicator dimensions in {path}: {indicator.dims}; "
                        f"expected {expected_dims}"
                    )
                attrs = indicator.attrs
                expected_attrs = {
                    "id": "202-qdm",
                    "season": season,
                    "time_binning": "years",
                    "units": "mm/s",
                }
                for name, expected in expected_attrs.items():
                    actual = str(attrs.get(name, "")).strip().lower()
                    if actual != expected:
                        raise ValueError(
                            f"Unexpected indicator {name} in {path}: {actual!r}; expected {expected!r}"
                        )

                percentiles = [int(value) for value in dataset["percentiles"].values.tolist()]
                if len(percentiles) != 3 or set(percentiles) != EXPECTED_PERCENTILES:
                    raise ValueError(
                        f"Unexpected percentiles in {path}: {percentiles}; expected 10, 50, and 90"
                    )

                years = _years_from_time(dataset["time"], path)
                if len(years) != len(set(years)):
                    raise ValueError(f"Duplicate yearly time values in {path}")
                missing_years = sorted(expected_years.difference(years))
                if missing_years:
                    raise ValueError(f"{path} does not cover required years: {missing_years}")

                latitudes = np.asarray(dataset["lat"].values)
                longitudes = np.asarray(dataset["lon"].values)
                if latitudes.ndim != 1 or longitudes.ndim != 1:
                    raise ValueError(f"Latitude and longitude must be one-dimensional in {path}")
                if len(latitudes) < 2 or len(longitudes) < 2:
                    raise ValueError(f"Latitude/longitude grids are empty in {path}")
                if not np.all(np.diff(latitudes) > 0) or not np.all(np.diff(longitudes) > 0):
                    raise ValueError(f"Latitude/longitude grids must be strictly increasing in {path}")
                if reference_latitudes is None:
                    reference_latitudes = latitudes.copy()
                    reference_longitudes = longitudes.copy()
                elif not (
                    np.array_equal(latitudes, reference_latitudes)
                    and np.array_equal(longitudes, reference_longitudes)
                ):
                    raise ValueError(f"Grid coordinates in {path} do not match the other inputs")

            validated.append(
                ValidatedSource(
                    source=SourceFile(
                        path=path,
                        indicator_id="202",
                        scenario=scenario,
                        season=season,
                        variable=str(config["variable"]),
                        kind="years",
                    ),
                    years=frozenset(years),
                )
            )

    if len(validated) != 9:
        raise AssertionError(f"Expected nine validated sources, found {len(validated)}")
    return validated


def _projection_key(row: dict[str, object]) -> tuple[str, str, str, int, str]:
    return (
        str(row["variable"]),
        str(row["district_id"]),
        str(row["scenario"]),
        int(row["year"]),
        str(row["percentile"]),
    )


def _historical_key(row: dict[str, object]) -> tuple[str, str, int, str]:
    return (
        str(row["variable"]),
        str(row["district_id"]),
        int(row["year"]),
        str(row["percentile"]),
    )


def _validate_row(row: dict[str, object], district_ids: set[str]) -> None:
    if str(row["district_id"]) not in district_ids:
        raise ValueError(f"Unexpected district in aggregated row: {row['district_id']}")
    if str(row["variable"]) not in TARGET_VARIABLES:
        raise ValueError(f"Unexpected variable in aggregated row: {row['variable']}")
    if str(row["percentile"]) not in set(PERCENTILE_MAPPING.values()):
        raise ValueError(f"Unexpected percentile in aggregated row: {row['percentile']}")
    if str(row["unit"]) != "mm":
        raise ValueError(f"Seasonal rainfall row has unexpected unit: {row['unit']}")
    if not math.isfinite(float(row["value"])):
        raise ValueError("Seasonal rainfall aggregation produced a non-finite value")


def build_target_rows(
    sources: list[ValidatedSource],
    districts,
    target_csv: Path,
) -> int:
    district_ids = set(districts["district_id"].astype(str))
    sample_path = sources[0].source.path
    with xr.open_dataset(sample_path) as sample:
        grid_lookup = build_grid_lookup(sample["lat"].values, sample["lon"].values, districts)
        nearest_lookup = build_nearest_cell_lookup(
            sample["lat"].values,
            sample["lon"].values,
            districts,
        )

    historical: dict[tuple[str, str, int, str], HistoricalAccumulator] = {}
    projection_count = 0
    expected_projection_per_source = (
        (END_YEAR - HISTORICAL_END_YEAR)
        * len(EXPECTED_PERCENTILES)
        * len(district_ids)
    )

    with target_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()

        for index, validated in enumerate(sources, start=1):
            source = validated.source
            print(f"[{index}/9] Aggregating {source.path.name} ({source.season.upper()})...")
            rows = process_yearly_file(source, districts, grid_lookup, nearest_lookup)
            source_projection_keys: set[tuple[str, str, str, int, str]] = set()

            for row in rows:
                year = int(row["year"])
                if year < START_YEAR or year > END_YEAR:
                    continue
                _validate_row(row, district_ids)

                if year <= HISTORICAL_END_YEAR:
                    key = _historical_key(row)
                    accumulator = historical.get(key)
                    if accumulator is None:
                        historical[key] = HistoricalAccumulator(
                            row={**row, "scenario": "historical"},
                            values=[float(row["value"])],
                            scenarios={source.scenario},
                        )
                        continue
                    if source.scenario in accumulator.scenarios:
                        raise ValueError(f"Duplicate historical contribution for {key} from {source.scenario}")
                    for field in ("district_name", "region", "unit", "grid_point_count"):
                        if accumulator.row[field] != row[field]:
                            raise ValueError(f"Historical metadata mismatch for {key}: {field}")
                    accumulator.values.append(float(row["value"]))
                    accumulator.scenarios.add(source.scenario)
                    continue

                key = _projection_key(row)
                if key in source_projection_keys:
                    raise ValueError(f"Duplicate projection row: {key}")
                source_projection_keys.add(key)
                writer.writerow({column: row[column] for column in CSV_COLUMNS})

            if len(source_projection_keys) != expected_projection_per_source:
                raise ValueError(
                    f"Incomplete projection rows for {source.path}: "
                    f"found {len(source_projection_keys):,}, expected {expected_projection_per_source:,}"
                )
            projection_count += len(source_projection_keys)

        expected_historical_count = (
            len(TARGET_VARIABLES)
            * (HISTORICAL_END_YEAR - START_YEAR + 1)
            * len(EXPECTED_PERCENTILES)
            * len(district_ids)
        )
        if len(historical) != expected_historical_count:
            raise ValueError(
                f"Incomplete historical rows: found {len(historical):,}, "
                f"expected {expected_historical_count:,}"
            )

        for key in sorted(historical):
            accumulator = historical[key]
            if accumulator.scenarios != set(EXPECTED_SCENARIOS) or len(accumulator.values) != 3:
                raise ValueError(f"Historical row does not contain all three RCP histories: {key}")
            averaged = dict(accumulator.row)
            averaged["value"] = math.fsum(accumulator.values) / len(accumulator.values)
            writer.writerow({column: averaged[column] for column in CSV_COLUMNS})

    return projection_count + len(historical)


def _open_reproducible_gzip_text(path: Path):
    raw_handle = path.open("wb")
    gzip_handle = gzip.GzipFile(filename="", mode="wb", fileobj=raw_handle, mtime=0)
    text_handle = io.TextIOWrapper(gzip_handle, encoding="utf-8", newline="")
    return raw_handle, gzip_handle, text_handle


def merge_yearly_values(existing_path: Path, target_csv: Path, output_path: Path) -> tuple[int, int]:
    if not existing_path.is_file():
        raise ValueError(f"Missing tracked yearly dataset: {existing_path}")

    retained_count = 0
    replaced_count = 0
    raw_handle, gzip_handle, text_handle = _open_reproducible_gzip_text(output_path)
    try:
        writer = csv.DictWriter(text_handle, fieldnames=CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        with gzip.open(existing_path, "rt", encoding="utf-8", newline="") as existing_handle:
            reader = csv.DictReader(existing_handle)
            if tuple(reader.fieldnames or ()) != CSV_COLUMNS:
                raise ValueError(
                    f"Unexpected yearly CSV columns: {reader.fieldnames}; expected {list(CSV_COLUMNS)}"
                )
            for row in reader:
                if row["variable"] in TARGET_VARIABLES:
                    replaced_count += 1
                    continue
                writer.writerow(row)
                retained_count += 1

        with target_csv.open("r", encoding="utf-8", newline="") as target_handle:
            reader = csv.DictReader(target_handle)
            if tuple(reader.fieldnames or ()) != CSV_COLUMNS:
                raise ValueError("Generated seasonal CSV has unexpected columns")
            for row in reader:
                writer.writerow(row)
    finally:
        text_handle.close()
        if not gzip_handle.closed:
            gzip_handle.close()
        if not raw_handle.closed:
            raw_handle.close()
    return retained_count, replaced_count


def validate_merged_yearly(
    path: Path,
    expected_total: int,
    expected_target_count: int,
    district_ids: set[str],
) -> None:
    total = 0
    target_count = 0
    target_keys: set[tuple[str, str, str, int, str]] = set()
    expected_scenarios = {"historical", *EXPECTED_SCENARIOS}
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != CSV_COLUMNS:
            raise ValueError("Merged yearly CSV has unexpected columns")
        for row in reader:
            total += 1
            if row["variable"] not in TARGET_VARIABLES:
                continue
            target_count += 1
            year = int(row["year"])
            scenario = row["scenario"]
            if not START_YEAR <= year <= END_YEAR:
                raise ValueError(f"Seasonal chart year outside 1950-2100: {year}")
            if scenario not in expected_scenarios:
                raise ValueError(f"Unexpected seasonal chart scenario: {scenario}")
            if (year <= HISTORICAL_END_YEAR) != (scenario == "historical"):
                raise ValueError(f"Seasonal chart history/projection boundary mismatch: {row}")
            key = _projection_key(row)
            if key in target_keys:
                raise ValueError(f"Duplicate seasonal row in merged yearly CSV: {key}")
            target_keys.add(key)
            _validate_row(row, district_ids)

    if total != expected_total:
        raise ValueError(f"Merged yearly row count is {total:,}; expected {expected_total:,}")
    if target_count != expected_target_count:
        raise ValueError(
            f"Merged seasonal row count is {target_count:,}; expected {expected_target_count:,}"
        )


def write_summary(source_path: Path, output_path: Path, yearly_rows: int) -> None:
    if not source_path.is_file():
        raise ValueError(f"Missing import summary: {source_path}")
    summary = json.loads(source_path.read_text(encoding="utf-8"))
    summary["yearly_rows"] = yearly_rows
    output_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def validate_timeseries(
    directory: Path,
    district_ids: set[str],
) -> None:
    paths = sorted(directory.glob("*.json.gz"))
    generated_ids = {path.name.removesuffix(".json.gz") for path in paths}
    if generated_ids != district_ids:
        missing = sorted(district_ids - generated_ids)
        extra = sorted(generated_ids - district_ids)
        raise ValueError(f"Timeseries district mismatch; missing={missing}, extra={extra}")

    expected_history_years = set(range(START_YEAR, HISTORICAL_END_YEAR + 1))
    expected_projection_years = set(range(HISTORICAL_END_YEAR + 1, END_YEAR + 1))
    for path in paths:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
        variables = payload.get("variables", {})
        for variable in TARGET_VARIABLES:
            block = variables.get(variable)
            if not isinstance(block, dict):
                raise ValueError(f"{path.name} is missing {variable}")
            for scenario in ("historical", *EXPECTED_SCENARIOS):
                points = block.get(scenario)
                if not isinstance(points, list):
                    raise ValueError(f"{path.name} is missing {variable}/{scenario}")
                years = {int(point["year"]) for point in points}
                expected_years = (
                    expected_history_years if scenario == "historical" else expected_projection_years
                )
                if years != expected_years or len(points) != len(expected_years):
                    raise ValueError(f"{path.name} has incomplete {variable}/{scenario} coverage")
                for point in points:
                    if not {"p10", "p50", "p90"}.issubset(point):
                        raise ValueError(f"{path.name} has incomplete percentile data")
                    if point.get("unit") != "mm":
                        raise ValueError(f"{path.name} has an unexpected seasonal rainfall unit")
                    values = [float(point[name]) for name in ("p10", "p50", "p90")]
                    if not all(math.isfinite(value) for value in values):
                        raise ValueError(f"{path.name} has non-finite seasonal rainfall values")
                    if not values[0] <= values[1] <= values[2]:
                        raise ValueError(f"{path.name} has unordered seasonal rainfall percentiles")


def _replace_staged_files(staged_directory: Path, output_directory: Path) -> None:
    staged_paths = sorted(staged_directory.glob("*.json.gz"))
    existing_names = {path.name for path in output_directory.glob("*.json.gz")}
    staged_names = {path.name for path in staged_paths}
    if existing_names != staged_names:
        raise ValueError("Refusing to replace a different set of per-district timeseries files")
    for staged_path in staged_paths:
        os.replace(staged_path, output_directory / staged_path.name)


def _reset_windows_acl_inheritance(files: tuple[Path, ...], directories: tuple[Path, ...]) -> None:
    """Ensure atomically moved staging files inherit their production ACLs on Windows."""
    if os.name != "nt":
        return

    for path in files:
        subprocess.run(
            ["icacls", str(path), "/reset", "/C", "/Q"],
            check=True,
            capture_output=True,
            text=True,
        )
    for path in directories:
        subprocess.run(
            ["icacls", str(path), "/reset", "/T", "/C", "/Q"],
            check=True,
            capture_output=True,
            text=True,
        )


def main() -> None:
    args = parse_args()
    guarded_hashes = _guarded_dataset_hashes(args.yearly_file.parent)
    sources = validate_sources(args.rainfall_dir)
    print("Validated all nine seasonal rainfall inputs.")

    districts = load_districts(args.districts)
    district_ids = set(districts["district_id"].astype(str))
    if len(district_ids) != EXPECTED_DISTRICT_COUNT or len(districts) != EXPECTED_DISTRICT_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_DISTRICT_COUNT} unique districts, found {len(district_ids)}"
        )

    with tempfile.TemporaryDirectory(prefix="seasonal-rainfall-", dir=args.yearly_file.parent) as temp:
        staging_root = Path(temp)
        target_csv = staging_root / "seasonal_yearly.csv"
        staged_yearly = staging_root / args.yearly_file.name
        staged_summary = staging_root / args.summary_file.name
        staged_timeseries = staging_root / "district_timeseries"

        target_count = build_target_rows(sources, districts, target_csv)
        expected_target_count = (
            len(TARGET_VARIABLES)
            * len(EXPECTED_PERCENTILES)
            * len(district_ids)
            * (
                (HISTORICAL_END_YEAR - START_YEAR + 1)
                + len(EXPECTED_SCENARIOS) * (END_YEAR - HISTORICAL_END_YEAR)
            )
        )
        if target_count != expected_target_count:
            raise ValueError(
                f"Generated {target_count:,} seasonal rows; expected {expected_target_count:,}"
            )

        retained_count, replaced_count = merge_yearly_values(
            args.yearly_file,
            target_csv,
            staged_yearly,
        )
        total_count = retained_count + target_count
        validate_merged_yearly(staged_yearly, total_count, target_count, district_ids)
        write_summary(args.summary_file, staged_summary, total_count)

        generated_ids = build_district_timeseries(staged_yearly, staged_timeseries)
        if generated_ids != district_ids:
            raise ValueError("District timeseries generation did not include all districts")
        validate_timeseries(staged_timeseries, district_ids)
        _assert_hashes_unchanged(guarded_hashes)

        _replace_staged_files(staged_timeseries, args.timeseries_dir)
        os.replace(staged_yearly, args.yearly_file)
        os.replace(staged_summary, args.summary_file)
        _reset_windows_acl_inheritance(
            (args.yearly_file, args.summary_file),
            (args.timeseries_dir,),
        )

    _assert_hashes_unchanged(guarded_hashes)
    print(
        f"Imported {target_count:,} seasonal rows, replaced {replaced_count:,} prior rows, "
        f"and rebuilt {len(district_ids)} district timeseries files."
    )
    print(f"Yearly dataset now contains {total_count:,} rows.")


if __name__ == "__main__":
    main()
