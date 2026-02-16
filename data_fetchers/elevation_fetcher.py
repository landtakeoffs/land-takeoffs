"""Fetch DEM elevation data from the OpenTopography API."""

import logging
from typing import Dict, Optional, Tuple

import numpy as np
import rasterio
from rasterio.io import MemoryFile

from config import config

logger = logging.getLogger(__name__)

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore[assignment]


class ElevationFetcher:
    """Download and analyse DEM rasters from OpenTopography."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.OPENTOPOGRAPHY_API_KEY
        self.base_url = config.OPENTOPOGRAPHY_BASE_URL

    def fetch_dem_for_parcel(
        self,
        bounds: Tuple[float, float, float, float],
        buffer_distance: float = 0.001,
        dem_type: str = "SRTMGL1",
    ) -> Tuple[np.ndarray, dict]:
        """Download a DEM raster covering the given WGS-84 bounding box.

        Args:
            bounds: (west, south, east, north) in EPSG:4326.
            buffer_distance: Degrees to expand the bounding box by.
            dem_type: OpenTopography dataset identifier.

        Returns:
            Tuple of (elevation_array, raster_profile).
        """
        west, south, east, north = bounds
        west -= buffer_distance
        south -= buffer_distance
        east += buffer_distance
        north += buffer_distance

        logger.info(
            "Fetching DEM (%s) for bounds: W=%.5f S=%.5f E=%.5f N=%.5f",
            dem_type, west, south, east, north,
        )

        url = f"{self.base_url}/globaldem"
        params = {
            "demtype": dem_type,
            "south": south,
            "north": north,
            "west": west,
            "east": east,
            "outputFormat": "GTiff",
            "API_Key": self.api_key,
        }

        if requests is None:
            raise RuntimeError("requests library is required")

        response = requests.get(url, params=params, timeout=120)
        response.raise_for_status()

        with MemoryFile(response.content) as memfile:
            with memfile.open() as dataset:
                elevation = dataset.read(1).astype(np.float64)
                profile = dict(dataset.profile)

        logger.info(
            "DEM fetched: shape=%s, min=%.1f, max=%.1f",
            elevation.shape, float(np.nanmin(elevation)), float(np.nanmax(elevation)),
        )
        return elevation, profile

    @staticmethod
    def calculate_elevation_statistics(elevation: np.ndarray) -> Dict[str, float]:
        """Compute basic statistics on an elevation array.

        Args:
            elevation: 2-D numpy array of elevations (metres).

        Returns:
            Dictionary with min, max, mean, std, median, and range.
        """
        valid = elevation[~np.isnan(elevation)]
        if valid.size == 0:
            return {k: 0.0 for k in ("min", "max", "mean", "std", "median", "range")}

        stats: Dict[str, float] = {
            "min": float(np.min(valid)),
            "max": float(np.max(valid)),
            "mean": float(np.mean(valid)),
            "std": float(np.std(valid)),
            "median": float(np.median(valid)),
            "range": float(np.ptp(valid)),
        }
        return stats
