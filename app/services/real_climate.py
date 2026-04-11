from __future__ import annotations

import csv
import gzip
import json
import os
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.data.mock_data import CLIMATE_VARIABLES, generate_district_id
from app.models.schemas import ClimateComparisonResponse, ClimateResponse, ClimateTimeSeriesResponse

DEFAULT_PROCESSED_DIR = Path(__file__).resolve().parents[1] / "data" / "processed"
DEFAULT_DISTRICTS_PATH = DEFAULT_PROCESSED_DIR / "districts.geojson"
DEFAULT_MAP_DISTRICTS_PATH = DEFAULT_PROCESSED_DIR / "districts_map.geojson"
DEFAULT_PERIOD_VALUES_PATH = DEFAULT_PROCESSED_DIR / "climate_period_values.csv"
DEFAULT_YEARLY_VALUES_PATH = DEFAULT_PROCESSED_DIR / "climate_yearly_values.csv.gz"
DEFAULT_SHAPEFILE_PATH = Path(__file__).resolve().parents[3] / "gadm41_GHA_2.shp"
VALID_PERCENTILES = {"p10", "p50", "p90"}
GRID_RESOLUTION_KM = 4.0


def _read_csv_records(path: Path, required_columns: set[str]) -> list[dict[str, Any]]:
    is_gzipped = path.suffix == ".gz"

    # Use stdlib csv instead of pandas to reduce memory footprint (~80MB savings)
    if is_gzipped:
        handle = gzip.open(path, "rt", encoding="utf-8", newline="")
    else:
        handle = path.open("r", encoding="utf-8", newline="")

    with handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        if not required_columns.issubset(fieldnames):
            missing = sorted(required_columns - fieldnames)
            raise ValueError(f"Processed climate data is missing required columns: {missing}")
        return list(reader)


def _read_csv_records_allowing_missing(
    path: Path,
    required_columns: set[str],
    optional_columns: set[str],
) -> list[dict[str, Any]]:
    records = _read_csv_records(path, required_columns)
    for row in records:
        for column in optional_columns:
            row.setdefault(column, None)
    return records


def _normalize_period_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in records:
        normalized.append(
            {
                "district_id": str(row["district_id"]),
                "district_name": str(row["district_name"]),
                "region": str(row["region"]),
                "variable": str(row["variable"]),
                "period": str(row["period"]).lower(),
                "scenario": str(row["scenario"]).lower(),
                "percentile": str(row["percentile"]).lower(),
                "value": float(row["value"]),
                "grid_point_count": int(float(row["grid_point_count"])) if row.get("grid_point_count") not in (None, "") else None,
                "unit": str(row["unit"]),
            }
        )
    return normalized


def _normalize_yearly_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in records:
        normalized.append(
            {
                "district_id": str(row["district_id"]),
                "district_name": str(row["district_name"]),
                "region": str(row["region"]),
                "variable": str(row["variable"]),
                "year": int(row["year"]),
                "scenario": str(row["scenario"]).lower(),
                "percentile": str(row["percentile"]).lower(),
                "value": float(row["value"]),
                "grid_point_count": int(float(row["grid_point_count"])) if row.get("grid_point_count") not in (None, "") else None,
                "unit": str(row["unit"]),
            }
        )
    return normalized


def _dedupe_rows(
    rows: list[dict[str, Any]],
    identity_keys: tuple[str, ...],
    *,
    sort_keys: tuple[str, ...],
) -> list[dict[str, Any]]:
    from collections import defaultdict

    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[tuple(row[key] for key in identity_keys)].append(row)

    deduped: list[dict[str, Any]] = []
    for group in groups.values():
        merged = dict(group[0])  # keep metadata from first row
        # Average the numeric 'value' field across duplicates
        values = [float(r["value"]) for r in group]
        merged["value"] = sum(values) / len(values)
        deduped.append(merged)

    return sorted(deduped, key=lambda row: tuple(row[key] for key in sort_keys))


def get_processed_dir() -> Path:
    configured = os.getenv("CLIMATE_PROCESSED_DIR")
    if configured:
        return Path(configured)
    return DEFAULT_PROCESSED_DIR


def get_districts_path() -> Path:
    configured = os.getenv("CLIMATE_DISTRICTS_PATH")
    if configured:
        return Path(configured)
    return get_processed_dir() / DEFAULT_DISTRICTS_PATH.name


def get_map_districts_path() -> Path:
    configured = os.getenv("CLIMATE_MAP_DISTRICTS_PATH")
    if configured:
        return Path(configured)
    return get_processed_dir() / DEFAULT_MAP_DISTRICTS_PATH.name


def get_fallback_shapefile_path() -> Path:
    configured = os.getenv("CLIMATE_DISTRICTS_SHAPEFILE")
    if configured:
        return Path(configured)
    return DEFAULT_SHAPEFILE_PATH


