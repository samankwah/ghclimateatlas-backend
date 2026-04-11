"""
Climate API endpoints
Serves climate projection data for Ghana districts
"""
from typing import List

from fastapi import APIRouter, HTTPException, Query, Response

from app.models.schemas import (
    ClimateVariable,
    ClimateResponse,
    ClimateValue,
    ClimateComparisonResponse,
    ClimateComparison,
    ClimateTimeSeriesResponse,
)
from app.data.mock_data import (
    CLIMATE_VARIABLES,
    REGIONS,
    REGIONAL_BASELINES,
    generate_district_id,
    get_mock_variable_value,
)
from app.services.real_climate import (
    build_real_climate_comparison,
    build_real_climate_response,
    build_real_climate_timeseries,
    get_supported_variables,
    has_real_climate_data,
    normalize_percentile,
)

router = APIRouter()

VALID_PERIODS = ["baseline", "2030", "2050", "2080"]
RCP_SCENARIOS = ["historical", "rcp26", "rcp45", "rcp85"]
SEA_LEVEL_SCENARIOS = ["historical", "ssp126", "ssp245", "ssp585"]


def _is_sea_level_variable(variable_id: str) -> bool:
    return variable_id == "sea_level_rise"


def _get_valid_scenarios(variable_id: str) -> list[str]:
    return SEA_LEVEL_SCENARIOS if _is_sea_level_variable(variable_id) else RCP_SCENARIOS


def _get_available_variables() -> list[dict]:
    if not has_real_climate_data():
        return CLIMATE_VARIABLES

    supported = get_supported_variables()
    return [var for var in CLIMATE_VARIABLES if var["id"] in supported]


def _resolve_variable(variable_id: str) -> dict | None:
    return next((var for var in _get_available_variables() if var["id"] == variable_id), None)


@router.get("/variables", response_model=List[ClimateVariable])
async def get_climate_variables():
    """
    Get list of all available climate variables with metadata.
    """
    return _get_available_variables()


@router.get("/variables/{variable_id}", response_model=ClimateVariable)
async def get_climate_variable(variable_id: str):
    """
    Get metadata for a specific climate variable.
    """
    var = _resolve_variable(variable_id)
    if var:
        return var
    raise HTTPException(status_code=404, detail=f"Variable {variable_id} not found")


