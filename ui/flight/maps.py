"""Mapbox vector tile fetching for the route preview.

Builds a tile *bundle* (the multi-tile shape consumed by ``Map``) covering
the full origin-to-destination flight path. Tiles are cached aggressively
because routes don't change between snapshots and the same airport pair is
likely to come up again. Network fetches happen on a background thread so
they don't block the render loop; until tiles arrive the slot stays blank.
"""

from __future__ import annotations

import gzip
import math
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

try:
    from mapbox_vector_tile import decode as decode_mvt
except Exception:  # pragma: no cover — dependency may be missing during dev.
    decode_mvt = None


MAPBOX_TILESET = "mapbox.mapbox-streets-v8"
MAPBOX_STYLE = "mapbox://styles/mapbox/streets-v12@00"
MAPBOX_STYLE_OWNER = "jackstoller"

# Limits the number of vector tiles a single route may pull in. A 3x3 grid is
# usually enough for a transcontinental route at zoom 4; tighter routes will
# pick a higher zoom but stay well under this limit.
MAX_TILE_GRID = 9
# Lat/lon padding around the route bounding box so the line doesn't sit flush
# against the edge of the rendered map. Expressed as a fraction of bbox span.
ROUTE_PADDING_FRAC = 0.20
# Minimum padding in degrees so very short routes (<1 degree span) still
# look reasonable.
MIN_PADDING_DEG = 0.5

_TILE_CACHE: dict[tuple[int, int, int], dict[str, Any]] = {}
_TILE_CACHE_LOCK = threading.Lock()
_TILE_FETCH_TIMEOUT_S = 12.0


def _resolve_style_uri(style: str, owner: str) -> str:
    if style.startswith("mapbox://"):
        return style
    return f"mapbox://styles/{owner}/{style}"


def _fetch_decoded_tile(zoom: int, x: int, y: int) -> dict[str, Any]:
    """Download and decode a single MVT, with a process-wide cache."""
    if decode_mvt is None:
        raise RuntimeError("mapbox-vector-tile is not installed")

    key = (zoom, x, y)
    with _TILE_CACHE_LOCK:
        cached = _TILE_CACHE.get(key)
    if cached is not None:
        return cached

    token = os.environ.get("MAPBOX_TOKEN", "")
    if not token:
        raise RuntimeError("MAPBOX_TOKEN is not set")

    style_uri = _resolve_style_uri(MAPBOX_STYLE, MAPBOX_STYLE_OWNER)
    encoded_style = urllib.parse.quote(style_uri, safe=":/@")

    base_url = f"https://api.mapbox.com/v4/{MAPBOX_TILESET}/{zoom}/{x}/{y}.mvt"
    urls = [
        f"{base_url}?style={encoded_style}&access_token={token}",
        f"{base_url}?access_token={token}",
    ]

    payload: bytes | None = None
    last_error: Exception | None = None
    for url in urls:
        try:
            with urllib.request.urlopen(url, timeout=_TILE_FETCH_TIMEOUT_S) as response:
                payload = response.read()
                break
        except urllib.error.HTTPError as exc:
            last_error = RuntimeError(f"map tile HTTP {exc.code}: {exc.reason}")
            continue
        except urllib.error.URLError as exc:
            last_error = RuntimeError(f"map tile fetch failed: {exc.reason}")
            continue

    if payload is None:
        raise RuntimeError(str(last_error) if last_error is not None else "map tile fetch failed")

    if payload.startswith(b"\x1f\x8b"):
        payload = gzip.decompress(payload)

    decoded = decode_mvt(payload, default_options={"y_coord_down": True})
    with _TILE_CACHE_LOCK:
        _TILE_CACHE[key] = decoded
    return decoded


def lon_lat_to_world_tile(lon: float, lat: float, zoom: int) -> tuple[float, float]:
    """Project lon/lat to fractional tile coordinates at ``zoom``."""
    lat = max(min(lat, 85.0511), -85.0511)
    n = 2**zoom
    x = ((lon + 180.0) / 360.0) * n
    lat_rad = math.radians(lat)
    y = (1.0 - (math.log(math.tan(lat_rad) + (1.0 / math.cos(lat_rad))) / math.pi)) * 0.5 * n
    return x, y


