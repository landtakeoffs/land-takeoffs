"""Fetch DEM elevation data from the OpenTopography API."""

import io
import logging
import struct
from typing import Dict, Optional, Tuple

import numpy as np

from config import config

logger = logging.getLogger(__name__)

try:
    import rasterio
    from rasterio.io import MemoryFile
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False

try:
    import requests
except ImportError:
    requests = None


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

        # Check for API errors (OpenTopography returns HTML/text on errors)
        ct = response.headers.get('content-type', '')
        if response.status_code != 200 or 'tiff' not in ct.lower() and 'octet' not in ct.lower():
            logger.error("OpenTopography error: status=%s, content-type=%s, body=%s",
                         response.status_code, ct, response.text[:500])
            raise RuntimeError(f"OpenTopography API error: {response.text[:200]}")

        if len(response.content) < 100:
            logger.error("OpenTopography returned tiny response (%d bytes): %s",
                         len(response.content), response.text[:200])
            raise RuntimeError("OpenTopography returned empty/invalid DEM data")

        if HAS_RASTERIO:
            return self._parse_with_rasterio(response.content)
        else:
            return self._parse_geotiff_minimal(response.content, west, south, east, north)

    def _parse_with_rasterio(self, data: bytes) -> Tuple[np.ndarray, dict]:
        """Parse GeoTIFF using rasterio (full featured)."""
        with MemoryFile(data) as memfile:
            with memfile.open() as dataset:
                elevation = dataset.read(1).astype(np.float64)
                profile = dict(dataset.profile)
        logger.info("DEM fetched (rasterio): shape=%s", elevation.shape)
        return elevation, profile

    def _parse_geotiff_minimal(self, data: bytes, west, south, east, north) -> Tuple[np.ndarray, dict]:
        """Parse GeoTIFF without rasterio — basic TIFF parser for single-band DEMs."""
        import struct

        # Read TIFF header
        bo = '<' if data[:2] == b'II' else '>'
        magic = struct.unpack_from(f'{bo}H', data, 2)[0]
        if magic != 42:
            raise ValueError("Not a valid TIFF file")

        ifd_offset = struct.unpack_from(f'{bo}I', data, 4)[0]
        num_entries = struct.unpack_from(f'{bo}H', data, ifd_offset)[0]

        tags = {}
        for i in range(num_entries):
            entry_offset = ifd_offset + 2 + i * 12
            tag, dtype, count = struct.unpack_from(f'{bo}HHI', data, entry_offset)
            if dtype == 3 and count == 1:  # SHORT
                val = struct.unpack_from(f'{bo}H', data, entry_offset + 8)[0]
            elif dtype == 4 and count == 1:  # LONG
                val = struct.unpack_from(f'{bo}I', data, entry_offset + 8)[0]
            elif dtype == 1 and count == 1:  # BYTE
                val = data[entry_offset + 8]
            else:
                val = struct.unpack_from(f'{bo}I', data, entry_offset + 8)[0]
            tags[tag] = (dtype, count, val)

        width = tags.get(256, (0, 0, 0))[2]   # ImageWidth
        height = tags.get(257, (0, 0, 0))[2]   # ImageLength
        bits = tags.get(258, (0, 0, 16))[2]     # BitsPerSample
        sample_format = tags.get(339, (0, 0, 1))[2]  # SampleFormat (1=uint, 2=int, 3=float)
        strip_offsets = tags.get(273, (0, 0, 0))[2]
        strip_byte_counts = tags.get(279, (0, 0, 0))[2]

        # Handle strip offsets that point to an array
        so_dtype, so_count, so_val = tags.get(273, (4, 1, 0))
        if so_count == 1:
            offsets = [so_val]
        else:
            fmt = f'{bo}{so_count}I' if so_dtype == 4 else f'{bo}{so_count}H'
            offsets = list(struct.unpack_from(fmt, data, so_val))

        sbc_dtype, sbc_count, sbc_val = tags.get(279, (4, 1, 0))
        if sbc_count == 1:
            byte_counts = [sbc_val]
        else:
            fmt = f'{bo}{sbc_count}I' if sbc_dtype == 4 else f'{bo}{sbc_count}H'
            byte_counts = list(struct.unpack_from(fmt, data, sbc_val))

        # Read pixel data
        raw = b''
        for off, bc in zip(offsets, byte_counts):
            raw += data[off:off + bc]

        # Convert to numpy
        if bits == 16 and sample_format == 2:
            elevation = np.frombuffer(raw, dtype=f'{bo.replace("<","<").replace(">",">")}i2').reshape(height, width).astype(np.float64)
        elif bits == 16 and sample_format == 1:
            elevation = np.frombuffer(raw, dtype=f'{bo.replace("<","<").replace(">",">")}u2').reshape(height, width).astype(np.float64)
        elif bits == 32 and sample_format == 3:
            elevation = np.frombuffer(raw, dtype=f'{bo.replace("<","<").replace(">",">")}f4').reshape(height, width).astype(np.float64)
        else:
            elevation = np.frombuffer(raw, dtype=f'{bo.replace("<","<").replace(">",">")}i2').reshape(height, width).astype(np.float64)

        # Build a minimal profile with transform info
        x_res = (east - west) / width
        y_res = (north - south) / height
        profile = {
            "width": width,
            "height": height,
            "transform": [x_res, 0, west, 0, -y_res, north],
        }

        logger.info("DEM fetched (minimal parser): shape=%s, min=%.1f, max=%.1f",
                     elevation.shape, float(np.nanmin(elevation)), float(np.nanmax(elevation)))
        return elevation, profile

    @staticmethod
    def calculate_elevation_statistics(elevation: np.ndarray) -> Dict[str, float]:
        valid = elevation[~np.isnan(elevation)]
        if valid.size == 0:
            return {k: 0.0 for k in ("min", "max", "mean", "std", "median", "range")}

        return {
            "min": float(np.min(valid)),
            "max": float(np.max(valid)),
            "mean": float(np.mean(valid)),
            "std": float(np.std(valid)),
            "median": float(np.median(valid)),
            "range": float(np.ptp(valid)),
        }
