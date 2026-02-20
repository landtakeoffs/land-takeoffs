"""Terrain slope, aspect, and buildability analysis."""

import logging
from typing import Dict, Optional, Tuple

import numpy as np
from scipy import ndimage

logger = logging.getLogger(__name__)


class TerrainAnalyzer:
    """Analyse a DEM raster for slope, aspect, buildable areas, and cut/fill."""

    def __init__(self, elevation: np.ndarray, cell_size: float = 1.0):
        """
        Args:
            elevation: 2-D array of elevations.
            cell_size: Ground distance per pixel (same units as elevation, typically metres or feet).
        """
        self.elevation = elevation.astype(np.float64)
        self.cell_size = cell_size

    # ------------------------------------------------------------------
    # Slope & Aspect
    # ------------------------------------------------------------------

    def calculate_slope(self) -> np.ndarray:
        """Calculate slope in degrees using Horn's method via Sobel operators.

        Returns:
            2-D array of slope values in degrees.
        """
        dz_dx = ndimage.sobel(self.elevation, axis=1) / (8.0 * self.cell_size)
        dz_dy = ndimage.sobel(self.elevation, axis=0) / (8.0 * self.cell_size)
        slope_rad = np.arctan(np.sqrt(dz_dx ** 2 + dz_dy ** 2))
        slope_deg = np.degrees(slope_rad)
        logger.info(
            "Slope calculated: min=%.2f°, max=%.2f°, mean=%.2f°",
            float(np.nanmin(slope_deg)),
            float(np.nanmax(slope_deg)),
            float(np.nanmean(slope_deg)),
        )
        return slope_deg

    def calculate_aspect(self) -> np.ndarray:
        """Calculate aspect (compass bearing of steepest descent) in degrees.

        Returns:
            2-D array of aspect values (0-360°, north = 0°).
        """
        dz_dx = ndimage.sobel(self.elevation, axis=1) / (8.0 * self.cell_size)
        dz_dy = ndimage.sobel(self.elevation, axis=0) / (8.0 * self.cell_size)
        aspect_rad = np.arctan2(-dz_dy, dz_dx)
        aspect_deg = np.degrees(aspect_rad)
        # Convert from math-angle to compass bearing
        aspect_compass = (90.0 - aspect_deg) % 360.0
        return aspect_compass

    # ------------------------------------------------------------------
    # Buildable Area Identification
    # ------------------------------------------------------------------

    def identify_buildable_areas(
        self,
        max_slope: float = 15.0,
        min_area_sqft: float = 5000.0,
    ) -> np.ndarray:
        """Identify contiguous regions with slope ≤ *max_slope*.

        Small isolated patches (< *min_area_sqft*) are filtered out.

        Args:
            max_slope: Maximum allowable slope in degrees.
            min_area_sqft: Minimum contiguous area in square feet.

        Returns:
            Boolean mask where True = buildable.
        """
        slope = self.calculate_slope()
        buildable = slope <= max_slope

        # Connected-component labelling to remove small patches
        labelled, num_features = ndimage.label(buildable)
        logger.info("Found %d connected buildable regions before filtering", num_features)

        cell_area_sqft = (self.cell_size ** 2) * 10.7639  # m² → ft² (approx)
        min_cells = max(1, int(min_area_sqft / cell_area_sqft))

        for region_id in range(1, num_features + 1):
            region_mask = labelled == region_id
            if region_mask.sum() < min_cells:
                buildable[region_mask] = False

        remaining = ndimage.label(buildable)[1]
        logger.info(
            "Buildable area: %.1f%% of raster (%d regions after filtering)",
            100.0 * buildable.sum() / buildable.size,
            remaining,
        )
        return buildable

    # ------------------------------------------------------------------
    # Cut / Fill
    # ------------------------------------------------------------------

    def calculate_cut_fill_volumes(
        self,
        target_elevation: float,
        buildable_mask: Optional[np.ndarray] = None,
    ) -> Dict[str, float]:
        """Estimate earthwork cut and fill volumes.

        Args:
            target_elevation: Desired pad / finish grade elevation.
            buildable_mask: Optional boolean mask limiting the analysis area.

        Returns:
            Dict with 'cut_cy' and 'fill_cy' (cubic yards).
        """
        elev = self.elevation.copy()
        if buildable_mask is not None:
            elev = np.where(buildable_mask, elev, np.nan)

        diff = elev - target_elevation  # positive = cut, negative = fill
        cell_volume_m3 = self.cell_size ** 2  # volume per 1 m depth per cell

        cut_m3 = float(np.nansum(np.where(diff > 0, diff, 0.0)) * cell_volume_m3)
        fill_m3 = float(np.nansum(np.where(diff < 0, -diff, 0.0)) * cell_volume_m3)

        m3_to_cy = 1.30795  # 1 m³ ≈ 1.308 yd³
        result = {
            "cut_cy": round(cut_m3 * m3_to_cy, 1),
            "fill_cy": round(fill_m3 * m3_to_cy, 1),
        }
        logger.info("Cut/Fill: cut=%.1f CY, fill=%.1f CY", result["cut_cy"], result["fill_cy"])
        return result

    def find_optimal_pad_elevation(
        self,
        buildable_mask: Optional[np.ndarray] = None,
    ) -> float:
        """Find the pad elevation that minimises total earthwork (median).

        Args:
            buildable_mask: Optional boolean mask for the area of interest.

        Returns:
            Optimal pad elevation value.
        """
        elev = self.elevation.copy()
        if buildable_mask is not None:
            elev = elev[buildable_mask]
        else:
            elev = elev.ravel()

        valid = elev[~np.isnan(elev)]
        if valid.size == 0:
            raise ValueError("No valid elevation data in the buildable area")

        optimal = float(np.median(valid))
        logger.info("Optimal pad elevation (median): %.2f", optimal)
        return optimal