def _route_bbox(
    points: list[tuple[float, float]],
) -> tuple[float, float, float, float]:
    """Padded (min_lat, min_lon, max_lat, max_lon) for a list of (lat, lon)."""
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    min_lat = min(lats)
    max_lat = max(lats)
    min_lon = min(lons)
    max_lon = max(lons)
    pad_lat = max(MIN_PADDING_DEG, (max_lat - min_lat) * ROUTE_PADDING_FRAC)
    pad_lon = max(MIN_PADDING_DEG, (max_lon - min_lon) * ROUTE_PADDING_FRAC)
    return (
        max(-85.0, min_lat - pad_lat),
        min_lon - pad_lon,
        min(85.0, max_lat + pad_lat),
        max_lon + pad_lon,
    )


def _select_zoom(
    bbox: tuple[float, float, float, float],
    *,
    max_tiles: int = MAX_TILE_GRID,
) -> int:
    """Pick the highest zoom level whose tile grid stays under ``max_tiles``.

    The search runs from zoom 1 up; the loop returns the previous level once
    the grid would exceed the limit. Caps at zoom 8 — the route preview only
    needs broad land/water context, and higher zooms add download cost
    without making the line easier to read on a 40-pixel-wide widget.
    """
    min_lat, min_lon, max_lat, max_lon = bbox
    best = 1
    for zoom in range(1, 9):
        # Tile y grows southward, so the NW corner gives (min_x, min_y) and
        # the SE corner gives (max_x, max_y) in world-tile coordinates.
        x_min, y_min = lon_lat_to_world_tile(min_lon, max_lat, zoom)
        x_max, y_max = lon_lat_to_world_tile(max_lon, min_lat, zoom)
        tile_w = math.floor(x_max) - math.floor(x_min) + 1
        tile_h = math.floor(y_max) - math.floor(y_min) + 1
        if tile_w * tile_h > max_tiles:
            return best
        best = zoom
    return best


def _expand_bbox_to_aspect(
    bbox: tuple[float, float, float, float],
    target_aspect: float,
    zoom: int,
) -> tuple[float, float, float, float]:
    """Pad the bbox in lat or lon so its world-tile shape matches ``target_aspect``.

    The route alone often produces a portrait bbox (e.g. CLT → CLE goes
    far more north-south than east-west). When that gets rendered into a
    landscape rect it leaves bald green padding on the sides. Expanding
    the bbox here means we fetch enough tiles to fill the whole rect.

    ``target_aspect`` is rect_w / rect_h. The expansion happens in world
    tile coordinates so the fix-up is correct under Mercator distortion.
    """
    if target_aspect <= 0:
        return bbox
    min_lat, min_lon, max_lat, max_lon = bbox
    x_min, y_min = lon_lat_to_world_tile(min_lon, max_lat, zoom)
    x_max, y_max = lon_lat_to_world_tile(max_lon, min_lat, zoom)
    world_w = max(1e-9, x_max - x_min)
    world_h = max(1e-9, y_max - y_min)
    current_aspect = world_w / world_h
    if current_aspect < target_aspect:
        # Portrait → widen lon span until aspect matches.
        new_w = world_h * target_aspect
        pad = (new_w - world_w) * 0.5
        x_min -= pad
        x_max += pad
    elif current_aspect > target_aspect:
        # Landscape → widen lat span.
        new_h = world_w / target_aspect
        pad = (new_h - world_h) * 0.5
        y_min -= pad
        y_max += pad
    else:
        return bbox

    # Convert the world-tile-coord box back to lat/lon. Inverting the
    # web-mercator y → lat is the only fiddly bit; lon is linear.
    n = 2**zoom
    new_min_lon = (x_min / n) * 360.0 - 180.0
    new_max_lon = (x_max / n) * 360.0 - 180.0
    new_max_lat = math.degrees(
        math.atan(math.sinh(math.pi * (1.0 - 2.0 * y_min / n)))
    )
    new_min_lat = math.degrees(
        math.atan(math.sinh(math.pi * (1.0 - 2.0 * y_max / n)))
    )
    return (
        max(-85.0, new_min_lat),
        new_min_lon,
        min(85.0, new_max_lat),
        new_max_lon,
    )


