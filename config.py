"""
Configuration module for Civil Engineering Analysis Application.

Centralizes all configuration parameters including CRS settings,
development standards, cost parameters, and API credentials.
"""

import os
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Application configuration with sensible defaults for civil engineering analysis."""

    # --- Coordinate Reference Systems ---
    DEFAULT_CRS: str = "EPSG:4326"  # WGS84 Geographic
    WORKING_CRS: str = "EPSG:3857"  # Web Mercator (meters)

    # --- Terrain / Grading ---
    MAX_BUILDABLE_SLOPE: float = 15.0  # percent slope
    OPTIMAL_PAD_SLOPE: float = 2.0  # percent, for drainage
    MAX_CUT_DEPTH_FT: float = 15.0
    MAX_FILL_DEPTH_FT: float = 10.0
    SOIL_SWELL_FACTOR: float = 1.25  # cut material expands ~25%
    SOIL_SHRINK_FACTOR: float = 0.90  # fill material compacts ~10%

    # --- Lot / Subdivision Standards ---
    MIN_LOT_SIZE: float = 0.25  # acres
    MAX_LOT_SIZE: float = 2.0  # acres
    ROAD_WIDTH: float = 30.0  # feet (back-of-curb to back-of-curb)
    ROW_WIDTH: float = 50.0  # feet (right-of-way)
    CUL_DE_SAC_RADIUS: float = 45.0  # feet

    # --- Setbacks (feet) ---
    SETBACK_FRONT: float = 25.0
    SETBACK_SIDE: float = 10.0
    SETBACK_REAR: float = 20.0

    # --- Stormwater ---
    PRE_DEVELOPMENT_C: float = 0.35  # runoff coefficient – meadow/woods
    POST_DEVELOPMENT_C: float = 0.65  # runoff coefficient – developed
    MANNING_N_PIPE: float = 0.013  # RCP
    MANNING_N_CHANNEL: float = 0.035  # grass-lined
    FREEBOARD_FT: float = 1.0

    # --- Utility Standards ---
    WATER_MAIN_DEPTH_FT: float = 3.5
    SEWER_MAIN_DEPTH_FT: float = 6.0
    MIN_SEWER_SLOPE: float = 0.005  # ft/ft for 8" pipe
    FIRE_HYDRANT_SPACING_FT: float = 500.0

    # --- API Keys (from environment) ---
    REGRID_API_KEY: str = os.getenv("REGRID_API_KEY", "")
    OPENTOPO_API_KEY: str = os.getenv("OPENTOPO_API_KEY", "")
    OPENTOPOGRAPHY_API_KEY: str = os.getenv("OPENTOPO_API_KEY", "")

    # --- API Endpoints ---
    REGRID_BASE_URL: str = "https://api.regrid.com/v2"
    OPENTOPO_BASE_URL: str = "https://portal.opentopography.org/API"
    OPENTOPOGRAPHY_BASE_URL: str = "https://portal.opentopography.org/API"

    # --- Flask ---
    FLASK_HOST: str = os.getenv("FLASK_HOST", "0.0.0.0")
    FLASK_PORT: int = int(os.getenv("FLASK_PORT", "5000"))
    FLASK_DEBUG: bool = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    # --- Output ---
    OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", os.path.dirname(os.path.abspath(__file__)))

    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-prod")

    @classmethod
    def validate(cls):
        """Return list of configuration issues."""
        issues = []
        if not cls.REGRID_API_KEY:
            issues.append("REGRID_API_KEY not set - parcel lookup unavailable")
        if not cls.OPENTOPO_API_KEY:
            issues.append("OPENTOPO_API_KEY not set - elevation data unavailable")
        return issues

    @classmethod
    def setbacks_dict(cls) -> Dict[str, float]:
        """Return setbacks as a dictionary."""
        return {
            "front": cls.SETBACK_FRONT,
            "side": cls.SETBACK_SIDE,
            "rear": cls.SETBACK_REAR,
        }

    @classmethod
    def to_dict(cls) -> Dict[str, Any]:
        """Serialize all non-callable, non-dunder attributes."""
        return {
            k: v
            for k, v in vars(cls).items()
            if not k.startswith("_") and not callable(v)
        }


# Module-level convenience alias
config = Config
