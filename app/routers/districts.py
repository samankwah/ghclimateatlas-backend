"""
Districts API endpoints
Serves Ghana district boundaries and metadata
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
import json
from pathlib import Path

from app.models.schemas import (
    District,
    DistrictGeoJSON,
    DistrictFeatureCollection,
    DistrictClimate,
)
from app.data.mock_data import (
    REGIONS,
    generate_district_id,
    generate_all_districts,
    get_district_climate_data,
)

router = APIRouter()

# Ghana bounding box coordinates (approximate)
GHANA_BOUNDS = {
    "min_lat": 3.3,
    "max_lat": 11.2,
    "min_lng": -3.3,
    "max_lng": 1.2,
}

# Generate simple polygon for each district (placeholder - replace with real GeoJSON)
def calculate_centroid(coordinates: list) -> list:
    """Calculate the centroid of a polygon from its coordinates."""
    # For simple polygons, use the average of all vertices
    # coordinates[0] is the outer ring
    ring = coordinates[0]
    # Exclude the closing point (which duplicates the first)
    points = ring[:-1] if ring[0] == ring[-1] else ring

    if not points:
        return [0, 0]

    centroid_lon = sum(p[0] for p in points) / len(points)
    centroid_lat = sum(p[1] for p in points) / len(points)

    return [centroid_lon, centroid_lat]


def generate_district_geometry(region: str, district_index: int, total_in_region: int):
    """Generate a simple rectangular geometry for a district (placeholder)"""
    # This creates mock geometries - replace with real GeoJSON boundaries
    region_centers = {
        "Greater Accra": (5.6, -0.2),
        "Ashanti": (6.7, -1.6),
        "Western": (5.0, -2.0),
        "Central": (5.5, -1.2),
        "Eastern": (6.3, -0.5),
        "Volta": (6.5, 0.5),
        "Northern": (9.5, -1.0),
        "Upper East": (10.8, -0.8),
        "Upper West": (10.3, -2.3),
        "Bono": (7.5, -2.3),
        "Bono East": (7.8, -1.5),
        "Ahafo": (7.0, -2.5),
        "Western North": (6.2, -2.5),
        "Oti": (7.8, 0.3),
        "North East": (10.2, -0.2),
        "Savannah": (9.0, -1.8),
    }

    center = region_centers.get(region, (7.5, -1.0))
    lat, lng = center

    # Create small offset based on district index
    row = district_index // 4
    col = district_index % 4
    offset_lat = row * 0.3 - 0.3
    offset_lng = col * 0.3 - 0.3

    # Create a small polygon
    size = 0.12
    base_lat = lat + offset_lat
    base_lng = lng + offset_lng

    return {
        "type": "Polygon",
        "coordinates": [[
            [base_lng - size, base_lat - size],
            [base_lng + size, base_lat - size],
            [base_lng + size, base_lat + size],
            [base_lng - size, base_lat + size],
            [base_lng - size, base_lat - size],
        ]]
    }


@router.get("", response_model=DistrictFeatureCollection)
async def get_all_districts(region: Optional[str] = Query(None, description="Filter by region name")):
    """
    Get all Ghana districts as GeoJSON FeatureCollection.
    Optionally filter by region.
    """
    features = []

    for region_name, district_list in REGIONS.items():
        if region and region.lower() != region_name.lower():
            continue

        for idx, district_name in enumerate(district_list):
            district_id = generate_district_id(region_name, district_name)
            geometry = generate_district_geometry(region_name, idx, len(district_list))
            centroid = calculate_centroid(geometry["coordinates"])

            feature = {
                "type": "Feature",
                "properties": {
                    "id": district_id,
                    "name": district_name,
                    "region": region_name,
                    "centroid": centroid,
                },
                "geometry": geometry,
            }
            features.append(feature)

    return {"type": "FeatureCollection", "features": features}


@router.get("/list", response_model=List[District])
async def list_districts(region: Optional[str] = Query(None, description="Filter by region name")):
    """
    Get list of all districts (without geometry).
    """
    districts = generate_all_districts()

    if region:
        districts = [d for d in districts if d["region"].lower() == region.lower()]

    return districts


@router.get("/regions")
async def get_regions():
    """
    Get list of all Ghana regions with district counts.
    """
    return [
        {"name": region, "district_count": len(districts)}
        for region, districts in REGIONS.items()
    ]


@router.get("/{district_id}", response_model=DistrictGeoJSON)
async def get_district(district_id: str):
    """
    Get a single district by ID.
    """
    for region_name, district_list in REGIONS.items():
        for idx, district_name in enumerate(district_list):
            d_id = generate_district_id(region_name, district_name)
            if d_id == district_id:
                geometry = generate_district_geometry(region_name, idx, len(district_list))
                centroid = calculate_centroid(geometry["coordinates"])
                return {
                    "type": "Feature",
                    "properties": {
                        "id": d_id,
                        "name": district_name,
                        "region": region_name,
                        "centroid": centroid,
                    },
                    "geometry": geometry,
                }

    raise HTTPException(status_code=404, detail=f"District {district_id} not found")


@router.get("/{district_id}/climate", response_model=DistrictClimate)
async def get_district_climate(district_id: str):
    """
    Get full climate data for a specific district.
    """
    for region_name, district_list in REGIONS.items():
        for district_name in district_list:
            d_id = generate_district_id(region_name, district_name)
            if d_id == district_id:
                climate_data = get_district_climate_data(d_id, region_name)
                return {
                    "district_id": d_id,
                    "district_name": district_name,
                    "region": region_name,
                    "climate": climate_data,
                }

    raise HTTPException(status_code=404, detail=f"District {district_id} not found")