def build_route_view(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    *,
    plane_lat: float | None = None,
    plane_lon: float | None = None,
    target_aspect: float | None = None,
) -> tuple[int, tuple[float, float, float, float]]:
    """Compute (zoom, padded_bbox) for the route — used to key tile cache.

    When ``target_aspect`` is supplied (rect_w / rect_h), the bbox is
    expanded so the fetched tile coverage matches the rect's shape.
    """
    points: list[tuple[float, float]] = [(origin_lat, origin_lon), (dest_lat, dest_lon)]
    if plane_lat is not None and plane_lon is not None:
        points.append((plane_lat, plane_lon))
    bbox = _route_bbox(points)
    zoom = _select_zoom(bbox)
    if target_aspect is not None:
        bbox = _expand_bbox_to_aspect(bbox, target_aspect, zoom)
        # Re-pick zoom; expanded bbox might exceed the previous tile cap.
        zoom = _select_zoom(bbox)
        bbox = _expand_bbox_to_aspect(bbox, target_aspect, zoom)
    return zoom, bbox


def fetch_route_tiles(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    *,
    plane_lat: float | None = None,
    plane_lon: float | None = None,
    target_aspect: float | None = None,
) -> dict[str, Any]:
    """Synchronously assemble the multi-tile bundle covering the route.

    Returned dict mirrors the shape that ``Map`` and ``_draw_map_view``
    expect when rendering a multi-tile view. Use ``RouteMapFetcher`` if you
    need this off the render thread.
    """
    zoom, bbox = build_route_view(
        origin_lat,
        origin_lon,
        dest_lat,
        dest_lon,
        plane_lat=plane_lat,
        plane_lon=plane_lon,
        target_aspect=target_aspect,
    )
    min_lat, min_lon, max_lat, max_lon = bbox
    x_min_w, y_min_w = lon_lat_to_world_tile(min_lon, max_lat, zoom)
    x_max_w, y_max_w = lon_lat_to_world_tile(max_lon, min_lat, zoom)

    n = 2**zoom
    min_tx = math.floor(x_min_w)
    max_tx = math.floor(x_max_w)
    min_ty = max(0, math.floor(y_min_w))
    max_ty = min(n - 1, math.floor(y_max_w))

    tiles: list[dict[str, Any]] = []
    for tile_y in range(min_ty, max_ty + 1):
        for tile_x_unwrapped in range(min_tx, max_tx + 1):
            tile_x_wrapped = tile_x_unwrapped % n
            data = _fetch_decoded_tile(zoom, tile_x_wrapped, tile_y)
            tiles.append(
                {
                    "x": tile_x_wrapped,
                    "x_unwrapped": tile_x_unwrapped,
                    "y": tile_y,
                    "data": data,
                }
            )

    return {
        "zoom": zoom,
        "min_world_x": x_min_w,
        "min_world_y": y_min_w,
        "world_width": max(1e-9, x_max_w - x_min_w),
        "world_height": max(1e-9, y_max_w - y_min_w),
        "tiles": tiles,
        "bbox": bbox,
    }


