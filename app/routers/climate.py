"""
Climate API endpoints
Serves climate projection data for Ghana districts
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List

from app.models.schemas import (
    ClimateVariable,
    ClimateResponse,
    ClimateValue,
    ClimateComparisonResponse,
    ClimateComparison,
)
from app.data.mock_data import (
    CLIMATE_VARIABLES,
    GDD_VARIABLES,
    REGIONS,
    REGIONAL_BASELINES,
    generate_district_id,
    get_climate_value,
    compute_maize_heat_units,
    compute_gdd_ghana,
)

router = APIRouter()

VALID_PERIODS = ["baseline", "2030", "2050", "2080"]
VALID_SCENARIOS = ["historical", "rcp45", "rcp85"]


@router.get("/variables", response_model=List[ClimateVariable])
async def get_climate_variables():
    """
    Get list of all available climate variables with metadata.
    """
    return CLIMATE_VARIABLES


@router.get("/variables/{variable_id}", response_model=ClimateVariable)
async def get_climate_variable(variable_id: str):
    """
    Get metadata for a specific climate variable.
    """
    for var in CLIMATE_VARIABLES:
        if var["id"] == variable_id:
            return var
    raise HTTPException(status_code=404, detail=f"Variable {variable_id} not found")


@router.get("/{variable}", response_model=ClimateResponse)
async def get_climate_data(
    variable: str,
    period: str = Query("baseline", description="Time period: baseline, 2030, 2050, or 2080"),
    scenario: str = Query("rcp45", description="Emission scenario: historical, rcp45, or rcp85"),
):
    """
    Get climate values for all districts for a specific variable, period, and scenario.

    - **variable**: Climate variable ID (e.g., annual_max_temp, annual_precipitation)
    - **period**: Time period (baseline, 2030, 2050, 2080)
    - **scenario**: Emission scenario (historical, rcp45, rcp85)
    """
    # Validate variable
    var_info = None
    for v in CLIMATE_VARIABLES:
        if v["id"] == variable:
            var_info = v
            break
    if not var_info:
        raise HTTPException(
            status_code=404,
            detail=f"Variable '{variable}' not found. Available: {[v['id'] for v in CLIMATE_VARIABLES]}"
        )

    # Validate period
    if period not in VALID_PERIODS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid period '{period}'. Valid periods: {VALID_PERIODS}"
        )

    # Validate scenario
    if scenario not in VALID_SCENARIOS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid scenario '{scenario}'. Valid scenarios: {VALID_SCENARIOS}"
        )

    # Handle baseline period
    if period == "baseline":
        scenario = "historical"

    # Check if this is a GDD variable (computed from projected temps)
    is_gdd = variable in GDD_VARIABLES

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

            if is_gdd:
                # Compute GDD from projected max/min temps
                base_temp = GDD_VARIABLES[variable]
                max_baseline = baseline_values.get("annual_max_temp", 32)
                min_baseline = baseline_values.get("annual_min_temp", 22)

                if period == "baseline" or scenario == "historical":
                    max_temp = max_baseline
                    min_temp = min_baseline
                else:
                    max_temp = get_climate_value(max_baseline, "annual_max_temp", scenario, period)
                    min_temp = get_climate_value(min_baseline, "annual_min_temp", scenario, period)

                if variable == "maize_heat_units":
                    value = compute_maize_heat_units(max_temp, min_temp)
                else:
                    value = compute_gdd_ghana(max_temp, min_temp, base_temp)
                value = round(value * (1 + variation), 1)
            else:
                baseline_value = baseline_values.get(variable, 0)

                # Calculate projected value
                if period == "baseline" or scenario == "historical":
                    value = baseline_value
                else:
                    value = get_climate_value(baseline_value, variable, scenario, period)

                value = round(value * (1 + variation), 1)

            data.append(ClimateValue(
                district_id=district_id,
                district_name=district_name,
                value=value,
            ))

    return ClimateResponse(
        variable=variable,
        variable_name=var_info["name"],
        period=period,
        scenario=scenario if period != "baseline" else "historical",
        unit=var_info["unit"],
        data=data,
    )


@router.get("/{variable}/compare", response_model=ClimateComparisonResponse)
async def compare_climate_data(
    variable: str,
    period: str = Query("2050", description="Future time period to compare against baseline"),
    scenario: str = Query("rcp85", description="Emission scenario: rcp45 or rcp85"),
):
    """
    Compare baseline climate values with future projections.
    Returns change amounts and percentages for each district.

    - **variable**: Climate variable ID
    - **period**: Future time period (2030, 2050, 2080)
    - **scenario**: Emission scenario (rcp45, rcp85)
    """
    # Validate variable
    var_info = None
    for v in CLIMATE_VARIABLES:
        if v["id"] == variable:
            var_info = v
            break
    if not var_info:
        raise HTTPException(
            status_code=404,
            detail=f"Variable '{variable}' not found"
        )

    # Validate inputs
    if period not in ["2030", "2050", "2080"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid period '{period}'. Valid periods for comparison: 2030, 2050, 2080"
        )

    if scenario not in ["rcp45", "rcp85"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid scenario '{scenario}'. Valid scenarios: rcp45, rcp85"
        )

    # Check if this is a GDD variable
    is_gdd = variable in GDD_VARIABLES

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

            if is_gdd:
                base_temp = GDD_VARIABLES[variable]
                max_baseline = baseline_values.get("annual_max_temp", 32)
                min_baseline = baseline_values.get("annual_min_temp", 22)

                max_future = get_climate_value(max_baseline, "annual_max_temp", scenario, period)
                min_future = get_climate_value(min_baseline, "annual_min_temp", scenario, period)

                if variable == "maize_heat_units":
                    baseline_gdd = compute_maize_heat_units(max_baseline, min_baseline)
                    future_gdd = compute_maize_heat_units(max_future, min_future)
                else:
                    baseline_gdd = compute_gdd_ghana(max_baseline, min_baseline, base_temp)
                    future_gdd = compute_gdd_ghana(max_future, min_future, base_temp)

                baseline = round(baseline_gdd * (1 + variation), 1)
                future = round(future_gdd * (1 + variation), 1)
            else:
                baseline_value = baseline_values.get(variable, 0)
                baseline = round(baseline_value * (1 + variation), 1)
                future = round(get_climate_value(baseline_value, variable, scenario, period) * (1 + variation), 1)

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

    return ClimateComparisonResponse(
        variable=variable,
        variable_name=var_info["name"],
        period=period,
        scenario=scenario,
        unit=var_info["unit"],
        data=data,
    )


@router.get("/{variable}/range")
async def get_variable_range(
    variable: str,
    period: str = Query("baseline", description="Time period"),
    scenario: str = Query("rcp45", description="Emission scenario"),
):
    """
    Get min/max range for a variable across all districts.
    Useful for setting up color scale legends.
    """
    # Get the full climate data
    response = await get_climate_data(variable, period, scenario)

    values = [d.value for d in response.data]

    return {
        "variable": variable,
        "period": period,
        "scenario": scenario,
        "min": min(values),
        "max": max(values),
        "mean": round(sum(values) / len(values), 1),
    }
