"""
Extract the ocean coastline from the district polygons for the sea level map.

The coast is derived from the geometry itself rather than a hand-maintained
list of district names:

1. Every district edge is indexed by the districts that use it. Edges used by
   exactly one district lie on the national outline (or on a tiny topology gap
   between neighbouring districts).
2. Starting at the southernmost outline vertex (Cape Three Points), the outline
   is walked west to the Ghana/Cote d'Ivoire coastal border point and east to
   the Ghana/Togo coastal border point. Only that arc is ocean coast; the rest
   of the outline is an international land border. Topology gaps form separate
   tiny rings that the walk never visits.
3. Each coastal edge is attributed to the district that owns it.

Outputs (all generated - do not edit by hand):
  - frontend  src/assets/ghana_coastline_segments.geojson  (map overlay)
  - frontend  src/data/coastalDistricts.ts                  (coastal district IDs)
  - backend   app/data/processed/coastal_districts.json      (used by the importer)

Usage:
    python scripts/extract_coastline.py [--frontend-dir ../ghclimateatlas-frontend]
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = BACKEND_ROOT / "app" / "data" / "processed"
INPUT_PATH = PROCESSED_DIR / "districts.geojson"
COASTAL_DISTRICTS_JSON = PROCESSED_DIR / "coastal_districts.json"
DEFAULT_FRONTEND_DIR = BACKEND_ROOT.parent / "ghclimateatlas-frontend"

# Where the coastline meets the land borders, as (lon, lat). The nearest
# outline vertex is used, so these only need to be approximately right.
WEST_COAST_END = (-3.1019, 5.0897)  # Ghana / Cote d'Ivoire, west of Newtown
EAST_COAST_END = (1.1995, 6.1127)  # Ghana / Togo, Aflao
# A coast end must snap to an outline vertex within this distance (degrees)
MAX_SNAP_DISTANCE = 0.01

KEY_PRECISION = 6


def vertex_key(coord) -> tuple[float, float]:
    return (round(coord[0], KEY_PRECISION), round(coord[1], KEY_PRECISION))


def edge_key(a, b) -> tuple:
    return (a, b) if a <= b else (b, a)


def iter_rings(geometry):
    if geometry["type"] == "Polygon":
        yield from geometry["coordinates"]
    elif geometry["type"] == "MultiPolygon":
        for polygon in geometry["coordinates"]:
            yield from polygon


def haversine_km(a, b) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def build_outline(districts):
    """Return (adjacency of outline vertices, owner of each outline edge)."""
    edge_owners = defaultdict(set)
    for feature in districts["features"]:
        district_id = feature["properties"]["id"]
        for ring in iter_rings(feature["geometry"]):
            for i in range(len(ring) - 1):
                a, b = vertex_key(ring[i]), vertex_key(ring[i + 1])
                if a != b:
                    edge_owners[edge_key(a, b)].add(district_id)

    adjacency = defaultdict(list)
    outline_owner = {}
    for key, owners in edge_owners.items():
        if len(owners) != 1:
            continue
        a, b = key
        adjacency[a].append(b)
        adjacency[b].append(a)
        outline_owner[key] = next(iter(owners))
    return adjacency, outline_owner


def snap_to_outline(adjacency, target):
    vertex = min(adjacency, key=lambda p: (p[0] - target[0]) ** 2 + (p[1] - target[1]) ** 2)
    distance = math.dist(vertex, target)
    if distance > MAX_SNAP_DISTANCE:
        raise SystemExit(f"Coast end {target} is {distance:.4f} deg from the outline; update the constant.")
    return vertex


def walk_outline(adjacency, start, first_step, stop):
    """Follow the outline from start via first_step until reaching stop."""
    path = [start, first_step]
    previous, current = start, first_step
    while current != stop:
        neighbours = adjacency[current]
        if len(neighbours) != 2:
            raise SystemExit(f"Outline branches at {current}; cannot follow the coast unambiguously.")
        previous, current = current, neighbours[0] if neighbours[1] == previous else neighbours[1]
        path.append(current)
        if current == start:
            raise SystemExit(f"Walked the whole outline without reaching {stop}.")
    return path


def split_by_owner(path, outline_owner):
    """Split a vertex path into consecutive runs of [district_id, [vertices]]."""
    runs = []
    for a, b in zip(path, path[1:]):
        owner = outline_owner[edge_key(a, b)]
        if runs and runs[-1][0] == owner:
            runs[-1][1].append(b)
        else:
            runs.append([owner, [a, b]])
    return runs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--frontend-dir", type=Path, default=DEFAULT_FRONTEND_DIR)
    args = parser.parse_args()

    coastline_path = args.frontend_dir / "src" / "assets" / "ghana_coastline_segments.geojson"
    frontend_ids_path = args.frontend_dir / "src" / "data" / "coastalDistricts.ts"
    if not coastline_path.parent.is_dir() or not frontend_ids_path.parent.is_dir():
        raise SystemExit(f"Frontend directory not found: {args.frontend_dir}")

    with INPUT_PATH.open("r", encoding="utf-8") as handle:
        districts = json.load(handle)
    props_by_id = {f["properties"]["id"]: f["properties"] for f in districts["features"]}

    adjacency, outline_owner = build_outline(districts)
    print(f"Outline edges: {len(outline_owner)}")

    west_end = snap_to_outline(adjacency, WEST_COAST_END)
    east_end = snap_to_outline(adjacency, EAST_COAST_END)
    # Cape Three Points: the southernmost vertex is always on the coast
    south = min(adjacency, key=lambda p: p[1])
    west_step, east_step = sorted(adjacency[south])  # sorted by longitude

    westward = walk_outline(adjacency, south, west_step, west_end)
    eastward = walk_outline(adjacency, south, east_step, east_end)
    coast = westward[::-1] + eastward[1:]  # west -> east

    runs = split_by_owner(coast, outline_owner)

    lines_by_district = defaultdict(list)
    order = []
    for district_id, vertices in runs:
        if district_id not in lines_by_district:
            order.append(district_id)
        lines_by_district[district_id].append([list(v) for v in vertices])

    features = []
    coastal_districts = []
    for district_id in order:
        lines = lines_by_district[district_id]
        props = props_by_id[district_id]
        length_km = sum(haversine_km(a, b) for line in lines for a, b in zip(line, line[1:]))
        geometry = (
            {"type": "LineString", "coordinates": lines[0]}
            if len(lines) == 1
            else {"type": "MultiLineString", "coordinates": lines}
        )
        features.append({
            "type": "Feature",
            "properties": {
                "district_id": district_id,
                "district_name": props["name"],
                "region": props["region"],
            },
            "geometry": geometry,
        })
        coastal_districts.append({
            "id": district_id,
            "name": props["name"],
            "region": props["region"],
            "coast_length_km": round(length_km, 2),
        })
        print(f"  {props['name']:<32} {district_id:<16} {length_km:7.2f} km  parts={len(lines)}")

    total_km = sum(d["coast_length_km"] for d in coastal_districts)
    print(f"Coastal districts: {len(coastal_districts)}, coastline length: {total_km:.1f} km")

    with coastline_path.open("w", encoding="utf-8") as handle:
        json.dump({"type": "FeatureCollection", "features": features}, handle, separators=(",", ":"))
    print(f"Wrote {coastline_path} ({coastline_path.stat().st_size / 1024:.1f} KB)")

    with COASTAL_DISTRICTS_JSON.open("w", encoding="utf-8") as handle:
        json.dump(coastal_districts, handle, indent=2)
        handle.write("\n")
    print(f"Wrote {COASTAL_DISTRICTS_JSON}")

    id_lines = "\n".join(f'  "{d["id"]}", // {d["name"]}' for d in coastal_districts)
    frontend_ids_path.write_text(
        "// Generated by ghclimateatlas-backend/scripts/extract_coastline.py - do not edit by hand.\n"
        "// Districts whose boundary touches the ocean coastline, ordered west to east.\n"
        f"export const COASTAL_DISTRICT_IDS: readonly string[] = [\n{id_lines}\n];\n",
        encoding="utf-8",
    )
    print(f"Wrote {frontend_ids_path}")


if __name__ == "__main__":
    main()