def empty_route_view(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    *,
    plane_lat: float | None = None,
    plane_lon: float | None = None,
    target_aspect: float | None = None,
) -> dict[str, Any]:
    """Tile-less bundle with just the projection metadata.

    Used as a placeholder while the real bundle is being fetched (or when
    Mapbox is unreachable / the token isn't configured) so the route line
    overlay still has a valid projection to draw against. The empty
    ``tiles`` list keeps the rendering codepath happy without painting any
    underlying basemap features.
    """
    zoom, bbox = build_route_view(
        origin_lat,
        origin_lon,
        dest_lat,
        dest_lon,
        plane_lat=plane_lat,
        plane_lon=plane_lon,
        target_aspect=target_aspect,
    )
    min_lat, min_lon, max_lat, max_lon = bbox
    x_min_w, y_min_w = lon_lat_to_world_tile(min_lon, max_lat, zoom)
    x_max_w, y_max_w = lon_lat_to_world_tile(max_lon, min_lat, zoom)
    return {
        "zoom": zoom,
        "min_world_x": x_min_w,
        "min_world_y": y_min_w,
        "world_width": max(1e-9, x_max_w - x_min_w),
        "world_height": max(1e-9, y_max_w - y_min_w),
        "tiles": [],
        "bbox": bbox,
    }


class RouteMapFetcher:
    """Background-thread tile fetcher keyed on (origin, destination).

    A single executor backs a one-slot cache: the most recent successful
    bundle plus its key. The hero loop polls ``get`` on every render —
    the call returns immediately with whatever tiles are ready (possibly
    a tile-less placeholder bundle until the first fetch completes).
    """

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="route-map")
        self._lock = threading.Lock()
        self._key: tuple[float, float, float, float] | None = None
        self._bundle: dict[str, Any] | None = None
        self._pending: Future[dict[str, Any]] | None = None
        self._pending_key: tuple[float, float, float, float] | None = None
        self._error: str | None = None
        # Routes whose tile fetches failed permanently (e.g. no MAPBOX_TOKEN).
        # Keyed the same way as ``_key``; we won't retry until the key drifts.
        self._failed: set[tuple[float, float, float, float]] = set()

    def get(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
        *,
        target_aspect: float | None = None,
    ) -> dict[str, Any]:
        """Return a bundle for the route — tiles when ready, placeholder otherwise.

        The route key is rounded to ~1 km so tiny aircraft-driven shifts
        don't invalidate the cache. The plane position is *not* part of
        the key — we want the same bundle reused as the plane moves so the
        map doesn't reload mid-flight. ``target_aspect`` rounds into the
        key at 2 decimal places, which keeps a consistent rect shape from
        re-fetching tiles unnecessarily.
        """
        aspect_key = round(target_aspect, 2) if target_aspect is not None else None
        key = (
            round(origin_lat, 2),
            round(origin_lon, 2),
            round(dest_lat, 2),
            round(dest_lon, 2),
            aspect_key,
        )

        with self._lock:
            if self._pending is not None and self._pending.done():
                future = self._pending
                pending_key = self._pending_key
                self._pending = None
                self._pending_key = None
                try:
                    result = future.result()
                    self._bundle = result
                    self._key = pending_key
                    self._error = None
                except Exception as exc:  # pragma: no cover — best-effort
                    self._error = f"{exc.__class__.__name__}: {exc}"
                    if pending_key is not None:
                        self._failed.add(pending_key)

            if self._key == key and self._bundle is not None:
                return self._bundle

            if (
                self._pending is None
                and key not in self._failed
                and (self._pending_key != key or self._key != key)
            ):
                self._pending_key = key
                self._pending = self._executor.submit(
                    fetch_route_tiles,
                    origin_lat,
                    origin_lon,
                    dest_lat,
                    dest_lon,
                    target_aspect=target_aspect,
                )

        # Fallback while tiles are loading or after a permanent failure: a
        # bundle with the right projection but no basemap features.
        return empty_route_view(
            origin_lat, origin_lon, dest_lat, dest_lon,
            target_aspect=target_aspect,
        )


_default_fetcher: RouteMapFetcher | None = None


def default_fetcher() -> RouteMapFetcher:
    """Lazily construct the process-wide route-map fetcher."""
    global _default_fetcher
    if _default_fetcher is None:
        _default_fetcher = RouteMapFetcher()
    return _default_fetcher
