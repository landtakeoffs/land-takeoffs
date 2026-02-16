"""Flask API for civil engineering site analysis."""

import logging
from flask import Flask, jsonify, request
from flask_cors import CORS

from config import config
from data_fetchers.gcgis_fetcher import search_parcels, get_parcel_by_pin, geocode_address

# Lazy imports for heavy modules (scipy, numpy) — only loaded when needed
ParcelFetcher = None
ElevationFetcher = None
TerrainAnalyzer = None

def _load_heavy_modules():
    global ElevationFetcher, TerrainAnalyzer
    if TerrainAnalyzer is None:
        from data_fetchers.elevation_fetcher import ElevationFetcher as _EF
        from analysis.terrain_analysis import TerrainAnalyzer as _TA
        ElevationFetcher = _EF
        TerrainAnalyzer = _TA

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["SECRET_KEY"] = config.SECRET_KEY
app.json.sort_keys = False  # preserve dict key order
CORS(app)


@app.route("/api/debug", methods=["GET"])
def debug_check():
    """Test heavy module loading."""
    issues = []
    try:
        import numpy as np
        issues.append(f"numpy OK: {np.__version__}")
    except Exception as e:
        issues.append(f"numpy FAIL: {e}")
    try:
        from scipy import ndimage
        issues.append("scipy.ndimage OK")
    except Exception as e:
        issues.append(f"scipy FAIL: {e}")
    try:
        _load_heavy_modules()
        issues.append(f"heavy modules OK: EF={ElevationFetcher}, TA={TerrainAnalyzer}")
    except Exception as e:
        issues.append(f"heavy modules FAIL: {e}")
    
    # Check API keys and rasterio
    issues.append(f"OPENTOPO_API_KEY: {'SET' if config.OPENTOPO_API_KEY else 'MISSING'}")
    issues.append(f"OPENTOPOGRAPHY_API_KEY: {'SET' if config.OPENTOPOGRAPHY_API_KEY else 'MISSING'}")
    try:
        from data_fetchers.elevation_fetcher import HAS_RASTERIO, HAS_PILLOW
        issues.append(f"rasterio: {'AVAILABLE' if HAS_RASTERIO else 'NOT_AVAILABLE'}")
        issues.append(f"pillow: {'AVAILABLE' if HAS_PILLOW else 'NOT_AVAILABLE'}")
    except Exception as e:
        issues.append(f"image library check FAILED: {e}")
    
    return jsonify({"checks": issues})


@app.route("/api/health", methods=["GET"])
def health():
    """Health-check endpoint."""
    issues = config.validate()
    return jsonify({"status": "ok" if not issues else "degraded", "issues": issues})


@app.route("/api/analyze", methods=["POST"])
def analyze():
    _load_heavy_modules()
    """Run the full analysis pipeline for a parcel.

    Expects JSON body::

        {
            "tax_id": "123-456-789",
            "max_slope": 15,          // optional
            "buffer_distance": 0.001  // optional
        }
    """
    data = request.get_json(force=True)
    tax_id: str = data.get("tax_id", "").strip()
    if not tax_id:
        return jsonify({"error": "tax_id is required"}), 400

    max_slope = float(data.get("max_slope", config.MAX_BUILDABLE_SLOPE))
    buffer_distance = float(data.get("buffer_distance", 0.001))

    try:
        # 1. Fetch parcel geometry
        parcel_fetcher = ParcelFetcher()
        parcel_gdf = parcel_fetcher.fetch_by_tax_id(tax_id)
        issues = ParcelFetcher.validate_parcel_data(parcel_gdf)
        if issues:
            logger.warning("Parcel validation issues: %s", issues)

        bounds = tuple(parcel_gdf.total_bounds)  # (minx, miny, maxx, maxy)

        # 2. Fetch elevation data
        elev_fetcher = ElevationFetcher()
        elevation, profile = elev_fetcher.fetch_dem_for_parcel(
            bounds=bounds,
            buffer_distance=buffer_distance,
        )
        elev_stats = ElevationFetcher.calculate_elevation_statistics(elevation)

        # 3. Terrain analysis — convert degrees to meters
        import math
        deg_size = abs(profile.get("transform", [1])[0])
        mid_lat = (bounds[1] + bounds[3]) / 2.0
        cell_size = deg_size * 111320 * math.cos(math.radians(mid_lat))
        analyzer = TerrainAnalyzer(elevation, cell_size=cell_size)
        slope = analyzer.calculate_slope()
        buildable = analyzer.identify_buildable_areas(max_slope=max_slope)
        optimal_elev = analyzer.find_optimal_pad_elevation(buildable)
        cut_fill = analyzer.calculate_cut_fill_volumes(optimal_elev, buildable)

        result = {
            "tax_id": tax_id,
            "parcel_bounds": list(bounds),
            "elevation_stats": elev_stats,
            "slope_stats": {
                "min": float(slope.min()),
                "max": float(slope.max()),
                "mean": float(slope.mean()),
            },
            "buildable_pct": round(100.0 * buildable.sum() / buildable.size, 2),
            "optimal_pad_elevation": optimal_elev,
            "cut_fill": cut_fill,
            "validation_issues": issues,
        }
        return jsonify(result)

    except ValueError as exc:
        logger.error("Analysis error: %s", exc)
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        logger.exception("Unexpected error during analysis")
        return jsonify({"error": "Internal server error", "detail": str(exc)}), 500


