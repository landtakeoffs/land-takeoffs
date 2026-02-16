"""Lot layout generation and optimisation for subdivision planning."""

import logging
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
from shapely.geometry import box, Point

logger = logging.getLogger(__name__)

SQFT_PER_ACRE = 43_560.0


@dataclass
class LotCenter:
    """A candidate lot centre point."""
    x: float
    y: float
    id: int = 0


class LotLayoutGenerator:
    """Generate and optimise rectangular lot layouts within a buildable boundary.

    Coordinates are expected in a projected CRS (feet).
    """

    def __init__(
        self,
        boundary: "shapely.geometry.base.BaseGeometry",  # noqa: F821
        buildable_mask: Optional[np.ndarray] = None,
        cell_size: float = 1.0,
        origin: tuple = (0.0, 0.0),
    ):
        """
        Args:
            boundary: Shapely polygon of the site boundary (projected, feet).
            buildable_mask: Optional boolean raster mask (not used directly for vector layout).
            cell_size: Raster cell size in feet (used when converting mask).
            origin: (x, y) origin of the raster grid in CRS units.
        """
        self.boundary = boundary
        self.buildable_mask = buildable_mask
        self.cell_size = cell_size
        self.origin = origin

    # ------------------------------------------------------------------
    # Lot Centre Generation
    # ------------------------------------------------------------------

    def generate_lot_centers(
        self,
        target_lot_size_acres: float = 0.5,
        min_spacing: float = 100.0,
    ) -> List[LotCenter]:
        """Create a regular grid of lot centres inside the boundary.

        Args:
            target_lot_size_acres: Desired individual lot area (acres).
            min_spacing: Minimum spacing between centres (feet).

        Returns:
            List of LotCenter objects that fall within the boundary.
        """
        lot_sqft = target_lot_size_acres * SQFT_PER_ACRE
        # Use spacing derived from a square lot, but at least min_spacing
        spacing = max(min_spacing, np.sqrt(lot_sqft))

        minx, miny, maxx, maxy = self.boundary.bounds
        centers: List[LotCenter] = []
        idx = 0

        y = miny + spacing / 2
        while y < maxy:
            x = minx + spacing / 2
            while x < maxx:
                pt = Point(x, y)
                if self.boundary.contains(pt):
                    centers.append(LotCenter(x=x, y=y, id=idx))
                    idx += 1
                x += spacing
            y += spacing

        logger.info(
            "Generated %d lot centres (target %.2f ac, spacing %.1f ft)",
            len(centers), target_lot_size_acres, spacing,
        )
        return centers

    # ------------------------------------------------------------------
    # Lot Boundaries
    # ------------------------------------------------------------------

    def create_lot_boundaries(
        self,
        lot_centers: List[LotCenter],
        lot_width: float = 100.0,
        lot_depth: float = 150.0,
    ) -> list:
        """Create rectangular lot polygons centred on each lot centre.

        Lots that extend outside the site boundary are clipped.

        Args:
            lot_centers: List of LotCenter points.
            lot_width: Width of each lot in feet.
            lot_depth: Depth of each lot in feet.

        Returns:
            List of (lot_id, shapely Polygon) tuples.
        """
        half_w = lot_width / 2.0
        half_d = lot_depth / 2.0
        lots = []

        for lc in lot_centers:
            lot_poly = box(lc.x - half_w, lc.y - half_d, lc.x + half_w, lc.y + half_d)
            clipped = lot_poly.intersection(self.boundary)
            if not clipped.is_empty:
                lots.append((lc.id, clipped))

        logger.info("Created %d lot boundaries from %d centres", len(lots), len(lot_centers))
        return lots

    # ------------------------------------------------------------------
    # Optimisation
    # ------------------------------------------------------------------

    def optimize_lot_count(
        self,
        pad_size_sqft: float = 3_000.0,
        target_lot_size_acres: float = 0.5,
        road_reserve_pct: float = 0.20,
        open_space_pct: float = 0.15,
    ) -> dict:
        """Estimate maximum lot yield for the site.

        Args:
            pad_size_sqft: Building pad area per lot (sq ft).
            target_lot_size_acres: Target lot size (acres).
            road_reserve_pct: Fraction of gross area reserved for roads.
            open_space_pct: Fraction of gross area reserved for open space.

        Returns:
            Dictionary with gross_area, net_area, max_lots, road_area, open_space_area (all sq ft).
        """
        gross_sqft = self.boundary.area  # assumes projected CRS in feet
        road_sqft = gross_sqft * road_reserve_pct
        open_sqft = gross_sqft * open_space_pct
        net_sqft = gross_sqft - road_sqft - open_sqft

        lot_sqft = target_lot_size_acres * SQFT_PER_ACRE
        max_lots = int(net_sqft / lot_sqft) if lot_sqft > 0 else 0

        result = {
            "gross_area_sqft": round(gross_sqft, 1),
            "road_area_sqft": round(road_sqft, 1),
            "open_space_area_sqft": round(open_sqft, 1),
            "net_area_sqft": round(net_sqft, 1),
            "target_lot_sqft": round(lot_sqft, 1),
            "max_lots": max_lots,
        }
        logger.info("Lot optimisation: max %d lots on %.1f net sq ft", max_lots, net_sqft)
        return result
