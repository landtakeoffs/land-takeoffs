"""Flask API for civil engineering site analysis."""

import logging
import json
import os
import smtplib
from datetime import datetime
from pathlib import Path
from email.message import EmailMessage
from flask import Flask, jsonify, request, send_file
from werkzeug.utils import secure_filename
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

UPLOAD_DIR = Path(__file__).parent / "uploads" / "plans"
SUBMISSIONS_DIR = UPLOAD_DIR / "submissions"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
SUBMISSIONS_DIR.mkdir(parents=True, exist_ok=True)


def _smtp_config():
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    smtp_from = os.getenv("SMTP_FROM", smtp_user or "noreply@landtakeoffs.local")
    return smtp_host, smtp_port, smtp_user, smtp_pass, smtp_from


def _send_email(message: EmailMessage) -> tuple[bool, str]:
    smtp_host, smtp_port, smtp_user, smtp_pass, _ = _smtp_config()
    if not smtp_host or not smtp_user or not smtp_pass:
        return False, "SMTP not configured"
    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(message)
        return True, "Email sent"
    except Exception as exc:
        logger.exception("Failed sending email")
        return False, f"Email failed: {exc}"


def _send_plan_intake_email(submission: dict, saved_path: Path) -> tuple[bool, str]:
    """Send intake notification email if SMTP env vars are configured."""
    _, _, _, _, smtp_from = _smtp_config()
    review_to = os.getenv("PLAN_REVIEW_TO", "natejarvisone@gmail.com")

    msg = EmailMessage()
    msg["Subject"] = f"[Plan Upload] {submission.get('project','(No project)')} — {submission.get('name','Unknown')}"
    msg["From"] = smtp_from
    msg["To"] = review_to
    msg.set_content(
        "New civil plan upload received.\n\n"
        f"Submission ID: {submission.get('id','')}\n"
        f"Name: {submission.get('name','')}\n"
        f"Email: {submission.get('email','')}\n"
        f"Phone: {submission.get('phone','')}\n"
        f"Company: {submission.get('company','')}\n"
        f"Project: {submission.get('project','')}\n"
        f"Scope notes: {submission.get('scope','')}\n"
        f"File: {saved_path.name}\n"
        f"Submitted at: {submission.get('submitted_at','')}\n"
    )

    # Attach uploaded PDF for review
    try:
        msg.add_attachment(
            saved_path.read_bytes(),
            maintype="application",
            subtype="pdf",
            filename=saved_path.name,
        )
    except Exception:
        logger.exception("Failed attaching uploaded PDF to intake email")

    return _send_email(msg)


def _send_status_email_to_client(submission: dict, status: str, note: str = "") -> tuple[bool, str]:
    """Notify client when status changes."""
    _, _, _, _, smtp_from = _smtp_config()
    to_email = submission.get("email")
    if not to_email:
        return False, "No client email"

    msg = EmailMessage()
    msg["Subject"] = f"Plan Review Update — {submission.get('project','Your Project')}"
    msg["From"] = smtp_from
    msg["To"] = to_email
    body = (
        f"Hello {submission.get('name','')},\n\n"
        f"Your plan review status is now: {status}.\n"
    )
    if note:
        body += f"\nNote: {note}\n"
    body += "\nThank you,\nLand Takeoffs"
    msg.set_content(body)
    return _send_email(msg)


def _submission_path(submission_id: str) -> Path:
    return SUBMISSIONS_DIR / f"{submission_id}.json"


def _require_admin_token() -> bool:
    expected = os.getenv("ADMIN_TOKEN", "").strip()
    if not expected:
        return True
    provided = request.headers.get("X-Admin-Token", "") or request.args.get("token", "")
    return provided == expected


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


@app.route("/unified", methods=["GET"])
@app.route("/app/unified", methods=["GET"])
def unified_page():
    """Serve the unified estimate + proforma builder UI."""
    return app.send_static_file("unified.html")


@app.route("/concept-plan", methods=["GET"])
@app.route("/app/concept-plan", methods=["GET"])
def concept_plan_page():
    """Serve the concept plan generator."""
    return app.send_static_file("concept-plan.html")


@app.route("/plans-upload", methods=["GET"])
def plans_upload_page():
    """Serve the civil plans upload page."""
    return app.send_static_file("plans-upload.html")