def get_period_values_path() -> Path:
    configured = os.getenv("CLIMATE_PERIOD_VALUES_PATH")
    if configured:
        return Path(configured)
    return get_processed_dir() / DEFAULT_PERIOD_VALUES_PATH.name


def get_yearly_values_path() -> Path:
    configured = os.getenv("CLIMATE_YEARLY_VALUES_PATH")
    if configured:
        return Path(configured)
    return get_processed_dir() / DEFAULT_YEARLY_VALUES_PATH.name


def normalize_percentile(percentile: str | None) -> str:
    value = (percentile or "p50").lower()
    if value not in VALID_PERCENTILES:
        raise ValueError(f"Invalid percentile '{percentile}'. Valid values: {sorted(VALID_PERCENTILES)}")
    return value


@lru_cache(maxsize=1)
def load_period_values():
    path = get_period_values_path()
    if not path.exists():
        return None

    required_columns = {
        "district_id",
        "district_name",
        "region",
        "variable",
        "period",
        "scenario",
        "percentile",
        "value",
        "unit",
    }
    optional_columns = {"grid_point_count"}
    return _normalize_period_records(
        _read_csv_records_allowing_missing(path, required_columns, optional_columns)
    )


@lru_cache(maxsize=1)
def _period_values_index() -> dict[tuple[str, str, str, str], list[dict[str, Any]]] | None:
    """Build a dict index over period values for O(1) lookup by (variable, period, scenario, percentile)."""
    rows = load_period_values()
    if rows is None:
        return None
    index: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (row["variable"], row["period"], row["scenario"], row["percentile"])
        index[key].append(row)
    return dict(index)


@lru_cache(maxsize=1)
def load_yearly_values():
    path = get_yearly_values_path()
    if not path.exists():
        return None

    required_columns = {
        "district_id",
        "district_name",
        "region",
        "variable",
        "year",
        "scenario",
        "percentile",
        "value",
        "unit",
    }
    optional_columns = {"grid_point_count"}
    return _normalize_yearly_records(
        _read_csv_records_allowing_missing(path, required_columns, optional_columns)
    )


@lru_cache(maxsize=1)
def _yearly_values_index() -> dict[tuple[str, str, str, str], list[dict[str, Any]]] | None:
    """Build a dict index over yearly values for O(1) lookup by (variable, district, scenario, percentile)."""
    rows = load_yearly_values()
    if rows is None:
        return None

    index: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (row["variable"], row["district_id"], row["scenario"], row["percentile"])
        index[key].append(row)

    for key, subset in index.items():
        subset.sort(key=lambda row: row["year"])

    return dict(index)


@lru_cache(maxsize=1)
def load_districts_geojson() -> dict[str, Any] | None:
    path = get_districts_path()
    if not path.exists():
        return load_districts_from_shapefile()

    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=1)
def load_map_districts_geojson() -> dict[str, Any] | None:
    path = get_map_districts_path()
    if not path.exists():
        return load_districts_geojson()

    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=1)
def load_districts_from_shapefile() -> dict[str, Any] | None:
    path = get_fallback_shapefile_path()
    if not path.exists():
        return None

    import geopandas as gpd

    districts = gpd.read_file(path)
    if districts.empty:
        return None

    districts = districts.to_crs("EPSG:4326").copy()
    region_column = next(
        (col for col in districts.columns if col.lower() in {"level2name", "region", "region_name"}),
        None,
    )
    district_column = next(
        (col for col in districts.columns if col.lower() in {"level3name", "district", "district_name", "name"}),
        None,
    )
    if region_column is None or district_column is None:
        return None

    # Merge multipart districts like Adansi Asokwa into one feature before export.
    districts = (
        districts[[region_column, district_column, "geometry"]]
        .rename(columns={region_column: "region", district_column: "name"})
        .dissolve(by=["region", "name"], as_index=False)
    )

    representative_points = districts.geometry.representative_point()
    features = []
    for idx, record in enumerate(districts.to_dict("records"), start=1):
        district_name = str(record["name"])
        region_name = str(record["region"])
        district_id = generate_district_id(region_name, district_name)
        if any(feature["properties"]["id"] == district_id for feature in features):
            district_id = f"{district_id}_{idx}"

        point = representative_points.iloc[idx - 1]
        geometry = json.loads(
            gpd.GeoSeries([record["geometry"]], crs="EPSG:4326").to_json()
        )["features"][0]["geometry"]
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "id": district_id,
                    "name": district_name,
                    "region": region_name,
                    "centroid": [point.x, point.y],
                },
                "geometry": geometry,
            }
        )

    return {"type": "FeatureCollection", "features": features}


def has_real_climate_data() -> bool:
    return get_period_values_path().exists()


