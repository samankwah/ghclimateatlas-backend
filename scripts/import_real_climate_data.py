from __future__ import annotations

import argparse
import gzip
import json
import re
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr
from shapely.geometry import Point


FILE_PATTERN = re.compile(
    r"(?P<indicator_id>10[12]|20[12])-qdm_CORDEX_Ghana0p0375_(?P<scenario>rcp26|rcp45|rcp85)_ensstats\.nc$",
    re.IGNORECASE,
)
SEA_LEVEL_PERIOD_FILE = "SLRprojectionsPeriods.nc"
VARIABLE_MAPPING = {
    ("101", "annual"): {"variable": "annual_mean_temp", "kind": "periods"},
    ("102", "annual"): {"variable": "annual_mean_temp", "kind": "years"},
    ("201", "annual"): {"variable": "annual_precipitation", "kind": "periods"},
    ("202", "annual"): {"variable": "annual_precipitation", "kind": "years"},
    ("101", "amj"): {"variable": "mean_temp_apr_may_jun", "kind": "periods"},
    ("102", "amj"): {"variable": "mean_temp_apr_may_jun", "kind": "years"},
    ("201", "amj"): {"variable": "precipitation_apr_may_jun", "kind": "periods"},
    ("202", "amj"): {"variable": "precipitation_apr_may_jun", "kind": "years"},
    ("101", "jas"): {"variable": "mean_temp_jul_aug_sep", "kind": "periods"},
    ("102", "jas"): {"variable": "mean_temp_jul_aug_sep", "kind": "years"},
    ("201", "jas"): {"variable": "precipitation_jul_aug_sep", "kind": "periods"},
    ("202", "jas"): {"variable": "precipitation_jul_aug_sep", "kind": "years"},
    ("101", "son"): {"variable": "mean_temp_sep_oct_nov", "kind": "periods"},
    ("102", "son"): {"variable": "mean_temp_sep_oct_nov", "kind": "years"},
    ("201", "son"): {"variable": "precipitation_sep_oct_nov", "kind": "periods"},
    ("202", "son"): {"variable": "precipitation_sep_oct_nov", "kind": "years"},
    ("101", "djf"): {"variable": "mean_temp_dry_season", "kind": "periods"},
    ("102", "djf"): {"variable": "mean_temp_dry_season", "kind": "years"},
    ("201", "djf"): {"variable": "precipitation_dec_jan_feb", "kind": "periods"},
    ("202", "djf"): {"variable": "precipitation_dec_jan_feb", "kind": "years"},
}
PERCENTILE_MAPPING = {10: "p10", 50: "p50", 90: "p90"}
SEA_LEVEL_PERCENTILE_MAPPING = {0.1: "p10", 0.5: "p50", 0.9: "p90"}
SEA_LEVEL_SCENARIOS = {"SSP126": "ssp126", "SSP245": "ssp245", "SSP585": "ssp585"}
SEA_LEVEL_PERIOD_MAPPING = {"2021-2040": "2030", "2041-2060": "2050", "2081-2100": "2080"}
COASTAL_DISTRICT_NAMES = {
    "accra metropolitan",
    "accra",
    "tema metropolitan",
    "tema",
    "kpone katamanso",
    "ada east",
    "ada west",
    "ningo prampram",
    "shai osudoku",
    "krowor",
    "ledzokuku",
    "la dade kotopon",
    "ga south",
    "sekondi takoradi metropolitan",
    "sekondi takoradi",
    "effia kwesimintsim",
    "shama",
    "ahanta west",
    "ellembelle",
    "jomoro",
    "nzema east",
    "cape coast metropolitan",
    "cape coast",
    "komenda edina eguafo abrem",
    "mfantseman",
    "ekumfi",
    "gomoa west",
    "gomoa east",
    "effutu",
    "awutu senya east",
    "awutu senya west",
    "keta",
    "keta municipal",
    "ketu south",
    "south tongu",
}
ATLAS_PERIOD_ORDER = ("baseline", "2030", "2050", "2080")
GRID_RESOLUTION_KM = 4.0
SEASON_LENGTH_DAYS = {
    "annual": 365,
    "amj": 91,
    "jas": 92,
    "son": 91,
    "djf": 90,
}