@app.route("/api/analyze-coords", methods=["POST"])
def analyze_coords():
    _load_heavy_modules()
    """Analyze terrain for a bounding box (no parcel lookup needed).

    Expects JSON body::

        {
            "south": 35.05,
            "north": 35.06,
            "west": -82.45,
            "east": -82.44,
            "max_slope": 15
        }
    """
    data = request.get_json(force=True)
    required = ["south", "north", "west", "east"]
    missing = [k for k in required if k not in data]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400

    south, north = float(data["south"]), float(data["north"])
    west, east = float(data["west"]), float(data["east"])
    max_slope = float(data.get("max_slope", config.MAX_BUILDABLE_SLOPE))

    try:
        bounds = (west, south, east, north)

        # Fetch elevation
        elev_fetcher = ElevationFetcher()
        elevation, profile = elev_fetcher.fetch_dem_for_parcel(
            bounds=bounds, buffer_distance=0.0005
        )
        elev_stats = ElevationFetcher.calculate_elevation_statistics(elevation)

        # Terrain analysis — convert cell size from degrees to meters
        import math
        deg_size = abs(profile.get("transform", [1])[0])
        mid_lat = (south + north) / 2.0
        cell_size_m = deg_size * 111320 * math.cos(math.radians(mid_lat))
        analyzer = TerrainAnalyzer(elevation, cell_size=cell_size_m)
        slope = analyzer.calculate_slope()
        buildable = analyzer.identify_buildable_areas(max_slope=max_slope)
        optimal_elev = analyzer.find_optimal_pad_elevation(buildable)
        cut_fill = analyzer.calculate_cut_fill_volumes(optimal_elev, buildable)

        return jsonify({
            "bounds": list(bounds),
            "elevation_stats": elev_stats,
            "slope_stats": {
                "min": float(slope.min()),
                "max": float(slope.max()),
                "mean": float(slope.mean()),
            },
            "buildable_pct": round(100.0 * buildable.sum() / buildable.size, 2),
            "optimal_pad_elevation": optimal_elev,
            "cut_fill": cut_fill,
        })
    except Exception as exc:
        logger.exception("Error in coordinate analysis")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/estimate/template", methods=["GET"])
def get_estimate_template():
    """Return default sections and unit prices for the estimate form."""
    from unit_prices import DEFAULT_SECTIONS
    return jsonify(DEFAULT_SECTIONS)


@app.route("/api/estimate/generate", methods=["POST"])
def generate_estimate_post():
    """Generate an estimate workbook from user-provided data.

    Expects JSON::
        {
            "project_name": "Pennington Ridge",
            "sections": { ... }   // same shape as DEFAULT_SECTIONS with user Qty values
        }
    Returns the file as a download.
    """
    import io
    from estimate_workbook import generate_workbook
    from unit_prices import DEFAULT_SECTIONS

    data = request.get_json(force=True)
    project_name = data.get("project_name", "Untitled Project")
    sections = data.get("sections", DEFAULT_SECTIONS)

    # Generate to memory buffer
    output_path = f"/tmp/{project_name.replace(' ', '_')}_Estimate.xlsx"
    generate_workbook(output_path=output_path, project_name=project_name, sections=sections)

    from flask import send_file
    return send_file(output_path, as_attachment=True,
                     download_name=f"{project_name.replace(' ', '_')}_Estimate.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/api/estimate", methods=["POST"])
