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
    data: List[ClimateComparison]


class DistrictClimate(BaseModel):
    """Full climate data for a single district"""
    district_id: str
    district_name: str
    region: str
    climate: Dict[str, Dict[str, float]]