@dataclass(frozen=True)
class SourceFile:
    path: Path
    indicator_id: str
    scenario: str
    season: str
    variable: str
    kind: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate NetCDF climate outputs to districts.")
    parser.add_argument("--temperature-dir", action="append", type=Path, default=[])
    parser.add_argument("--rainfall-dir", action="append", type=Path, default=[])
    parser.add_argument(
        "--source-dir",
        action="append",
        type=Path,
        default=[],
        help="Additional directory containing annual or seasonal NetCDF files.",
    )
    parser.add_argument(
        "--sea-level-dir",
        action="append",
        type=Path,
        default=[],
        help="Directory containing extracted sea-level NetCDF files.",
    )
    parser.add_argument("--districts", required=True, type=Path, help="District GeoJSON or vector file")
    parser.add_argument("--periods-file", required=True, type=Path, help="Path to config/periods.tsv")
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def collect_source_directories(args: argparse.Namespace) -> list[Path]:
    directories = [*args.temperature_dir, *args.rainfall_dir, *args.source_dir]
    unique_directories: list[Path] = []
    seen: set[Path] = set()
    for directory in directories:
        resolved = directory.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_directories.append(directory)
    return unique_directories


def collect_sea_level_files(args: argparse.Namespace) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for directory in args.sea_level_dir:
        for path in sorted(directory.glob(SEA_LEVEL_PERIOD_FILE)):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(path)
    return files


def resolve_variable_mapping(path: Path, indicator_id: str) -> dict[str, str] | None:
    with xr.open_dataset(path) as dataset:
        indicator = dataset["indicator"]
        season = str(indicator.attrs.get("season", "annual")).strip().lower()
        time_binning = str(indicator.attrs.get("time_binning", "")).strip().lower()

    meta = VARIABLE_MAPPING.get((indicator_id, season))
    if meta is None:
        return None
    if time_binning and time_binning != meta["kind"]:
        raise ValueError(
            f"Unexpected time_binning '{time_binning}' for {path.name}; expected '{meta['kind']}'."
        )
    return {"season": season, **meta}


def find_source_files(*directories: Path) -> list[SourceFile]:
    files: list[SourceFile] = []
    for directory in directories:
        for path in sorted(directory.glob("*.nc")):
            match = FILE_PATTERN.search(path.name)
            if not match:
                continue
            indicator_id = match.group("indicator_id")
            scenario = match.group("scenario").lower()
            meta = resolve_variable_mapping(path, indicator_id)
            if meta is None:
                continue
            files.append(
                SourceFile(
                    path=path,
                    indicator_id=indicator_id,
                    scenario=scenario,
                    season=meta["season"],
                    variable=meta["variable"],
                    kind=meta["kind"],
                )
            )
    return files


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def is_direct_coastal_district(district_name: str) -> bool:
    return normalize_name(district_name) in COASTAL_DISTRICT_NAMES