@app.route("/api/plans-upload", methods=["POST"])
def plans_upload_api():
    """Handle plan-upload form submissions and notify reviewer."""
    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    company = (request.form.get("company") or "").strip()
    project = (request.form.get("project") or "").strip()
    scope = (request.form.get("scope") or "").strip()
    file = request.files.get("plans")

    if not name or not email or not project:
        return jsonify({"ok": False, "error": "Missing required fields"}), 400
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "PDF file is required"}), 400

    filename = secure_filename(file.filename)
    if not filename.lower().endswith(".pdf"):
        return jsonify({"ok": False, "error": "Only PDF files are allowed"}), 400

    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    saved_name = f"{ts}_{filename}"
    saved_path = UPLOAD_DIR / saved_name
    file.save(saved_path)

    submission = {
        "id": ts,
        "status": "received",
        "name": name,
        "email": email,
        "phone": phone,
        "company": company,
        "project": project,
        "scope": scope,
        "file": saved_name,
        "submitted_at": datetime.utcnow().isoformat() + "Z",
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "source_ip": request.headers.get("X-Forwarded-For", request.remote_addr),
        "user_agent": request.headers.get("User-Agent", "")
    }

    # Persist intake log (JSONL + per-submission JSON)
    log_path = UPLOAD_DIR / "submissions.jsonl"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(submission) + "\n")
    _submission_path(ts).write_text(json.dumps(submission, indent=2), encoding="utf-8")

    emailed, msg = _send_plan_intake_email(submission, saved_path)

    return jsonify({
        "ok": True,
        "message": "We’ve received your file. You’ll receive an email with the estimate and pro forma within 24 hours from one of our licensed contractors.",
        "emailNotification": emailed,
        "status": msg,
        "submissionId": ts
    })


@app.route("/admin/plan-submissions", methods=["GET"])
def plans_admin_page():
    """Serve admin review page for plan submissions."""
    return app.send_static_file("plans-admin.html")


@app.route("/api/plans-upload/submissions", methods=["GET"])
def plans_upload_submissions_api():
    """List plan upload submissions for admin review."""
    if not _require_admin_token():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    items = []
    for p in sorted(SUBMISSIONS_DIR.glob("*.json"), reverse=True):
        try:
            items.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            logger.exception("Failed reading submission file: %s", p)

    return jsonify({"ok": True, "count": len(items), "submissions": items})


@app.route("/api/plans-upload/<submission_id>/status", methods=["POST"])
def plans_upload_update_status_api(submission_id: str):
    """Update submission status and optionally notify client by email."""
    if not _require_admin_token():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    p = _submission_path(submission_id)
    if not p.exists():
        return jsonify({"ok": False, "error": "Submission not found"}), 404

    payload = request.get_json(silent=True) or {}
    new_status = (payload.get("status") or "").strip().lower()
    note = (payload.get("note") or "").strip()
    notify_client = bool(payload.get("notifyClient", True))
    if not new_status:
        return jsonify({"ok": False, "error": "Status is required"}), 400

    data = json.loads(p.read_text(encoding="utf-8"))
    data["status"] = new_status
    data["status_note"] = note
    data["updated_at"] = datetime.utcnow().isoformat() + "Z"
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")

    emailed = False
    email_status = "Client notification skipped"
    if notify_client:
        emailed, email_status = _send_status_email_to_client(data, new_status, note)

    return jsonify({"ok": True, "submission": data, "clientNotified": emailed, "emailStatus": email_status})


@app.route("/api/plans-upload/<submission_id>/file", methods=["GET"])
def plans_upload_get_file_api(submission_id: str):
    """Download original uploaded plan PDF for review."""
    if not _require_admin_token():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    p = _submission_path(submission_id)
    if not p.exists():
        return jsonify({"ok": False, "error": "Submission not found"}), 404
    data = json.loads(p.read_text(encoding="utf-8"))
    file_path = UPLOAD_DIR / data.get("file", "")
    if not file_path.exists():
        return jsonify({"ok": False, "error": "File not found"}), 404
    return send_file(file_path, as_attachment=True, download_name=file_path.name)


@app.route("/robots.txt", methods=["GET"])
def robots_txt():
    """Serve robots.txt for SEO."""
    return app.send_static_file("robots.txt")


@app.route("/sitemap.xml", methods=["GET"])
def sitemap_xml():
    """Serve sitemap.xml for SEO."""
    return app.send_static_file("sitemap.xml")