def has_real_districts() -> bool:
    return get_districts_path().exists()


def get_variable_meta(variable: str) -> dict[str, Any] | None:
    return next((item for item in CLIMATE_VARIABLES if item["id"] == variable), None)


def get_supported_variables() -> set[str]:
    rows = load_period_values()
    if rows is None:
        return set()
    return {row["variable"] for row in rows if row.get("variable")}


def get_supported_yearly_variables() -> set[str]:
    rows = load_yearly_values()
    if rows is None:
        return set()
    return {row["variable"] for row in rows if row.get("variable")}


def get_real_district_feature_collection(region: str | None = None) -> dict[str, Any] | None:
    payload = load_districts_geojson()
    if payload is None:
        return None

    if not region:
        return payload

    filtered = [
        feature
        for feature in payload.get("features", [])
        if feature.get("properties", {}).get("region", "").lower() == region.lower()
    ]
    return {"type": "FeatureCollection", "features": filtered}


def get_real_map_district_feature_collection(region: str | None = None) -> dict[str, Any] | None:
    payload = load_map_districts_geojson()
    if payload is None:
        return None

    if not region:
        return payload

    filtered = [
        feature
        for feature in payload.get("features", [])
        if feature.get("properties", {}).get("region", "").lower() == region.lower()
    ]
    return {"type": "FeatureCollection", "features": filtered}


def get_real_district(district_id: str) -> dict[str, Any] | None:
    payload = load_districts_geojson()
    if payload is None:
        return None

    return next(
        (
            feature
            for feature in payload.get("features", [])
            if feature.get("properties", {}).get("id") == district_id
        ),
        None,
    )


def get_real_district_list(region: str | None = None) -> list[dict[str, Any]] | None:
    payload = get_real_district_feature_collection(region)
    if payload is None:
        return None

    districts: list[dict[str, Any]] = []
    for feature in payload.get("features", []):
        props = feature.get("properties", {})
        districts.append(
            {
                "id": props.get("id"),
                "name": props.get("name"),
                "region": props.get("region"),
            }
        )
    return districts


def build_real_climate_response(
    variable: str,
    period: str,
    scenario: str,
    percentile: str | None = None,
) -> ClimateResponse | None:
    index = _period_values_index()
    meta = get_variable_meta(variable)
    if index is None or meta is None:
        return None

    normalized_percentile = normalize_percentile(percentile)
    period_key = period.lower()
    scenario_key = ("historical" if period_key == "baseline" else scenario).lower()

    subset = list(index.get((variable, period_key, scenario_key, normalized_percentile), []))
    subset = _dedupe_rows(
        subset,
        ("district_id", "variable", "period", "scenario", "percentile"),
        sort_keys=("region", "district_name", "district_id"),
    )

    if not subset:
        return None

    unit = str(subset[0]["unit"])
    # Sea level rise is stored in cm in CSV; convert to meters for display
    is_slr = variable == "sea_level_rise"
    if is_slr:
        unit = "m"
    data = [
        {
            "district_id": row["district_id"],
            "district_name": row["district_name"],
            "value": round(float(row["value"]) / 100, 3) if is_slr else round(float(row["value"]), 2),
        }
        for row in subset
    ]

    return ClimateResponse(
        variable=variable,
        variable_name=meta["name"],
        period=period_key,
        scenario=scenario_key,
        unit=unit,
        percentile=normalized_percentile,
        data=data,
    )


def build_real_climate_comparison(
    variable: str,
    period: str,
    scenario: str,
    percentile: str | None = None,
) -> ClimateComparisonResponse | None:
    baseline = build_real_climate_response(variable, "baseline", "historical", percentile)
    future = build_real_climate_response(variable, period, scenario, percentile)
    meta = get_variable_meta(variable)
    if baseline is None or future is None or meta is None:
        return None

    baseline_by_district = {entry.district_id: entry for entry in baseline.data}
    comparisons = []
    for entry in future.data:
        baseline_entry = baseline_by_district.get(entry.district_id)
        if baseline_entry is None:
            continue

        change = round(entry.value - baseline_entry.value, 2)
        change_percent = round((change / baseline_entry.value) * 100, 2) if baseline_entry.value else 0.0
        comparisons.append(
            {
                "district_id": entry.district_id,
                "district_name": entry.district_name,
                "baseline": baseline_entry.value,
                "future": entry.value,
                "change": change,
                "change_percent": change_percent,
            }
        )

    if not comparisons:
        return None

    return ClimateComparisonResponse(
        variable=variable,
        variable_name=meta["name"],
        period=period.lower(),
        scenario=scenario.lower(),
        unit=future.unit,
        percentile=future.percentile,
        data=comparisons,
    )