def load_districts(path: Path) -> gpd.GeoDataFrame:
    districts = gpd.read_file(path)
    if districts.crs is None:
        raise ValueError("District file must have a CRS defined.")
    districts = districts.to_crs("EPSG:4326").copy()

    name_column = next(
        (col for col in districts.columns if col.lower() in {"level3name", "name", "district", "district_name"}),
        None,
    )
    region_column = next(
        (col for col in districts.columns if col.lower() in {"level2name", "region", "region_name"}),
        None,
    )
    id_column = next((col for col in districts.columns if col.lower() in {"id", "district_id"}), None)

    if name_column is None or region_column is None:
        raise ValueError("District file must contain name and region columns.")

    # Merge multipart districts such as Adansi Asokwa before deriving IDs and centroids.
    districts = (
        districts[[region_column, name_column, "geometry"]]
        .rename(columns={region_column: "region", name_column: "district_name"})
        .dissolve(by=["region", "district_name"], as_index=False)
    )
    region_column = "region"
    name_column = "district_name"

    if id_column is None:
        districts["district_id"] = districts.apply(
            lambda row: (
                f"GH-{normalize_name(str(row[region_column]))[:3].upper()}-"
                f"{normalize_name(str(row[name_column])).replace(' ', '_')[:5].upper()}"
            ),
            axis=1,
        )
        id_column = "district_id"

    districts["district_id"] = districts[id_column].astype(str)
    duplicate_counts: dict[str, int] = {}
    unique_ids: list[str] = []
    for district_id in districts["district_id"].tolist():
        count = duplicate_counts.get(district_id, 0) + 1
        duplicate_counts[district_id] = count
        unique_ids.append(district_id if count == 1 else f"{district_id}_{count}")

    districts["district_id"] = unique_ids
    districts["district_name"] = districts[name_column].astype(str)
    districts["region"] = districts[region_column].astype(str)
    districts["centroid"] = districts.geometry.representative_point().apply(lambda geom: [geom.x, geom.y])
    return districts[["district_id", "district_name", "region", "geometry", "centroid"]]


def export_district_geojson(districts: gpd.GeoDataFrame, output_path: Path) -> None:
    features = []
    for record in districts.to_dict("records"):
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "id": record["district_id"],
                    "name": record["district_name"],
                    "region": record["region"],
                    "centroid": record["centroid"],
                },
                "geometry": json.loads(
                    gpd.GeoSeries([record["geometry"]], crs="EPSG:4326").to_json()
                )["features"][0]["geometry"],
            }
        )

    payload = {"type": "FeatureCollection", "features": features}
    output_path.write_text(json.dumps(payload), encoding="utf-8")


def build_grid_lookup(latitudes: np.ndarray, longitudes: np.ndarray, districts: gpd.GeoDataFrame) -> dict[str, np.ndarray]:
    lon_grid, lat_grid = np.meshgrid(longitudes, latitudes)
    points = gpd.GeoDataFrame(
        {
            "lat_idx": np.repeat(np.arange(len(latitudes)), len(longitudes)),
            "lon_idx": np.tile(np.arange(len(longitudes)), len(latitudes)),
        },
        geometry=[Point(lon, lat) for lon, lat in zip(lon_grid.ravel(), lat_grid.ravel(), strict=False)],
        crs="EPSG:4326",
    )
    joined = gpd.sjoin(points, districts[["district_id", "geometry"]], predicate="within", how="inner")

    lookup: dict[str, np.ndarray] = {}
    for district_id, frame in joined.groupby("district_id"):
        lookup[district_id] = frame[["lat_idx", "lon_idx"]].to_numpy(dtype=int)
    return lookup


def build_nearest_cell_lookup(
    latitudes: np.ndarray,
    longitudes: np.ndarray,
    districts: gpd.GeoDataFrame,
) -> dict[str, tuple[int, int]]:
    lookup: dict[str, tuple[int, int]] = {}
    for district in districts.to_dict("records"):
        centroid_lon, centroid_lat = district["centroid"]
        lat_idx = int(np.abs(latitudes - centroid_lat).argmin())
        lon_idx = int(np.abs(longitudes - centroid_lon).argmin())
        lookup[district["district_id"]] = (lat_idx, lon_idx)
    return lookup