@router.get("/{variable}", response_model=ClimateResponse)
async def get_climate_data(
    variable: str,
    response: Response,
    period: str = Query(
        "baseline",
        description="Time period: baseline, 2030 (2021-2040), 2050 (2041-2060), or 2080 (2081-2100)",
    ),
    scenario: str = Query("rcp45", description="Emission scenario: historical, rcp26, rcp45, or rcp85"),
    percentile: str = Query("p50", description="Ensemble percentile: p10, p50, or p90"),
):
    """
    Get climate values for all districts for a specific variable, period, and scenario.

    - **variable**: Climate variable ID (e.g., annual_max_temp, annual_precipitation)
    - **period**: Time period (baseline, 2030/2021-2040, 2050/2041-2060, 2080/2081-2100)
    - **scenario**: Emission scenario (historical, rcp26, rcp45, rcp85)
    """
    # Validate variable
    var_info = _resolve_variable(variable)
    if not var_info:
        raise HTTPException(
            status_code=404,
            detail=f"Variable '{variable}' not found. Available: {[v['id'] for v in _get_available_variables()]}"
        )

    # Validate period
    if period not in VALID_PERIODS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid period '{period}'. Valid periods: {VALID_PERIODS}"
        )

    # Validate scenario
    valid_scenarios = _get_valid_scenarios(variable)
    if scenario not in valid_scenarios:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid scenario '{scenario}'. Valid scenarios: {valid_scenarios}"
        )

    normalized_percentile = normalize_percentile(percentile)
    response.headers["Cache-Control"] = "public, max-age=3600"

    # Handle baseline period
    if period == "baseline":
        scenario = "historical"

    real_response = build_real_climate_response(variable, period, scenario, normalized_percentile)
    if real_response is not None:
        return real_response

    if has_real_climate_data():
        raise HTTPException(
            status_code=404,
            detail=(
                f"Real climate data is unavailable for variable='{variable}', "
                f"period='{period}', scenario='{scenario}', percentile='{normalized_percentile}'."
            ),
        )

    # Generate climate values for all districts
    data = []
    for region_name, district_list in REGIONS.items():
        baseline_values = REGIONAL_BASELINES.get(region_name, REGIONAL_BASELINES["Greater Accra"])

        for district_name in district_list:
            district_id = generate_district_id(region_name, district_name)

            # Add small random variation per district (±5%)
            import hashlib
            hash_val = int(hashlib.md5(district_id.encode()).hexdigest()[:8], 16)
            variation = ((hash_val % 100) - 50) / 1000  # -5% to +5%

            value = get_mock_variable_value(baseline_values, variable, scenario, period, region_name, district_name)
            value = round(value * (1 + variation), 1)

            data.append(ClimateValue(
                district_id=district_id,
                district_name=district_name,
                value=value,
            ))

    # Fill in districts from real GeoJSON that aren't in mock REGIONS
    from app.services.real_climate import load_districts_geojson
    geojson = load_districts_geojson()
    if geojson:
        mock_ids = {d.district_id for d in data}
        fallback_baseline = REGIONAL_BASELINES.get("Greater Accra")
        for feature in geojson.get("features", []):
            props = feature.get("properties", {})
            fid = props.get("id")
            if fid and fid not in mock_ids:
                region_name = props.get("region", "Greater Accra")
                district_name = props.get("name", fid)
                baseline_values = REGIONAL_BASELINES.get(region_name, fallback_baseline)
                value = get_mock_variable_value(baseline_values, variable, scenario, period, region_name, district_name)
                import hashlib
                hash_val = int(hashlib.md5(fid.encode()).hexdigest()[:8], 16)
                variation = ((hash_val % 100) - 50) / 1000
                value = round(value * (1 + variation), 1)
                data.append(ClimateValue(district_id=fid, district_name=district_name, value=value))

    return ClimateResponse(
        variable=variable,
        variable_name=var_info["name"],
        period=period,
        scenario=scenario if period != "baseline" else "historical",
        unit=var_info["unit"],
        percentile=normalized_percentile,
        data=data,
    )