def _normalize_timeseries_unit_and_value(variable: str, unit: str, value: float) -> tuple[str, float]:
    if variable == "sea_level_rise" and unit == "cm":
        return "m", round(value / 100, 4)
    return unit, round(value, 4)


def build_real_climate_timeseries(
    variable: str,
    district_id: str,
    scenario: str,
) -> ClimateTimeSeriesResponse | None:
    index = _yearly_values_index()
    meta = get_variable_meta(variable)
    if index is None or meta is None:
        return None

    historical_p10 = index.get((variable, district_id, "historical", "p10"), [])
    historical_p50 = index.get((variable, district_id, "historical", "p50"), [])
    historical_p90 = index.get((variable, district_id, "historical", "p90"), [])
    scenario_p10 = index.get((variable, district_id, scenario.lower(), "p10"), [])
    scenario_p50 = index.get((variable, district_id, scenario.lower(), "p50"), [])
    scenario_p90 = index.get((variable, district_id, scenario.lower(), "p90"), [])

    if not historical_p50:
        return None

    rows_by_year: dict[int, dict[str, Any]] = {}

    def merge_rows(rows: list[dict[str, Any]], percentile: str) -> None:
        for row in rows:
            year = int(row["year"])
            current = rows_by_year.setdefault(
                year,
                {
                    "year": year,
                    "district_name": row["district_name"],
                    "unit": str(row["unit"]),
                },
            )
            current[percentile] = float(row["value"])

    merge_rows(historical_p10, "p10")
    merge_rows(historical_p50, "p50")
    merge_rows(historical_p90, "p90")
    merge_rows(scenario_p10, "p10")
    merge_rows(scenario_p50, "p50")
    merge_rows(scenario_p90, "p90")

    if not rows_by_year:
        return None

    merged_points = []
    display_unit = None
    for year in sorted(rows_by_year):
        row = rows_by_year[year]
        if not {"p10", "p50", "p90"}.issubset(row):
            continue

        normalized_unit, p10 = _normalize_timeseries_unit_and_value(variable, row["unit"], row["p10"])
        _, p50 = _normalize_timeseries_unit_and_value(variable, row["unit"], row["p50"])
        _, p90 = _normalize_timeseries_unit_and_value(variable, row["unit"], row["p90"])
        display_unit = normalized_unit
        merged_points.append(
            {
                "year": year,
                "p10": p10,
                "p50": p50,
                "p90": p90,
            }
        )

    if not merged_points:
        return None

    reference_start = 1991
    reference_end = 2020
    reference_values = [
        point["p50"]
        for point in merged_points
        if reference_start <= point["year"] <= reference_end
    ]
    if not reference_values:
        return None

    district_name = rows_by_year[merged_points[0]["year"]]["district_name"]
    return ClimateTimeSeriesResponse(
        variable=variable,
        variable_name=meta["name"],
        scenario=scenario.lower(),
        unit=display_unit or str(historical_p50[0]["unit"]),
        district_id=district_id,
        district_name=str(district_name),
        reference_period={"start": reference_start, "end": reference_end},
        reference_mean=round(sum(reference_values) / len(reference_values), 2),
        data=merged_points,
    )


def build_real_district_climate(district_id: str) -> dict[str, dict[str, float]] | None:
    rows = load_period_values()
    if rows is None:
        return None

    subset = [
        row for row in rows
        if row["district_id"] == district_id and row["percentile"] == "p50"
    ]
    subset = _dedupe_rows(
        subset,
        ("district_id", "variable", "period", "scenario", "percentile"),
        sort_keys=("variable", "period", "scenario"),
    )
    if not subset:
        return None

    payload: dict[str, dict[str, float]] = {}
    for row in subset:
        variable = row["variable"]
        period = row["period"]
        scenario = row["scenario"]
        value = round(float(row["value"]), 2)
        payload.setdefault(variable, {})
        key = "baseline" if period == "baseline" else f"{period}_{scenario}"
        payload[variable][key] = value
    return payload


def get_real_grid_point_count(
    district_id: str,
    variable: str,
    period: str,
    scenario: str,
    percentile: str | None = None,
) -> int | None:
    rows = load_period_values()
    if rows is None:
        return None

    normalized_percentile = normalize_percentile(percentile)
    period_key = period.lower()
    scenario_key = ("historical" if period_key == "baseline" else scenario).lower()

    subset = [
        row for row in rows
        if row["district_id"] == district_id
        and row["variable"] == variable
        and row["period"] == period_key
        and row["scenario"] == scenario_key
        and row["percentile"] == normalized_percentile
        and row.get("grid_point_count") is not None
    ]
    subset = _dedupe_rows(
        subset,
        ("district_id", "variable", "period", "scenario", "percentile"),
        sort_keys=("district_id", "variable", "period", "scenario", "percentile"),
    )
    if not subset:
        return None

    return int(round(float(subset[0]["grid_point_count"])))