def parse_period_definitions(path: Path) -> dict[str, str]:
    frame = pd.read_csv(path, sep="\t")
    columns = {col.lower(): col for col in frame.columns}
    period_id_col = next((columns[col] for col in columns if "period" in col and "id" in col), None)
    if period_id_col is None:
        period_id_col = columns.get("id")

    label_col = next((columns[col] for col in columns if "atlas" in col or "label" in col or "period_name" in col), None)
    if label_col is None:
        label_col = columns.get("name")
    start_col = next((columns[col] for col in columns if col in {"start_year", "start"}), None)
    end_col = next((columns[col] for col in columns if col in {"end_year", "end"}), None)

    mapping: dict[str, str] = {}
    if period_id_col and label_col:
        for row in frame.to_dict("records"):
            label = str(row[label_col]).strip().lower()
            if label in ATLAS_PERIOD_ORDER:
                mapping[str(row[period_id_col])] = label
        if mapping:
            return mapping

    if period_id_col and start_col and end_col:
        for row in frame.to_dict("records"):
            start_year = int(row[start_col])
            end_year = int(row[end_col])
            if end_year <= 2020:
                mapping[str(row[period_id_col])] = "baseline"
            elif start_year <= 2050 and end_year <= 2050:
                mapping[str(row[period_id_col])] = "2030"
            elif start_year <= 2070 and end_year <= 2070:
                mapping[str(row[period_id_col])] = "2050"
            else:
                mapping[str(row[period_id_col])] = "2080"
        if mapping:
            return mapping

    raise ValueError("Could not derive atlas period mapping from periods.tsv.")


def convert_units(variable: str, values: np.ndarray, units: str, season: str) -> tuple[np.ndarray, str]:
    if variable in {
        "annual_mean_temp",
        "mean_temp_apr_may_jun",
        "mean_temp_jul_aug_sep",
        "mean_temp_sep_oct_nov",
        "mean_temp_dry_season",
    } and units == "K":
        return values - 273.15, "°C"
    if units == "mm/s" and variable in {
        "annual_precipitation",
        "precipitation_apr_may_jun",
        "precipitation_jul_aug_sep",
        "precipitation_sep_oct_nov",
        "precipitation_dec_jan_feb",
    }:
        season_days = SEASON_LENGTH_DAYS.get(season, 365)
        converted = values * 60 * 60 * 24 * season_days
        unit = "mm/year" if season == "annual" else "mm"
        return converted, unit
    return values, units


def aggregate_values_for_districts(
    data_array: xr.DataArray,
    districts: gpd.GeoDataFrame,
    grid_lookup: dict[str, np.ndarray],
    nearest_cell_lookup: dict[str, tuple[int, int]],
    variable: str,
    season: str,
) -> list[dict[str, object]]:
    raw = data_array.to_numpy()
    units = data_array.attrs.get("units", "")
    converted, unit = convert_units(variable, raw, units, season)
    valid_positions = np.argwhere(~np.isnan(converted))
    results: list[dict[str, object]] = []

    for district in districts.to_dict("records"):
        cell_indices = grid_lookup.get(district["district_id"])
        valid = np.array([], dtype=float)
        if cell_indices is not None and len(cell_indices) > 0:
            values = converted[cell_indices[:, 0], cell_indices[:, 1]]
            valid = values[~np.isnan(values)]
            grid_point_count = int(len(valid))
        else:
            grid_point_count = 0

        if not len(valid):
            nearest_cell = nearest_cell_lookup.get(district["district_id"])
            fallback_value: float | None = None
            if nearest_cell is not None:
                nearest_lat_idx, nearest_lon_idx = nearest_cell
                nearest_value = converted[nearest_lat_idx, nearest_lon_idx]
                if not np.isnan(nearest_value):
                    fallback_value = float(nearest_value)
                elif len(valid_positions):
                    deltas = valid_positions - np.array([nearest_lat_idx, nearest_lon_idx])
                    nearest_valid_idx = int(np.argmin((deltas[:, 0] ** 2) + (deltas[:, 1] ** 2)))
                    fallback_row, fallback_col = valid_positions[nearest_valid_idx]
                    fallback_value = float(converted[fallback_row, fallback_col])
            if fallback_value is None:
                continue
            valid = np.array([fallback_value], dtype=float)
            grid_point_count = 1

        results.append(
            {
                "district_id": district["district_id"],
                "district_name": district["district_name"],
                "region": district["region"],
                "value": float(valid.mean()),
                "grid_point_count": grid_point_count,
                "unit": unit,
            }
        )
    return results


