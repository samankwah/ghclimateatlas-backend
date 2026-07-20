"""Refresh MAM and JJA period maps and yearly temperature chart datasets.

The command imports the twelve seasonal ``101``/``102`` NetCDF files under
``chart-source-data/temperature``. It stages and validates the period CSV,
yearly CSV, import summary, and all per-district timeseries files before
replacing production artifacts.

Run from the backend repository:

    python scripts/import_seasonal_temperature.py
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
    SourceFile,
    build_grid_lookup,
    build_nearest_cell_lookup,
    load_districts,
    process_period_file,
    process_yearly_file,
)
from precompute_district_timeseries import build_district_timeseries


BACKEND_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = BACKEND_ROOT.parent
PROCESSED_DIR = BACKEND_ROOT / "app" / "data" / "processed"

DEFAULT_TEMPERATURE_DIR = WORKSPACE_ROOT / "chart-source-data" / "temperature"
DEFAULT_DISTRICTS = PROCESSED_DIR / "districts.geojson"
DEFAULT_PERIOD_VALUES = PROCESSED_DIR / "climate_period_values.csv"
DEFAULT_YEARLY_VALUES = PROCESSED_DIR / "climate_yearly_values.csv.gz"
DEFAULT_IMPORT_SUMMARY = PROCESSED_DIR / "import_summary.json"
DEFAULT_TIMESERIES_DIR = PROCESSED_DIR / "district_timeseries"

START_YEAR = 1950
HISTORICAL_END_YEAR = 2020
END_YEAR = 2100
EXPECTED_DISTRICT_COUNT = 259
EXPECTED_PERCENTILES = {10, 50, 90}
EXPECTED_SCENARIOS = ("rcp26", "rcp45", "rcp85")
PERIOD_MAPPING = {"1": "baseline", "2": "2030", "3": "2050", "4": "2080"}
FUTURE_PERIODS = ("2030", "2050", "2080")
SEASON_CONFIG = {
    "mam": {"directory": "MAM", "variable": "mean_temp_mam"},
    "jja": {"directory": "JJA", "variable": "mean_temp_jja"},
}
TARGET_VARIABLES = frozenset(config["variable"] for config in SEASON_CONFIG.values())
PERIOD_COLUMNS = (
    "district_id",
    "district_name",
    "region",
    "value",
    "grid_point_count",
    "unit",
    "variable",
    "period",
    "scenario",
    "percentile",
)
YEARLY_COLUMNS = (
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


@dataclass
class HistoricalAccumulator:
    row: dict[str, object]
    values: list[float]
    scenarios: set[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh MAM and JJA district temperature maps and charts."
    )
    parser.add_argument("--temperature-dir", type=Path, default=DEFAULT_TEMPERATURE_DIR)
    parser.add_argument("--districts", type=Path, default=DEFAULT_DISTRICTS)
    parser.add_argument("--period-file", type=Path, default=DEFAULT_PERIOD_VALUES)
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


def _guarded_map_hashes(processed_dir: Path) -> dict[Path, str]:
    guarded = (
        processed_dir / "districts.geojson",
        processed_dir / "districts_map.geojson",
    )
    missing = [path for path in guarded if not path.exists()]
    if missing:
        raise ValueError(f"Missing guarded map dataset(s): {', '.join(map(str, missing))}")
    return {path: _sha256(path) for path in guarded}


def _assert_hashes_unchanged(expected: dict[Path, str]) -> None:
    changed = [path for path, digest in expected.items() if _sha256(path) != digest]
    if changed:
        raise RuntimeError(f"Map dataset changed during import: {', '.join(map(str, changed))}")


def _source_path(
    temperature_dir: Path,
    season: str,
    indicator_id: str,
    scenario: str,
) -> Path:
    directory = str(SEASON_CONFIG[season]["directory"])
    return (
        temperature_dir
        / directory
        / f"{indicator_id}-qdm_CORDEX_Ghana0p0375_{scenario}_ensstats.nc"
    )


def _years_from_time(data: xr.DataArray, path: Path) -> list[int]:
    try:
        years = pd.DatetimeIndex(data.values).year.tolist()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Could not decode yearly time values in {path}") from exc
    return [int(year) for year in years]


def validate_sources(temperature_dir: Path) -> list[ValidatedSource]:
    expected_years = set(range(START_YEAR, END_YEAR + 1))
    validated: list[ValidatedSource] = []
    reference_latitudes: np.ndarray | None = None
    reference_longitudes: np.ndarray | None = None

    expected_paths = [
        _source_path(temperature_dir, season, indicator_id, scenario)
        for season in SEASON_CONFIG
        for indicator_id in ("101", "102")
        for scenario in EXPECTED_SCENARIOS
    ]
    missing = [path for path in expected_paths if not path.is_file()]
    if missing:
        raise ValueError(f"Missing required temperature input(s): {', '.join(map(str, missing))}")

    for season, config in SEASON_CONFIG.items():
        for indicator_id, kind in (("101", "periods"), ("102", "years")):
            for scenario in EXPECTED_SCENARIOS:
                path = _source_path(temperature_dir, season, indicator_id, scenario)
                with xr.open_dataset(path) as dataset:
                    coordinate_name = "periodID" if kind == "periods" else "time"
                    required_names = {
                        "indicator",
                        coordinate_name,
                        "lat",
                        "lon",
                        "percentiles",
                    }
                    absent = sorted(required_names.difference(dataset.variables))
                    if absent:
                        raise ValueError(f"{path} is missing required variables: {absent}")

                    indicator = dataset["indicator"]
                    expected_dims = (
                        ("periodID", "lat", "lon", "percentiles")
                        if kind == "periods"
                        else ("time", "lat", "lon", "percentiles")
                    )
                    if indicator.dims != expected_dims:
                        raise ValueError(
                            f"Unexpected indicator dimensions in {path}: {indicator.dims}; "
                            f"expected {expected_dims}"
                        )

                    expected_attrs = {
                        "id": f"{indicator_id}-qdm",
                        "season": season,
                        "statistic": "mean",
                        "time_binning": kind,
                        "units": "k",
                    }
                    for name, expected in expected_attrs.items():
                        actual = str(indicator.attrs.get(name, "")).strip().lower()
                        if actual != expected:
                            raise ValueError(
                                f"Unexpected indicator {name} in {path}: {actual!r}; "
                                f"expected {expected!r}"
                            )

                    percentiles = [int(value) for value in dataset["percentiles"].values.tolist()]
                    if len(percentiles) != 3 or set(percentiles) != EXPECTED_PERCENTILES:
                        raise ValueError(
                            f"Unexpected percentiles in {path}: {percentiles}; expected 10, 50, and 90"
                        )

                    if kind == "periods":
                        period_ids = {str(value) for value in dataset["periodID"].values.tolist()}
                        if period_ids != set(PERIOD_MAPPING):
                            raise ValueError(
                                f"Unexpected period IDs in {path}: {sorted(period_ids)}"
                            )
                    else:
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
                            indicator_id=indicator_id,
                            scenario=scenario,
                            season=season,
                            variable=str(config["variable"]),
                            kind=kind,
                        )
                    )
                )

    if len(validated) != 12:
        raise AssertionError(f"Expected twelve validated sources, found {len(validated)}")
    return validated


def _validate_temperature_row(row: dict[str, object], district_ids: set[str]) -> None:
    if str(row["district_id"]) not in district_ids:
        raise ValueError(f"Unexpected district in aggregated row: {row['district_id']}")
    if str(row["variable"]) not in TARGET_VARIABLES:
        raise ValueError(f"Unexpected variable in aggregated row: {row['variable']}")
    if str(row["percentile"]) not in set(PERCENTILE_MAPPING.values()):
        raise ValueError(f"Unexpected percentile in aggregated row: {row['percentile']}")
    if str(row["unit"]) != "°C":
        raise ValueError(f"Seasonal temperature row has unexpected unit: {row['unit']}")
    if not math.isfinite(float(row["value"])):
        raise ValueError("Seasonal temperature aggregation produced a non-finite value")


def _append_historical(
    accumulators: dict[tuple[object, ...], HistoricalAccumulator],
    key: tuple[object, ...],
    row: dict[str, object],
    source_scenario: str,
) -> None:
    accumulator = accumulators.get(key)
    if accumulator is None:
        accumulators[key] = HistoricalAccumulator(
            row={**row, "scenario": "historical"},
            values=[float(row["value"])],
            scenarios={source_scenario},
        )
        return
    if source_scenario in accumulator.scenarios:
        raise ValueError(f"Duplicate historical contribution for {key} from {source_scenario}")
    for field in ("district_name", "region", "unit", "grid_point_count"):
        if accumulator.row[field] != row[field]:
            raise ValueError(f"Historical metadata mismatch for {key}: {field}")
    accumulator.values.append(float(row["value"]))
    accumulator.scenarios.add(source_scenario)


def _write_averaged_historical(
    writer: csv.DictWriter,
    columns: tuple[str, ...],
    accumulators: dict[tuple[object, ...], HistoricalAccumulator],
) -> None:
    for key in sorted(accumulators):
        accumulator = accumulators[key]
        if accumulator.scenarios != set(EXPECTED_SCENARIOS) or len(accumulator.values) != 3:
            raise ValueError(f"Historical row does not contain all three RCP histories: {key}")
        averaged = dict(accumulator.row)
        averaged["value"] = math.fsum(accumulator.values) / len(accumulator.values)
        writer.writerow({column: averaged[column] for column in columns})


def build_period_rows(
    sources: list[ValidatedSource],
    districts,
    grid_lookup: dict[str, np.ndarray],
    nearest_lookup: dict[str, tuple[int, int]],
    target_csv: Path,
) -> int:
    district_ids = set(districts["district_id"].astype(str))
    period_sources = [item.source for item in sources if item.source.kind == "periods"]
    historical: dict[tuple[object, ...], HistoricalAccumulator] = {}
    projection_count = 0
    expected_projection_per_source = (
        len(FUTURE_PERIODS) * len(EXPECTED_PERCENTILES) * len(district_ids)
    )

    with target_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PERIOD_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for index, source in enumerate(period_sources, start=1):
            print(f"[period {index}/6] Aggregating {source.path.name} ({source.season.upper()})...")
            rows = process_period_file(
                source,
                districts,
                grid_lookup,
                nearest_lookup,
                PERIOD_MAPPING,
            )
            projection_keys: set[tuple[object, ...]] = set()
            for row in rows:
                _validate_temperature_row(row, district_ids)
                if row["period"] == "baseline":
                    key = (
                        row["variable"],
                        row["district_id"],
                        row["period"],
                        row["percentile"],
                    )
                    _append_historical(historical, key, row, source.scenario)
                    continue

                key = (
                    row["variable"],
                    row["district_id"],
                    row["period"],
                    row["scenario"],
                    row["percentile"],
                )
                if key in projection_keys:
                    raise ValueError(f"Duplicate period projection row: {key}")
                projection_keys.add(key)
                writer.writerow({column: row[column] for column in PERIOD_COLUMNS})

            if len(projection_keys) != expected_projection_per_source:
                raise ValueError(
                    f"Incomplete period projection rows for {source.path}: "
                    f"found {len(projection_keys):,}, expected {expected_projection_per_source:,}"
                )
            projection_count += len(projection_keys)

        expected_historical = (
            len(TARGET_VARIABLES) * len(EXPECTED_PERCENTILES) * len(district_ids)
        )
        if len(historical) != expected_historical:
            raise ValueError(
                f"Incomplete historical period rows: found {len(historical):,}, "
                f"expected {expected_historical:,}"
            )
        _write_averaged_historical(writer, PERIOD_COLUMNS, historical)

    return projection_count + len(historical)


def build_yearly_rows(
    sources: list[ValidatedSource],
    districts,
    grid_lookup: dict[str, np.ndarray],
    nearest_lookup: dict[str, tuple[int, int]],
    target_csv: Path,
) -> int:
    district_ids = set(districts["district_id"].astype(str))
    yearly_sources = [item.source for item in sources if item.source.kind == "years"]
    historical: dict[tuple[object, ...], HistoricalAccumulator] = {}
    projection_count = 0
    expected_projection_per_source = (
        (END_YEAR - HISTORICAL_END_YEAR)
        * len(EXPECTED_PERCENTILES)
        * len(district_ids)
    )

    with target_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=YEARLY_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for index, source in enumerate(yearly_sources, start=1):
            print(f"[yearly {index}/6] Aggregating {source.path.name} ({source.season.upper()})...")
            rows = process_yearly_file(source, districts, grid_lookup, nearest_lookup)
            projection_keys: set[tuple[object, ...]] = set()
            for row in rows:
                year = int(row["year"])
                if year < START_YEAR or year > END_YEAR:
                    continue
                _validate_temperature_row(row, district_ids)
                if year <= HISTORICAL_END_YEAR:
                    key = (
                        row["variable"],
                        row["district_id"],
                        year,
                        row["percentile"],
                    )
                    _append_historical(historical, key, row, source.scenario)
                    continue

                key = (
                    row["variable"],
                    row["district_id"],
                    row["scenario"],
                    year,
                    row["percentile"],
                )
                if key in projection_keys:
                    raise ValueError(f"Duplicate yearly projection row: {key}")
                projection_keys.add(key)
                writer.writerow({column: row[column] for column in YEARLY_COLUMNS})

            if len(projection_keys) != expected_projection_per_source:
                raise ValueError(
                    f"Incomplete yearly projection rows for {source.path}: "
                    f"found {len(projection_keys):,}, expected {expected_projection_per_source:,}"
                )
            projection_count += len(projection_keys)

        expected_historical = (
            len(TARGET_VARIABLES)
            * (HISTORICAL_END_YEAR - START_YEAR + 1)
            * len(EXPECTED_PERCENTILES)
            * len(district_ids)
        )
        if len(historical) != expected_historical:
            raise ValueError(
                f"Incomplete historical yearly rows: found {len(historical):,}, "
                f"expected {expected_historical:,}"
            )
        _write_averaged_historical(writer, YEARLY_COLUMNS, historical)

    return projection_count + len(historical)


def _update_retained_digest(
    digest,
    row: dict[str, str],
    columns: tuple[str, ...],
) -> None:
    digest.update("\x1f".join(row[column] for column in columns).encode("utf-8"))
    digest.update(b"\n")


def merge_period_values(
    existing_path: Path,
    target_csv: Path,
    output_path: Path,
) -> tuple[int, int, str]:
    retained_count = 0
    replaced_count = 0
    retained_digest = hashlib.sha256()
    with existing_path.open("r", encoding="utf-8", newline="") as existing_handle:
        reader = csv.DictReader(existing_handle)
        if tuple(reader.fieldnames or ()) != PERIOD_COLUMNS:
            raise ValueError(f"Unexpected period CSV columns: {reader.fieldnames}")
        with output_path.open("w", encoding="utf-8", newline="") as output_handle:
            writer = csv.DictWriter(output_handle, fieldnames=PERIOD_COLUMNS, lineterminator="\n")
            writer.writeheader()
            for row in reader:
                if row["variable"] in TARGET_VARIABLES:
                    replaced_count += 1
                    continue
                writer.writerow(row)
                _update_retained_digest(retained_digest, row, PERIOD_COLUMNS)
                retained_count += 1
            with target_csv.open("r", encoding="utf-8", newline="") as target_handle:
                target_reader = csv.DictReader(target_handle)
                if tuple(target_reader.fieldnames or ()) != PERIOD_COLUMNS:
                    raise ValueError("Generated temperature period CSV has unexpected columns")
                writer.writerows(target_reader)
    return retained_count, replaced_count, retained_digest.hexdigest()


def _open_reproducible_gzip_text(path: Path):
    raw_handle = path.open("wb")
    gzip_handle = gzip.GzipFile(filename="", mode="wb", fileobj=raw_handle, mtime=0)
    text_handle = io.TextIOWrapper(gzip_handle, encoding="utf-8", newline="")
    return raw_handle, gzip_handle, text_handle


def merge_yearly_values(
    existing_path: Path,
    target_csv: Path,
    output_path: Path,
) -> tuple[int, int, str]:
    retained_count = 0
    replaced_count = 0
    retained_digest = hashlib.sha256()
    raw_handle, gzip_handle, text_handle = _open_reproducible_gzip_text(output_path)
    try:
        writer = csv.DictWriter(text_handle, fieldnames=YEARLY_COLUMNS, lineterminator="\n")
        writer.writeheader()
        with gzip.open(existing_path, "rt", encoding="utf-8", newline="") as existing_handle:
            reader = csv.DictReader(existing_handle)
            if tuple(reader.fieldnames or ()) != YEARLY_COLUMNS:
                raise ValueError(f"Unexpected yearly CSV columns: {reader.fieldnames}")
            for row in reader:
                if row["variable"] in TARGET_VARIABLES:
                    replaced_count += 1
                    continue
                writer.writerow(row)
                _update_retained_digest(retained_digest, row, YEARLY_COLUMNS)
                retained_count += 1
        with target_csv.open("r", encoding="utf-8", newline="") as target_handle:
            reader = csv.DictReader(target_handle)
            if tuple(reader.fieldnames or ()) != YEARLY_COLUMNS:
                raise ValueError("Generated temperature yearly CSV has unexpected columns")
            writer.writerows(reader)
    finally:
        text_handle.close()
        if not gzip_handle.closed:
            gzip_handle.close()
        if not raw_handle.closed:
            raw_handle.close()
    return retained_count, replaced_count, retained_digest.hexdigest()


def validate_period_values(
    path: Path,
    expected_total: int,
    expected_target_count: int,
    expected_retained_digest: str,
    district_ids: set[str],
) -> None:
    total = 0
    target_count = 0
    target_keys: set[tuple[object, ...]] = set()
    retained_digest = hashlib.sha256()
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != PERIOD_COLUMNS:
            raise ValueError("Merged period CSV has unexpected columns")
        for row in reader:
            total += 1
            if row["variable"] not in TARGET_VARIABLES:
                _update_retained_digest(retained_digest, row, PERIOD_COLUMNS)
                continue
            target_count += 1
            period = row["period"]
            scenario = row["scenario"]
            if period == "baseline":
                if scenario != "historical":
                    raise ValueError(f"Baseline temperature row is not historical: {row}")
            elif period not in FUTURE_PERIODS or scenario not in EXPECTED_SCENARIOS:
                raise ValueError(f"Unexpected temperature period/scenario: {period}/{scenario}")
            key = (
                row["variable"],
                row["district_id"],
                period,
                scenario,
                row["percentile"],
            )
            if key in target_keys:
                raise ValueError(f"Duplicate temperature period row: {key}")
            target_keys.add(key)
            _validate_temperature_row(row, district_ids)

    if total != expected_total or target_count != expected_target_count:
        raise ValueError(
            f"Merged period counts are total={total:,}, target={target_count:,}; "
            f"expected total={expected_total:,}, target={expected_target_count:,}"
        )
    if retained_digest.hexdigest() != expected_retained_digest:
        raise ValueError("Unrelated period rows changed during the targeted merge")


def validate_yearly_values(
    path: Path,
    expected_total: int,
    expected_target_count: int,
    expected_retained_digest: str,
    district_ids: set[str],
) -> None:
    total = 0
    target_count = 0
    target_keys: set[tuple[object, ...]] = set()
    retained_digest = hashlib.sha256()
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != YEARLY_COLUMNS:
            raise ValueError("Merged yearly CSV has unexpected columns")
        for row in reader:
            total += 1
            if row["variable"] not in TARGET_VARIABLES:
                _update_retained_digest(retained_digest, row, YEARLY_COLUMNS)
                continue
            target_count += 1
            year = int(row["year"])
            scenario = row["scenario"]
            if not START_YEAR <= year <= END_YEAR:
                raise ValueError(f"Temperature chart year outside 1950-2100: {year}")
            if (year <= HISTORICAL_END_YEAR) != (scenario == "historical"):
                raise ValueError(f"Temperature history/projection boundary mismatch: {row}")
            if scenario != "historical" and scenario not in EXPECTED_SCENARIOS:
                raise ValueError(f"Unexpected temperature chart scenario: {scenario}")
            key = (
                row["variable"],
                row["district_id"],
                scenario,
                year,
                row["percentile"],
            )
            if key in target_keys:
                raise ValueError(f"Duplicate temperature yearly row: {key}")
            target_keys.add(key)
            _validate_temperature_row(row, district_ids)

    if total != expected_total or target_count != expected_target_count:
        raise ValueError(
            f"Merged yearly counts are total={total:,}, target={target_count:,}; "
            f"expected total={expected_total:,}, target={expected_target_count:,}"
        )
    if retained_digest.hexdigest() != expected_retained_digest:
        raise ValueError("Unrelated yearly rows changed during the targeted merge")


def validate_timeseries(directory: Path, district_ids: set[str]) -> None:
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
                    if point.get("unit") != "°C":
                        raise ValueError(f"{path.name} has an unexpected temperature unit")
                    values = [float(point[name]) for name in ("p10", "p50", "p90")]
                    if not all(math.isfinite(value) for value in values):
                        raise ValueError(f"{path.name} has non-finite temperature values")
                    if not values[0] <= values[1] <= values[2]:
                        raise ValueError(f"{path.name} has unordered temperature percentiles")


def write_summary(
    source_path: Path,
    output_path: Path,
    period_rows: int,
    yearly_rows: int,
) -> None:
    summary = json.loads(source_path.read_text(encoding="utf-8"))
    summary["period_rows"] = period_rows
    summary["yearly_rows"] = yearly_rows
    output_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def _replace_staged_timeseries(staged_directory: Path, output_directory: Path) -> None:
    staged_paths = sorted(staged_directory.glob("*.json.gz"))
    existing_names = {path.name for path in output_directory.glob("*.json.gz")}
    staged_names = {path.name for path in staged_paths}
    if existing_names != staged_names:
        raise ValueError("Refusing to replace a different set of per-district timeseries files")
    for staged_path in staged_paths:
        os.replace(staged_path, output_directory / staged_path.name)


def _reset_windows_acl_inheritance(files: tuple[Path, ...], directories: tuple[Path, ...]) -> None:
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
    guarded_hashes = _guarded_map_hashes(args.period_file.parent)
    sources = validate_sources(args.temperature_dir)
    print("Validated all twelve seasonal temperature inputs.")

    districts = load_districts(args.districts)
    district_ids = set(districts["district_id"].astype(str))
    if len(district_ids) != EXPECTED_DISTRICT_COUNT or len(districts) != EXPECTED_DISTRICT_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_DISTRICT_COUNT} unique districts, found {len(district_ids)}"
        )

    with xr.open_dataset(sources[0].source.path) as sample:
        grid_lookup = build_grid_lookup(sample["lat"].values, sample["lon"].values, districts)
        nearest_lookup = build_nearest_cell_lookup(
            sample["lat"].values,
            sample["lon"].values,
            districts,
        )

    with tempfile.TemporaryDirectory(prefix="seasonal-temperature-", dir=args.period_file.parent) as temp:
        staging_root = Path(temp)
        target_period = staging_root / "temperature_period.csv"
        target_yearly = staging_root / "temperature_yearly.csv"
        staged_period = staging_root / args.period_file.name
        staged_yearly = staging_root / args.yearly_file.name
        staged_summary = staging_root / args.summary_file.name
        staged_timeseries = staging_root / "district_timeseries"

        period_target_count = build_period_rows(
            sources,
            districts,
            grid_lookup,
            nearest_lookup,
            target_period,
        )
        yearly_target_count = build_yearly_rows(
            sources,
            districts,
            grid_lookup,
            nearest_lookup,
            target_yearly,
        )
        expected_period_target = (
            len(TARGET_VARIABLES)
            * len(EXPECTED_PERCENTILES)
            * len(district_ids)
            * (1 + len(EXPECTED_SCENARIOS) * len(FUTURE_PERIODS))
        )
        expected_yearly_target = (
            len(TARGET_VARIABLES)
            * len(EXPECTED_PERCENTILES)
            * len(district_ids)
            * (
                (HISTORICAL_END_YEAR - START_YEAR + 1)
                + len(EXPECTED_SCENARIOS) * (END_YEAR - HISTORICAL_END_YEAR)
            )
        )
        if period_target_count != expected_period_target:
            raise ValueError(
                f"Generated {period_target_count:,} period rows; expected {expected_period_target:,}"
            )
        if yearly_target_count != expected_yearly_target:
            raise ValueError(
                f"Generated {yearly_target_count:,} yearly rows; expected {expected_yearly_target:,}"
            )

        period_retained, period_replaced, period_digest = merge_period_values(
            args.period_file,
            target_period,
            staged_period,
        )
        yearly_retained, yearly_replaced, yearly_digest = merge_yearly_values(
            args.yearly_file,
            target_yearly,
            staged_yearly,
        )
        period_total = period_retained + period_target_count
        yearly_total = yearly_retained + yearly_target_count
        validate_period_values(
            staged_period,
            period_total,
            period_target_count,
            period_digest,
            district_ids,
        )
        validate_yearly_values(
            staged_yearly,
            yearly_total,
            yearly_target_count,
            yearly_digest,
            district_ids,
        )
        write_summary(
            args.summary_file,
            staged_summary,
            period_total,
            yearly_total,
        )

        generated_ids = build_district_timeseries(staged_yearly, staged_timeseries)
        if generated_ids != district_ids:
            raise ValueError("District timeseries generation did not include all districts")
        validate_timeseries(staged_timeseries, district_ids)
        _assert_hashes_unchanged(guarded_hashes)

        _replace_staged_timeseries(staged_timeseries, args.timeseries_dir)
        os.replace(staged_period, args.period_file)
        os.replace(staged_yearly, args.yearly_file)
        os.replace(staged_summary, args.summary_file)
        _reset_windows_acl_inheritance(
            (args.period_file, args.yearly_file, args.summary_file),
            (args.timeseries_dir,),
        )

    _assert_hashes_unchanged(guarded_hashes)
    print(
        f"Imported {period_target_count:,} period rows and {yearly_target_count:,} yearly rows; "
        f"replaced {period_replaced:,} period rows and {yearly_replaced:,} yearly rows."
    )
    print(
        f"Datasets now contain {period_total:,} period rows and {yearly_total:,} yearly rows; "
        f"rebuilt {len(district_ids)} district timeseries files."
    )


if __name__ == "__main__":
    main()
