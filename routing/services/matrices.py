import os

import requests


def travel_matrix(items, mode):
    base = os.getenv("VALHALLA_URL", "").rstrip("/")
    if not base or not items:
        return None
    locations = [{"lat": item["latitude"], "lon": item["longitude"]} for item in items]
    response = requests.post(f"{base}/sources_to_targets", json={"sources": locations, "targets": locations, "costing": "pedestrian" if mode == "walking" else "auto"}, timeout=90)
    response.raise_for_status()
    matrix = response.json().get("sources_to_targets")
    if not matrix or len(matrix) != len(items):
        raise ValueError("Valhalla returned an invalid travel-time matrix.")
    return [[cell.get("time") if cell else None for cell in row] for row in matrix]