def process_period_file(
    source: SourceFile,
    districts: gpd.GeoDataFrame,
    grid_lookup: dict[str, np.ndarray],
    nearest_cell_lookup: dict[str, tuple[int, int]],
    period_mapping: dict[str, str],
) -> list[dict[str, object]]:
    dataset = xr.open_dataset(source.path)
    rows: list[dict[str, object]] = []
    percentiles = [int(item) for item in dataset["percentiles"].values.tolist()]

    for period_id in dataset["periodID"].values.tolist():
        atlas_period = period_mapping[str(period_id)]
        scenario = "historical" if atlas_period == "baseline" else source.scenario
        for percentile in percentiles:
            percentile_name = PERCENTILE_MAPPING[int(percentile)]
            selection = dataset["indicator"].sel(periodID=period_id, percentiles=percentile)
            for row in aggregate_values_for_districts(
                selection,
                districts,
                grid_lookup,
                nearest_cell_lookup,
                source.variable,
                source.season,
            ):
                rows.append(
                    {
                        **row,
                        "variable": source.variable,
                        "period": atlas_period,
                        "scenario": scenario,
                        "percentile": percentile_name,
                    }
                )
    dataset.close()
    return rows


def process_yearly_file(
    source: SourceFile,
    districts: gpd.GeoDataFrame,
    grid_lookup: dict[str, np.ndarray],
    nearest_cell_lookup: dict[str, tuple[int, int]],
    baseline_end_year: int = 2020,
) -> list[dict[str, object]]:
    dataset = xr.open_dataset(source.path)
    rows: list[dict[str, object]] = []
    percentiles = [int(item) for item in dataset["percentiles"].values.tolist()]

    for time_index, timestamp in enumerate(dataset["time"].values):
        year = pd.Timestamp(timestamp).year
        scenario = "historical" if year <= baseline_end_year else source.scenario
        for percentile in percentiles:
            percentile_name = PERCENTILE_MAPPING[int(percentile)]
            selection = dataset["indicator"].isel(time=time_index).sel(percentiles=percentile)
            for row in aggregate_values_for_districts(
                selection,
                districts,
                grid_lookup,
                nearest_cell_lookup,
                source.variable,
                source.season,
            ):
                rows.append(
                    {
                        **row,
                        "variable": source.variable,
                        "year": year,
                        "scenario": scenario,
                        "percentile": percentile_name,
                    }
                )
    dataset.close()
    return rows


def _normalize_sea_level_units(values: np.ndarray) -> tuple[np.ndarray, str]:
    # The sea-level NetCDF stores values in millimetres across all period slices.
    # Always convert once to centimetres before district aggregation.
    return values / 10.0, "cm"


