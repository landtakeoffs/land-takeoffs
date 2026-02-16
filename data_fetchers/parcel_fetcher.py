"""Fetch parcel boundary data from the Regrid API."""

import logging
from typing import Optional

try:
    import geopandas as gpd
except ImportError:
    gpd = None
import requests
from shapely.geometry import shape

from config import config

logger = logging.getLogger(__name__)


class ParcelFetcher:
    """Retrieve and validate parcel geometry from the Regrid parcel API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or config.PARCEL_API_KEY
        self.base_url = config.REGRID_BASE_URL

    def fetch_by_tax_id(self, tax_id: str) -> gpd.GeoDataFrame:
        """Fetch parcel data by tax/parcel ID.

        Args:
            tax_id: The assessor parcel number (APN) or tax ID.

        Returns:
            GeoDataFrame with parcel geometry and attributes.

        Raises:
            ValueError: If the tax ID returns no results.
            requests.HTTPError: On API errors.
        """
        logger.info("Fetching parcel data for tax ID: %s", tax_id)

        url = f"{self.base_url}/parcels"
        params = {
            "token": self.api_key,
            "parcelnumb": tax_id,
            "return_geometry": True,
        }

        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        features = data.get("features") or data.get("results", [])
        if not features:
            raise ValueError(f"No parcel found for tax ID: {tax_id}")

        # Build GeoDataFrame from GeoJSON features
        geometries = []
        attributes = []
        for feat in features:
            geom = shape(feat["geometry"])
            props = feat.get("properties", {})
            geometries.append(geom)
            attributes.append(props)

        gdf = gpd.GeoDataFrame(attributes, geometry=geometries, crs=config.DEFAULT_CRS)
        logger.info(
            "Retrieved %d parcel(s) for tax ID %s, total area: %.2f sq m",
            len(gdf),
            tax_id,
            gdf.to_crs(config.WORKING_CRS).geometry.area.sum(),
        )
        return gdf

    @staticmethod
    def validate_parcel_data(gdf: gpd.GeoDataFrame) -> list[str]:
        """Check a parcel GeoDataFrame for common issues.

        Returns:
            List of warning/error strings (empty means valid).
        """
        issues: list[str] = []

        if gdf.empty:
            issues.append("GeoDataFrame is empty")
            return issues

        if gdf.geometry.is_empty.any():
            issues.append("One or more geometries are empty")

        if not gdf.geometry.is_valid.all():
            invalid_count = (~gdf.geometry.is_valid).sum()
            issues.append(f"{invalid_count} invalid geometries detected")

        if gdf.crs is None:
            issues.append("CRS is not set")

        return issues