@app.route("/residential-proforma", methods=["GET"])
def residential_proforma():
    """Serve residential proforma page."""
    return app.send_static_file("residential-proforma.html")


@app.route("/api/residential-proforma/calculate", methods=["POST"])
def residential_proforma_calculate():
    """Calculate residential development proforma."""
    data = request.json
    
    # INPUTS
    acres = float(data.get('acres', 10))
    lot_count = int(data.get('lot_count', 50))
    lot_price = float(data.get('lot_price', 75000))
    land_cost_per_acre = float(data.get('land_cost_per_acre', 50000))
    
    # Hard costs (from estimate)
    earthwork = float(data.get('earthwork', 0))
    erosion_control = float(data.get('erosion_control', 0))
    storm_drainage = float(data.get('storm_drainage', 0))
    sanitary_sewer = float(data.get('sanitary_sewer', 0))
    water = float(data.get('water', 0))
    paving_concrete = float(data.get('paving_concrete', 0))
    striping_signage = float(data.get('striping_signage', 0))
    fencing_misc = float(data.get('fencing_misc', 0))
    
    # Soft costs
    engineering = float(data.get('engineering', 0))
    permits = float(data.get('permits', 0))
    legal = float(data.get('legal', 0))
    marketing = float(data.get('marketing', 0))
    
    # Sales & financing
    sales_commission_pct = float(data.get('sales_commission_pct', 5.0))
    construction_loan_rate = float(data.get('construction_loan_rate', 7.5))
    development_months = int(data.get('development_months', 12))
    sales_months = int(data.get('sales_months', 18))
    lots_per_month = float(data.get('lots_per_month', 3))
    
    # CALCULATIONS
    land_cost = acres * land_cost_per_acre
    
    hard_costs = (earthwork + erosion_control + storm_drainage + sanitary_sewer + 
                  water + paving_concrete + striping_signage + fencing_misc)
    
    soft_costs = engineering + permits + legal + marketing
    
    total_development_cost = land_cost + hard_costs + soft_costs
    
    # Construction loan interest
    avg_loan_balance = total_development_cost / 2
    construction_interest = avg_loan_balance * (construction_loan_rate / 100) * (development_months / 12)
    
    total_cost_with_financing = total_development_cost + construction_interest
    
    # Revenue
    gross_revenue = lot_count * lot_price
    sales_commissions = gross_revenue * (sales_commission_pct / 100)
    net_revenue = gross_revenue - sales_commissions
    
    # Profit
    gross_profit = net_revenue - total_cost_with_financing
    profit_margin = (gross_profit / net_revenue * 100) if net_revenue > 0 else 0
    
    cost_per_lot = total_cost_with_financing / lot_count if lot_count > 0 else 0
    profit_per_lot = gross_profit / lot_count if lot_count > 0 else 0
    
    # ROI
    roi = (gross_profit / total_cost_with_financing * 100) if total_cost_with_financing > 0 else 0
    
    # Timeline
    total_months = development_months + sales_months
    months_to_breakeven = 0
    cumulative_cash = -total_development_cost
    
    for month in range(1, total_months + 1):
        if month <= development_months:
            cumulative_cash -= construction_interest / development_months
        else:
            month_revenue = lots_per_month * lot_price
            month_commission = month_revenue * (sales_commission_pct / 100)
            cumulative_cash += (month_revenue - month_commission)
            
            if cumulative_cash >= 0 and months_to_breakeven == 0:
                months_to_breakeven = month
    
    return jsonify({
        'land_cost': round(land_cost, 2),
        'hard_costs': round(hard_costs, 2),
        'soft_costs': round(soft_costs, 2),
        'construction_interest': round(construction_interest, 2),
        'total_cost': round(total_cost_with_financing, 2),
        'gross_revenue': round(gross_revenue, 2),
        'sales_commissions': round(sales_commissions, 2),
        'net_revenue': round(net_revenue, 2),
        'gross_profit': round(gross_profit, 2),
        'profit_margin': round(profit_margin, 2),
        'cost_per_lot': round(cost_per_lot, 2),
        'profit_per_lot': round(profit_per_lot, 2),
        'roi': round(roi, 2),
        'months_to_breakeven': months_to_breakeven,
        'total_months': total_months
    })


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