def process_sea_level_file(
    path: Path,
    districts: gpd.GeoDataFrame,
) -> list[dict[str, object]]:
    dataset = xr.open_dataset(path)
    rows: list[dict[str, object]] = []
    data_array = dataset["sea_level_change"]
    latitudes = dataset["lat"].values
    longitudes = dataset["lon"].values
    grid_lookup = build_grid_lookup(latitudes, longitudes, districts)
    nearest_cell_lookup = build_nearest_cell_lookup(latitudes, longitudes, districts)

    coastal_districts = [
        district
        for district in districts.to_dict("records")
        if is_direct_coastal_district(str(district["district_name"]))
    ]

    for percentile_name in SEA_LEVEL_PERCENTILE_MAPPING.values():
        for district in coastal_districts:
            rows.append(
                {
                    "district_id": district["district_id"],
                    "district_name": district["district_name"],
                    "region": district["region"],
                    "value": 0.0,
                    "grid_point_count": None,
                    "unit": "cm",
                    "variable": "sea_level_rise",
                    "period": "baseline",
                    "scenario": "historical",
                    "percentile": percentile_name,
                }
                )

    for scenario_name, scenario_key in SEA_LEVEL_SCENARIOS.items():
        if scenario_name not in dataset["scenarios"].values:
            continue
        for quantile_value, percentile_name in SEA_LEVEL_PERCENTILE_MAPPING.items():
            if quantile_value not in dataset["quantiles"].values:
                continue
            for year_label, atlas_period in SEA_LEVEL_PERIOD_MAPPING.items():
                if year_label not in dataset["years"].values:
                    continue

                selection = (
                    data_array
                    .sel(scenarios=scenario_name, quantiles=quantile_value, years=year_label)
                    .transpose("lat", "lon")
                )
                converted, unit = _normalize_sea_level_units(selection.to_numpy())
                normalized_selection = xr.DataArray(
                    converted,
                    coords={"lat": selection["lat"].values, "lon": selection["lon"].values},
                    dims=("lat", "lon"),
                    attrs={"units": unit},
                )

                for row in aggregate_values_for_districts(
                    normalized_selection,
                    districts,
                    grid_lookup,
                    nearest_cell_lookup,
                    "sea_level_rise",
                    "annual",
                ):
                    if not is_direct_coastal_district(str(row["district_name"])):
                        continue
                    rows.append(
                        {
                            **row,
                            "variable": "sea_level_rise",
                            "period": atlas_period,
                            "scenario": scenario_key,
                            "percentile": percentile_name,
                        }
                    )

    dataset.close()
    return rows


def main() -> None:
    args = parse_args()
    source_directories = collect_source_directories(args)
    files = find_source_files(*source_directories)
    sea_level_files = collect_sea_level_files(args)
    if not files and not sea_level_files:
        raise SystemExit("No matching NetCDF files found.")

    districts = load_districts(args.districts)
    period_mapping = parse_period_definitions(args.periods_file)

    grid_lookup: dict[str, np.ndarray] = {}
    nearest_cell_lookup: dict[str, tuple[int, int]] = {}
    if files:
        sample_dataset = xr.open_dataset(files[0].path)
        grid_lookup = build_grid_lookup(sample_dataset["lat"].values, sample_dataset["lon"].values, districts)
        nearest_cell_lookup = build_nearest_cell_lookup(
            sample_dataset["lat"].values,
            sample_dataset["lon"].values,
            districts,
        )
        sample_dataset.close()

    period_rows: list[dict[str, object]] = []
    yearly_rows: list[dict[str, object]] = []

    for source in files:
        if source.kind == "periods":
            period_rows.extend(process_period_file(source, districts, grid_lookup, nearest_cell_lookup, period_mapping))
        else:
            yearly_rows.extend(process_yearly_file(source, districts, grid_lookup, nearest_cell_lookup))
    for sea_level_file in sea_level_files:
        period_rows.extend(process_sea_level_file(sea_level_file, districts))

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    period_frame = pd.DataFrame(period_rows)
    if not period_frame.empty:
        period_frame = period_frame.sort_values(
            ["variable", "scenario", "period", "percentile", "region", "district_name"]
        )

    yearly_frame = pd.DataFrame(yearly_rows)
    if not yearly_frame.empty:
        yearly_frame = yearly_frame.sort_values(
            ["variable", "scenario", "year", "percentile", "region", "district_name"]
        )

    period_frame.to_csv(output_dir / "climate_period_values.csv", index=False)
    yearly_csv_path = output_dir / "climate_yearly_values.csv"
    yearly_frame.to_csv(yearly_csv_path, index=False)
    with yearly_csv_path.open("rb") as src, gzip.open(output_dir / "climate_yearly_values.csv.gz", "wb") as dst:
        dst.writelines(src)
    export_district_geojson(districts, output_dir / "districts.geojson")

    summary = {
        "period_rows": len(period_frame),
        "yearly_rows": len(yearly_frame),
        "district_count": int(districts["district_id"].nunique()),
        "grid_resolution_km": GRID_RESOLUTION_KM,
        "variables": sorted(period_frame["variable"].unique().tolist()),
        "scenarios": sorted(period_frame["scenario"].unique().tolist()),
    }
    (output_dir / "import_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
