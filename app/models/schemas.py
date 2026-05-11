"""
Pydantic schemas for Ghana Climate Atlas API
"""
from pydantic import BaseModel, Field, field_validator
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


class ClimateDataRequest(BaseModel):
    """Operational request for a downloadable climate data package"""
    full_name: str = Field(..., min_length=2, max_length=160)
    email: str = Field(..., min_length=5, max_length=320)
    organization: Optional[str] = Field(default=None, max_length=200)
    purpose: str = Field(..., min_length=3, max_length=1000)
    geography: str = Field(..., min_length=2, max_length=500)
    time_period: str = Field(..., min_length=2, max_length=200)
    climate_variables: List[str] = Field(..., min_length=1, max_length=24)
    scenarios: List[str] = Field(..., min_length=1, max_length=24)
    preferred_format: str = Field(..., min_length=2, max_length=80)
    additional_notes: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        cleaned = value.strip()
        if "@" not in cleaned or "." not in cleaned.rsplit("@", 1)[-1]:
            raise ValueError("Enter a valid email address")
        return cleaned.lower()

    @field_validator(
        "full_name",
        "organization",
        "purpose",
        "geography",
        "time_period",
        "preferred_format",
        "additional_notes",
        mode="before",
    )
    @classmethod
    def strip_optional_text(cls, value):
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        return value

    @field_validator("climate_variables", "scenarios")
    @classmethod
    def validate_non_empty_list_items(cls, value: List[str]) -> List[str]:
        cleaned = [item.strip() for item in value if item and item.strip()]
        if not cleaned:
            raise ValueError("Select at least one option")
        return cleaned


class ClimateDataRequestResponse(BaseModel):
    """Response after receiving a climate data request"""
    request_id: str
    submitted_at: str
    status: str
    email_status: str
    warning: Optional[str] = None
