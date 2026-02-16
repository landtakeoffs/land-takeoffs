"""Fetch parcel data from Greenville County GIS ArcGIS REST API.

Endpoints used:
- QueryLayers_JS/MapServer/0  — parcel polygons with attributes
- GVL_COMPOSITE_LOC/GeocodeServer — address geocoding

No API key required. Free public data.
"""

import logging
import requests

logger = logging.getLogger(__name__)

PARCEL_URL = (
    "https://www.gcgis.org/arcgis/rest/services/"
    "GreenvilleJS/QueryLayers_JS/MapServer/0/query"
)

GEOCODE_URL = (
    "https://www.gcgis.org/arcgis/rest/services/"
    "GVL_COMPOSITE_LOC/GeocodeServer/findAddressCandidates"
)

# Fields we care about
PARCEL_FIELDS = [
    "PIN", "OWNAM1", "OWNAM2", "NAMECO", "LOCATE", "STRNUM",
    "SUBDIV", "GIS_ACRES", "TACRES", "LANDVAL", "BLDGVAL",
    "TAXMKTVAL", "FAIRMKTVAL", "LANDUSE", "ZONECD", "TOTTAX",
    "SLPRICE", "DEEDTE", "CITY", "STATE", "ZIP5",
    "SHEET", "BLOCK", "LOT", "DESCR",
]


def search_parcels(query: str, field: str = "auto", max_results: int = 25) -> dict:
    """Search parcels by PIN, owner name, address/street, or subdivision.

    Args:
        query: Search string
        field: One of 'pin', 'owner', 'address', 'subdivision', 'auto'
        max_results: Max features to return

    Returns:
        dict with 'features' list of parcel attributes
    """
    if field == "auto":
        field = _detect_field(query)

    where = _build_where(query, field)
    logger.info("GCGIS parcel query: %s (field=%s)", where, field)

    params = {
        "where": where,
        "outFields": ",".join(PARCEL_FIELDS),
        "returnGeometry": "true",
        "outSR": "4326",  # WGS84 lat/lon
        "resultRecordCount": max_results,
        "f": "json",
    }

    resp = requests.get(PARCEL_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    if "error" in data:
        raise ValueError(f"GCGIS error: {data['error'].get('message', data['error'])}")

    features = []
    for f in data.get("features", []):
        attr = f.get("attributes", {})
        geom = f.get("geometry", {})
        # Convert rings to GeoJSON-style coordinates
        if geom and "rings" in geom:
            attr["_geometry"] = {
                "type": "Polygon",
                "coordinates": geom["rings"],
            }
        features.append(attr)

    return {"count": len(features), "field": field, "features": features}


def get_parcel_by_pin(pin: str) -> dict:
    """Get a single parcel by exact PIN with geometry."""
    params = {
        "where": f"PIN='{pin}'",
        "outFields": ",".join(PARCEL_FIELDS),
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "json",
    }
    resp = requests.get(PARCEL_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    features = data.get("features", [])
    if not features:
        raise ValueError(f"No parcel found for PIN: {pin}")

    f = features[0]
    attr = f.get("attributes", {})
    geom = f.get("geometry", {})
    if geom and "rings" in geom:
        attr["_geometry"] = {
            "type": "Polygon",
            "coordinates": geom["rings"],
        }
    return attr


def geocode_address(address: str, max_results: int = 5) -> list:
    """Geocode an address using GCGIS geocoder."""
    params = {
        "SingleLine": address,
        "maxLocations": max_results,
        "outSR": "4326",
        "f": "json",
    }
    resp = requests.get(GEOCODE_URL, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    results = []
    for c in data.get("candidates", []):
        results.append({
            "address": c.get("address", ""),
            "score": c.get("score", 0),
            "lat": c.get("location", {}).get("y"),
            "lon": c.get("location", {}).get("x"),
        })
    return results


def _detect_field(query: str) -> str:
    """Auto-detect which field to search based on query pattern."""
    q = query.strip()
    # PIN pattern: digits with possible dashes, 10-13 chars
    digits = q.replace("-", "").replace(" ", "")
    if digits.isdigit() and len(digits) >= 10:
        return "pin"
    # If it starts with a number, probably an address
    if q and q[0].isdigit():
        return "address"
    # Default: search all fields
    return "all"


def _build_where(query: str, field: str) -> str:
    """Build SQL WHERE clause for ArcGIS query."""
    q = query.strip().upper().replace("'", "''")

    if field == "pin":
        clean = q.replace("-", "").replace(" ", "")
        return f"PIN='{clean}'"
    elif field == "owner":
        return f"OWNAM1 LIKE '%{q}%' OR OWNAM2 LIKE '%{q}%' OR NAMECO LIKE '%{q}%'"
    elif field == "subdivision":
        return f"SUBDIV LIKE '%{q}%'"
    elif field == "address":
        return f"LOCATE LIKE '%{q}%'"
    elif field == "all":
        return (
            f"LOCATE LIKE '%{q}%' OR OWNAM1 LIKE '%{q}%' OR "
            f"OWNAM2 LIKE '%{q}%' OR NAMECO LIKE '%{q}%' OR "
            f"SUBDIV LIKE '%{q}%' OR DESCR LIKE '%{q}%'"
        )
    else:
        return (
            f"LOCATE LIKE '%{q}%' OR OWNAM1 LIKE '%{q}%' OR "
            f"SUBDIV LIKE '%{q}%'"
        )
