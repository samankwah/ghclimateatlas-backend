"""
Extract coastline segments from district polygons for sea level rise visualization.

Identifies ocean-facing edges of coastal districts (edges not shared with any
other district) and outputs them as a GeoJSON FeatureCollection of LineStrings
segmented by district.

Usage:
    python backend/scripts/extract_coastline.py
"""

import json
import os
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))

INPUT_PATH = os.path.join(PROJECT_ROOT, "backend", "app", "data", "processed", "districts.geojson")
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "frontend", "src", "assets", "ghana_coastline_segments.geojson")

# Coastal districts — names must match the GeoJSON exactly
COASTAL_DISTRICTS = {
    "Accra",
    "Tema",
    "Tema West",
    "Kpone-Katamanso",
    "Ada East",
    "Ada West",
    "Ningo-Prampram",
    "Shai Osudoku",
    "Krowor",
    "Ledzokuku",
    "La-Dade-Kotopon",
    "Ga South",
    "Sekondi Takoradi",
    "Effia Kwesimintsim",
    "Shama",
    "Ahanta West",
    "Ellembelle",
    "Jomoro",
    "Nzema East",
    "Cape Coast",
    "Komenda-Edina-Eguafo-Abirem-",
    "Mfantseman",
    "Ekumfi",
    "Gomoa West",
    "Gomoa East",
    "Effutu",
    "Awutu Senya East",
    "Awutu Senya West",
    "Keta Municipal",
    "Ketu South",
    "South Tongu",
}

# Maximum latitude for coastline edges — edges above this are inland boundaries
MAX_COAST_LAT = 6.2


def round_coord(c, precision=6):
    """Round a coordinate to given decimal places for matching."""
    return (round(c[0], precision), round(c[1], precision))


def make_edge_key(a, b):
    """Create a canonical edge key (sorted tuple) for deduplication."""
    return tuple(sorted([a, b]))


def extract_rings(geometry):
    """Extract all outer rings from a Polygon or MultiPolygon geometry."""
    if geometry["type"] == "Polygon":
        return [geometry["coordinates"][0]]
    elif geometry["type"] == "MultiPolygon":
        return [poly[0] for poly in geometry["coordinates"]]
    return []


def main():
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        districts = json.load(f)

    # Build edge index: for each edge, track which districts share it
    # edge_key -> set of district names
    edge_owners = defaultdict(set)
    # Also track original (non-rounded) coordinates per edge per district
    edge_coords = {}  # edge_key -> (original_a, original_b)
    # District properties lookup
    district_props = {}

    for feat in districts["features"]:
        props = feat["properties"]
        name = props["name"]
        district_props[name] = {
            "district_id": props["id"],
            "district_name": name,
            "region": props["region"],
        }

        rings = extract_rings(feat["geometry"])
        for ring in rings:
            for i in range(len(ring) - 1):
                a_raw = ring[i]
                b_raw = ring[i + 1]
                a = round_coord(a_raw)
                b = round_coord(b_raw)
                key = make_edge_key(a, b)
                edge_owners[key].add(name)
                if key not in edge_coords:
                    edge_coords[key] = (a_raw[:2], b_raw[:2])

    print(f"Total edges indexed: {len(edge_owners)}")

    # For each coastal district, collect edges that are:
    # 1. Owned by exactly one district (not shared = ocean boundary)
    # 2. Below MAX_COAST_LAT latitude threshold
    coastal_edges = defaultdict(list)  # district_name -> list of (coord_a, coord_b)

    for key, owners in edge_owners.items():
        if len(owners) != 1:
            continue
        owner = next(iter(owners))
        if owner not in COASTAL_DISTRICTS:
            continue

        a_raw, b_raw = edge_coords[key]
        # Both endpoints must be below the latitude threshold
        if a_raw[1] > MAX_COAST_LAT or b_raw[1] > MAX_COAST_LAT:
            continue

        coastal_edges[owner].append((a_raw, b_raw))

    print(f"Coastal districts with edges: {len(coastal_edges)}")
    for name, edges in sorted(coastal_edges.items()):
        print(f"  {name}: {len(edges)} edges")

    # Merge consecutive edges into polylines per district
    features = []
    for name in sorted(coastal_edges.keys()):
        edges = coastal_edges[name]
        if not edges:
            continue

        lines = merge_edges_into_lines(edges)
        props = district_props.get(name, {
            "district_id": name,
            "district_name": name,
            "region": "Unknown",
        })

        if len(lines) == 1:
            geometry = {
                "type": "LineString",
                "coordinates": lines[0],
            }
        else:
            geometry = {
                "type": "MultiLineString",
                "coordinates": lines,
            }

        features.append({
            "type": "Feature",
            "properties": props,
            "geometry": geometry,
        })

    geojson = {
        "type": "FeatureCollection",
        "features": features,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(geojson, f)

    file_size = os.path.getsize(OUTPUT_PATH)
    print(f"\nOutput: {OUTPUT_PATH}")
    print(f"Features: {len(features)}, Size: {file_size / 1024:.1f} KB")


def merge_edges_into_lines(edges):
    """
    Merge a list of (a, b) edge pairs into connected polylines.
    Returns a list of coordinate lists (each is a line).
    """
    if not edges:
        return []

    # Build adjacency: point -> list of connected points
    adjacency = defaultdict(list)
    for a, b in edges:
        ak = (round(a[0], 6), round(a[1], 6))
        bk = (round(b[0], 6), round(b[1], 6))
        adjacency[ak].append((bk, a, b))
        adjacency[bk].append((ak, b, a))

    visited_edges = set()
    lines = []

    for a, b in edges:
        ak = (round(a[0], 6), round(a[1], 6))
        bk = (round(b[0], 6), round(b[1], 6))
        ekey = make_edge_key(ak, bk)
        if ekey in visited_edges:
            continue

        # Start a new line from this edge
        line = [list(a), list(b)]
        visited_edges.add(ekey)

        # Extend forward from b
        current = bk
        while True:
            neighbors = adjacency[current]
            found = False
            for (nk, orig_from, orig_to) in neighbors:
                ek = make_edge_key(current, nk)
                if ek not in visited_edges:
                    visited_edges.add(ek)
                    line.append(list(orig_to))
                    current = nk
                    found = True
                    break
            if not found:
                break

        # Extend backward from a
        current = ak
        while True:
            neighbors = adjacency[current]
            found = False
            for (nk, orig_from, orig_to) in neighbors:
                ek = make_edge_key(current, nk)
                if ek not in visited_edges:
                    visited_edges.add(ek)
                    line.insert(0, list(orig_to))
                    current = nk
                    found = True
                    break
            if not found:
                break

        lines.append(line)

    return lines


if __name__ == "__main__":
    main()