@router.get("/{variable}/compare", response_model=ClimateComparisonResponse)
async def compare_climate_data(
    variable: str,
    response: Response,
    period: str = Query("2050", description="Future time period to compare against baseline"),
    scenario: str = Query("rcp45", description="Emission scenario: rcp26, rcp45, or rcp85"),
    percentile: str = Query("p50", description="Ensemble percentile: p10, p50, or p90"),
):
    """
    Compare baseline climate values with future projections.
    Returns change amounts and percentages for each district.

    - **variable**: Climate variable ID
    - **period**: Future time period (2030/2021-2040, 2050/2041-2060, 2080/2081-2100)
    - **scenario**: Emission scenario (rcp26, rcp45, rcp85)
    """
    # Validate variable
    var_info = _resolve_variable(variable)
    if not var_info:
        raise HTTPException(
            status_code=404,
            detail=f"Variable '{variable}' not found"
        )

    # Validate inputs
    if period not in ["2030", "2050", "2080"]:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid period '{period}'. Valid periods for comparison: "
                "2030 (2021-2040), 2050 (2041-2060), 2080 (2081-2100)"
            )
        )

    valid_comparison_scenarios = [item for item in _get_valid_scenarios(variable) if item != "historical"]
    if scenario not in valid_comparison_scenarios:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid scenario '{scenario}'. Valid scenarios: {valid_comparison_scenarios}"
        )

    normalized_percentile = normalize_percentile(percentile)
    response.headers["Cache-Control"] = "public, max-age=3600"

    real_response = build_real_climate_comparison(variable, period, scenario, normalized_percentile)
    if real_response is not None:
        return real_response

    if has_real_climate_data():
        raise HTTPException(
            status_code=404,
            detail=(
                f"Real climate comparison data is unavailable for variable='{variable}', "
                f"period='{period}', scenario='{scenario}', percentile='{normalized_percentile}'."
            ),
        )

    # Generate comparison data
    data = []
    for region_name, district_list in REGIONS.items():
        baseline_values = REGIONAL_BASELINES.get(region_name, REGIONAL_BASELINES["Greater Accra"])

        for district_name in district_list:
            district_id = generate_district_id(region_name, district_name)

            # Add small variation
            import hashlib
            hash_val = int(hashlib.md5(district_id.encode()).hexdigest()[:8], 16)
            variation = ((hash_val % 100) - 50) / 1000

            baseline = round(get_mock_variable_value(baseline_values, variable, "historical", "baseline", region_name, district_name) * (1 + variation), 1)
            future = round(get_mock_variable_value(baseline_values, variable, scenario, period, region_name, district_name) * (1 + variation), 1)

            change = round(future - baseline, 1)
            change_percent = round((change / baseline) * 100, 1) if baseline != 0 else 0

            data.append(ClimateComparison(
                district_id=district_id,
                district_name=district_name,
                baseline=baseline,
                future=future,
                change=change,
                change_percent=change_percent,
            ))

    # Fill in districts from real GeoJSON that aren't in mock REGIONS
    from app.services.real_climate import load_districts_geojson
    geojson = load_districts_geojson()
    if geojson:
        mock_ids = {d.district_id for d in data}
        fallback_baseline = REGIONAL_BASELINES.get("Greater Accra")
        for feature in geojson.get("features", []):
            props = feature.get("properties", {})
            fid = props.get("id")
            if fid and fid not in mock_ids:
                region_name = props.get("region", "Greater Accra")
                district_name = props.get("name", fid)
                baseline_values = REGIONAL_BASELINES.get(region_name, fallback_baseline)

                import hashlib
                hash_val = int(hashlib.md5(fid.encode()).hexdigest()[:8], 16)
                variation = ((hash_val % 100) - 50) / 1000

                baseline_val = round(get_mock_variable_value(baseline_values, variable, "historical", "baseline", region_name, district_name) * (1 + variation), 1)
                future_val = round(get_mock_variable_value(baseline_values, variable, scenario, period, region_name, district_name) * (1 + variation), 1)

                change = round(future_val - baseline_val, 1)
                change_percent = round((change / baseline_val) * 100, 1) if baseline_val != 0 else 0

                data.append(ClimateComparison(
                    district_id=fid,
                    district_name=district_name,
                    baseline=baseline_val,
                    future=future_val,
                    change=change,
                    change_percent=change_percent,
                ))

    return ClimateComparisonResponse(
        variable=variable,
        variable_name=var_info["name"],
        period=period,
        scenario=scenario,
        unit=var_info["unit"],
        percentile=normalized_percentile,
        data=data,
    )


@router.get("/{variable}/timeseries", response_model=ClimateTimeSeriesResponse)
async def get_climate_timeseries(
    variable: str,
    response: Response,
    district_id: str = Query(..., description="District ID"),
    scenario: str = Query("rcp45", description="Scenario for future years"),
):
    """Get yearly district climate time series with p10/p50/p90 values."""
    var_info = _resolve_variable(variable)
    if not var_info:
        raise HTTPException(status_code=404, detail=f"Variable '{variable}' not found")

    valid_scenarios = [item for item in _get_valid_scenarios(variable) if item != "historical"]
    if scenario not in valid_scenarios:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid scenario '{scenario}'. Valid scenarios: {valid_scenarios}"
        )

    response.headers["Cache-Control"] = "public, max-age=3600"

    real_response = build_real_climate_timeseries(variable, district_id, scenario)
    if real_response is not None:
        return real_response

    raise HTTPException(
        status_code=404,
        detail=(
            f"Yearly climate time series is unavailable for variable='{variable}', "
            f"district_id='{district_id}', scenario='{scenario}'."
        ),
    )


@router.get("/{variable}/range")
async def get_variable_range(
    variable: str,
    response: Response,
    period: str = Query("baseline", description="Time period"),
    scenario: str = Query("rcp45", description="Emission scenario"),
    percentile: str = Query("p50", description="Ensemble percentile"),
):
    """
    Get min/max range for a variable across all districts.
    Useful for setting up color scale legends.
    """
    response.headers["Cache-Control"] = "public, max-age=3600"
    # Get the full climate data
    climate_response = await get_climate_data(variable, response, period, scenario, percentile)

    values = [d.value for d in climate_response.data]

    return {
        "variable": variable,
        "period": period,
        "scenario": scenario,
        "percentile": climate_response.percentile,
        "min": min(values),
        "max": max(values),
        "mean": round(sum(values) / len(values), 1),
    }
