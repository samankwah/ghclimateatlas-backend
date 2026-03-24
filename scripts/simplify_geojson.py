"""
Create a simplified district GeoJSON for map rendering without mutating the
existing full-detail runtime artifact.

Usage:
    python backend/scripts/simplify_geojson.py

Input:
    backend/app/data/processed/districts.geojson

Output:
    backend/app/data/processed/districts_map.geojson
"""

import json
from pathlib import Path

try:
    from shapely.geometry import shape, mapping
    from shapely.validation import make_valid
except ImportError:
    print("ERROR: shapely is required. Install with: pip install shapely")
    raise SystemExit(1)

TOLERANCE = 0.001  # ~110m at equator — good for choropleth display
PRECISION = 5      # 5 decimal places ≈ 1.1m accuracy

DATA_DIR = Path(__file__).resolve().parents[1] / "app" / "data" / "processed"
GEOJSON_PATH = DATA_DIR / "districts.geojson"
SIMPLIFIED_PATH = DATA_DIR / "districts_map.geojson"


def truncate_coords(coords, precision: int):
    """Recursively truncate coordinate precision."""
    if isinstance(coords[0], (int, float)):
        return [round(c, precision) for c in coords]
    return [truncate_coords(c, precision) for c in coords]


def simplify_feature(feature: dict) -> dict:
    """Simplify a single GeoJSON feature's geometry."""
    geom = shape(feature["geometry"])

    # Ensure valid geometry
    if not geom.is_valid:
        geom = make_valid(geom)

    # Simplify with Douglas-Peucker, preserving topology
    simplified = geom.simplify(TOLERANCE, preserve_topology=True)

    # Convert back to GeoJSON and truncate precision
    geojson_geom = mapping(simplified)
    geojson_geom["coordinates"] = truncate_coords(
        geojson_geom["coordinates"], PRECISION
    )

    return {
        "type": feature["type"],
        "properties": feature["properties"],
        "geometry": geojson_geom,
    }


def main():
    if not GEOJSON_PATH.exists():
        print(f"ERROR: {GEOJSON_PATH} not found")
        raise SystemExit(1)

    original_size = GEOJSON_PATH.stat().st_size
    print(f"Original: {original_size / 1_000_000:.1f} MB")

    # Load and simplify
    with open(GEOJSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    original_count = len(data["features"])
    print(f"Districts: {original_count}")

    simplified_features = []
    for i, feature in enumerate(data["features"]):
        simplified_features.append(simplify_feature(feature))
        if (i + 1) % 50 == 0:
            print(f"  Simplified {i + 1}/{original_count} features...")

    data["features"] = simplified_features

    # Write simplified GeoJSON (compact, no extra whitespace)
    with open(SIMPLIFIED_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))

    new_size = SIMPLIFIED_PATH.stat().st_size
    reduction = (1 - new_size / original_size) * 100
    print(f"\nSimplified: {new_size / 1_000_000:.1f} MB")
    print(f"Reduction: {reduction:.0f}%")
    print(f"Features: {len(data['features'])} (should be {original_count})")
    print(f"Wrote {SIMPLIFIED_PATH}")


if __name__ == "__main__":
    main()
