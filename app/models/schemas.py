"""
Pydantic schemas for Ghana Climate Atlas API
"""
from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class District(BaseModel):
    """Basic district information"""
    id: str
    name: str
    region: str
    area_km2: Optional[float] = None
    population: Optional[int] = None


class DistrictGeoJSON(BaseModel):
    """GeoJSON Feature for a district"""
    type: str = "Feature"
    properties: Dict[str, Any]
    geometry: Dict[str, Any]


class DistrictFeatureCollection(BaseModel):
    """GeoJSON FeatureCollection for all districts"""
    type: str = "FeatureCollection"
    features: List[DistrictGeoJSON]


class ClimateVariable(BaseModel):
    """Climate variable metadata"""
    id: str
    name: str
    description: str
    unit: str
    category: str  # 'temperature' or 'precipitation'
    color_scale: str  # 'temperature', 'precipitation', 'diverging'


class ClimateValue(BaseModel):
    """Climate value for a single district"""
    district_id: str
    district_name: str
    value: float


class ClimateResponse(BaseModel):
    """Response for climate data query"""
    variable: str
    variable_name: str
    period: str
    scenario: str
    unit: str
    percentile: str | None = None
    data: List[ClimateValue]


class ClimateComparison(BaseModel):
    """Comparison between baseline and future period"""
    district_id: str
    district_name: str
    baseline: float
    future: float
    change: float
    change_percent: float


class ClimateComparisonResponse(BaseModel):
    """Response for climate comparison query"""
    variable: str
    variable_name: str
    period: str
    scenario: str
    unit: str
    percentile: str | None = None
    data: List[ClimateComparison]


class ClimateTimeSeriesPoint(BaseModel):
    """Yearly percentile values for a district time series"""
    year: int
    p10: float
    p50: float
    p90: float


class ClimateTimeSeriesReferencePeriod(BaseModel):
    """Reference period used for the legend mean"""
    start: int
    end: int


class ClimateTimeSeriesResponse(BaseModel):
    """Response for district yearly climate time series"""
    variable: str
    variable_name: str
    scenario: str
    unit: str
    district_id: str
    district_name: str
    reference_period: ClimateTimeSeriesReferencePeriod
    reference_mean: float
    data: List[ClimateTimeSeriesPoint]


class DistrictClimate(BaseModel):
    """Full climate data for a single district"""
    district_id: str
    district_name: str
    region: str
    climate: Dict[str, Dict[str, float]]
    grid_point_count: Optional[int] = None
    grid_resolution_km: Optional[float] = None