def generate_estimate():
    """Quick estimate with defaults. Returns download."""
    from estimate_workbook import generate_workbook
    from unit_prices import DEFAULT_SECTIONS
    output_path = "/tmp/Quick_Estimate.xlsx"
    generate_workbook(output_path=output_path, project_name="Quick Estimate", sections=DEFAULT_SECTIONS)
    from flask import send_file
    return send_file(output_path, as_attachment=True,
                     download_name="Quick_Estimate.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/api/parcels/search", methods=["GET"])
def parcel_search():
    """Search Greenville County parcels.

    Query params:
        q: search string (required)
        field: pin|owner|address|subdivision|auto (default: auto)
        limit: max results (default: 25)
    """
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "q parameter required"}), 400

    field = request.args.get("field", "auto")
    limit = min(int(request.args.get("limit", 25)), 100)

    try:
        result = search_parcels(q, field=field, max_results=limit)
        return jsonify(result)
    except Exception as exc:
        logger.exception("Parcel search error")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/parcels/<pin>", methods=["GET"])
def parcel_detail(pin):
    """Get a single parcel by PIN with geometry."""
    try:
        parcel = get_parcel_by_pin(pin)
        return jsonify(parcel)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        logger.exception("Parcel detail error")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/parcels/identify", methods=["GET"])
def parcel_identify():
    """Identify parcel at a clicked point (proxies GCGIS identify endpoint).

    Query params:
        lat, lon: click coordinates
        zoom: current map zoom level
        width, height: map container size in pixels
        sw_lat, sw_lon, ne_lat, ne_lon: map bounds
    """
    import requests as req

    lat = request.args.get("lat")
    lon = request.args.get("lon")
    if not lat or not lon:
        return jsonify({"error": "lat and lon required"}), 400

    sw_lat = request.args.get("sw_lat", "34.5")
    sw_lon = request.args.get("sw_lon", "-82.8")
    ne_lat = request.args.get("ne_lat", "35.2")
    ne_lon = request.args.get("ne_lon", "-82.0")
    width = request.args.get("width", "1000")
    height = request.args.get("height", "600")

    identify_url = (
        "https://www.gcgis.org/arcgis/rest/services/"
        "GreenvilleJS/QueryLayers_JS/MapServer/identify"
    )
    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "sr": "4326",
        "layers": "all:0",
        "tolerance": "3",
        "mapExtent": f"{sw_lon},{sw_lat},{ne_lon},{ne_lat}",
        "imageDisplay": f"{width},{height},96",
        "returnGeometry": "true",
        "returnFieldName": "true",
        "f": "json",
    }

    try:
        resp = req.get(identify_url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        results = []
        for r in data.get("results", []):
            attr = r.get("attributes", {})
            geom = r.get("geometry", {})
            if geom and "rings" in geom:
                attr["_geometry"] = {"type": "Polygon", "coordinates": geom["rings"]}
            results.append(attr)

        return jsonify({"count": len(results), "features": results})
    except Exception as exc:
        logger.exception("Identify error")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/geocode", methods=["GET"])
def geocode():
    """Geocode an address using Greenville County geocoder.

    Query params:
        q: address string
    """
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "q parameter required"}), 400
    try:
        results = geocode_address(q)
        return jsonify({"results": results})
    except Exception as exc:
        logger.exception("Geocode error")
        return jsonify({"error": str(exc)}), 500


@app.route("/", methods=["GET"])
def landing():
    """Serve the landing page."""
    return app.send_static_file("landing.html")


@app.route("/app", methods=["GET"])
def index():
    """Serve the web UI."""
    return app.send_static_file("index.html")


@app.route("/estimate", methods=["GET"])
@app.route("/app/estimate", methods=["GET"])
def estimate_page():
    """Serve the estimate builder UI."""
    return app.send_static_file("estimate.html")


@app.route("/concept-plan", methods=["GET"])
@app.route("/app/concept-plan", methods=["GET"])
def concept_plan_page():
    """Serve the concept plan generator."""
    return app.send_static_file("concept-plan.html")


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
