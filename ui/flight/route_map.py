"""Tiny route-preview map widget with great-circle path overlay.

Renders a minimal Mapbox basemap — just water polygons, admin (state /
country) borders, and a base land color — then overlays the origin →
destination great-circle path in white plus a small marker for the
live aircraft position.

The expensive work (polygon fills + line interpolation across multiple
tiles) is cached per route into an off-screen pixel buffer. Each frame
just blits that buffer and re-stamps the moving plane dot, so the map
no longer dominates render time at 30 Hz on a Pi 4.
"""

from __future__ import annotations

import math
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from ui.core.canvas import PixelCanvas, Rect
from ui.core.colors import Color, colors
from ui.core.widgets import Map

from ui.flight.maps import lon_lat_to_world_tile


# Number of route_map renders to keep cached at once. Each is a small RGB
# byte buffer (40x22 ≈ 2.6 KB), so a generous cache costs almost nothing.
_RENDER_CACHE_MAX = 16

# Path is a great circle resampled at this many segments. Always plenty for a
# 40-pixel-wide widget — on short hops the line will visually collapse to one
# or two pixels regardless of segment count.
_PATH_SEGMENTS = 32


def _great_circle_points(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    segments: int = _PATH_SEGMENTS,
) -> list[tuple[float, float]]:
    """Slerp on the unit sphere → list of (lat, lon) along the great circle.

    Falls back to a straight lat/lon interpolation when origin and dest are
    effectively the same point — slerp's denominator goes to zero in that
    case and would produce NaNs.
    """
    phi1 = math.radians(origin_lat)
    lam1 = math.radians(origin_lon)
    phi2 = math.radians(dest_lat)
    lam2 = math.radians(dest_lon)

    cos_d = (
        math.sin(phi1) * math.sin(phi2)
        + math.cos(phi1) * math.cos(phi2) * math.cos(lam2 - lam1)
    )
    cos_d = max(-1.0, min(1.0, cos_d))
    d = math.acos(cos_d)

    points: list[tuple[float, float]] = []
    if d < 1e-6 or segments < 1:
        for i in range(segments + 1):
            t = i / segments if segments else 0.0
            points.append(
                (
                    origin_lat + (dest_lat - origin_lat) * t,
                    origin_lon + (dest_lon - origin_lon) * t,
                )
            )
        return points

    sin_d = math.sin(d)
    for i in range(segments + 1):
        f = i / segments
        a = math.sin((1.0 - f) * d) / sin_d
        b = math.sin(f * d) / sin_d
        x = a * math.cos(phi1) * math.cos(lam1) + b * math.cos(phi2) * math.cos(lam2)
        y = a * math.cos(phi1) * math.sin(lam1) + b * math.cos(phi2) * math.sin(lam2)
        z = a * math.sin(phi1) + b * math.sin(phi2)
        lat = math.degrees(math.atan2(z, math.sqrt(x * x + y * y)))
        lon = math.degrees(math.atan2(y, x))
        points.append((lat, lon))
    return points


def _draw_line(
    canvas: PixelCanvas,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    color: Color,
) -> None:
    """1-pixel-wide Bresenham line."""
    dx = abs(x1 - x0)
    sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0)
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        canvas.pixel(x0, y0, color)
        if x0 == x1 and y0 == y1:
            return
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def _project_lat_lon(
    lat: float,
    lon: float,
    bundle: dict[str, Any],
    rect_w: int,
    rect_h: int,
    origin_x: float,
    origin_y: float,
) -> tuple[float, float]:
    """Project lat/lon onto the cached-canvas pixel grid.

    ``rect_w``/``rect_h`` are the (already pre-computed) drawable extents
    minus 1; ``origin_x``/``origin_y`` are the pixel origin after centering
    a non-square bundle inside a non-matching rect aspect.
    """
    zoom = int(bundle.get("zoom", 4))
    wx, wy = lon_lat_to_world_tile(lon, lat, zoom)
    min_world_x = float(bundle.get("min_world_x", 0.0))
    min_world_y = float(bundle.get("min_world_y", 0.0))
    world_width = max(1e-9, float(bundle.get("world_width", 1.0)))
    world_height = max(1e-9, float(bundle.get("world_height", 1.0)))

    content_w = max(1.0, float(rect_w))
    content_h = max(1.0, float(rect_h))
    scale = min(content_w / world_width, content_h / world_height)
    return (
        origin_x + ((wx - min_world_x) * scale),
        origin_y + ((wy - min_world_y) * scale),
    )


def _projection_origin(
    bundle: dict[str, Any],
    rect_w: int,
    rect_h: int,
) -> tuple[float, float, float]:
    """Top-left pixel of the bundle inside an `rect_w` × `rect_h` content area.

    Returns (origin_x, origin_y, scale). The bundle may have a different
    aspect than the rect — we centre on the shorter axis.
    """
    world_width = max(1e-9, float(bundle.get("world_width", 1.0)))
    world_height = max(1e-9, float(bundle.get("world_height", 1.0)))
    content_w = max(1.0, float(rect_w))
    content_h = max(1.0, float(rect_h))
    scale = min(content_w / world_width, content_h / world_height)
    draw_w = world_width * scale
    draw_h = world_height * scale
    origin_x = (content_w - draw_w) * 0.5
    origin_y = (content_h - draw_h) * 0.5
    return origin_x, origin_y, scale


# Each cache entry is a list of horizontal pixel runs:
# ``(x, y, run_length, (r, g, b))``. Replaying via ``canvas.hline`` is a
# few hundred native calls rather than the ~750 pixel writes that a raw
# bytes buffer would require, which is what previously dragged the Pi's
# refresh down to ~1 fps with a hero flight on screen.
_RouteRun = tuple[int, int, int, "Color"]
_RENDER_CACHE: "OrderedDict[tuple, list[_RouteRun]]" = OrderedDict()


def _cache_get(key: tuple) -> list[_RouteRun] | None:
    cached = _RENDER_CACHE.get(key)
    if cached is not None:
        _RENDER_CACHE.move_to_end(key)
    return cached


def _cache_put(key: tuple, value: list[_RouteRun]) -> None:
    _RENDER_CACHE[key] = value
    _RENDER_CACHE.move_to_end(key)
    while len(_RENDER_CACHE) > _RENDER_CACHE_MAX:
        _RENDER_CACHE.popitem(last=False)


def _encode_runs(canvas: PixelCanvas, width: int, height: int) -> list[_RouteRun]:
    """RGB byte buffer → list of (x, y, run_length, color) horizontal runs.

    Adjacent same-coloured pixels in a row collapse to a single run, so a
    typical 38×20 map (mostly green land + some blue water blob) goes
    from 760 pixel writes to roughly 100–200 ``hline`` calls per replay.
    """
    pixels = canvas.to_bytes()
    runs: list[_RouteRun] = []
    for y in range(height):
        row_base = y * width * 3
        x = 0
        while x < width:
            base = row_base + x * 3
            r = pixels[base]
            g = pixels[base + 1]
            b = pixels[base + 2]
            run_start = x
            x += 1
            while x < width:
                base2 = row_base + x * 3
                if pixels[base2] == r and pixels[base2 + 1] == g and pixels[base2 + 2] == b:
                    x += 1
                else:
                    break
            runs.append((run_start, y, x - run_start, (r, g, b)))
    return runs


def _bundle_signature(bundle: dict[str, Any]) -> tuple:
    """Cheap, hashable fingerprint of the tile bundle.

    The actual feature dicts are too deep to hash in a hot path, so we
    summarize by zoom + each tile's (x, y, feature counts). Two bundles
    with the same signature render to the same pixels for our purposes.
    """
    parts: list = [int(bundle.get("zoom", 0))]
    for tile in bundle.get("tiles", []):
        data = tile.get("data") or {}
        water = (data.get("water") or {}).get("features") or []
        admin = (data.get("admin") or {}).get("features") or []
        parts.append((int(tile.get("x", 0)), int(tile.get("y", 0)), len(water), len(admin)))
    return tuple(parts)


def _projection_params(
    bundle: dict[str, Any],
    rect_w: int,
    rect_h: int,
    origin_x: float,
    origin_y: float,
) -> tuple[float, float, float, float]:
    """Bundle projection collapsed to (offset_x, offset_y, scale, scale).

    A vertex at world coords (wx, wy) maps to screen coords
    ``(offset_x + wx * scale, offset_y + wy * scale)``. The two scales
    are returned separately so callers can plug straight into the inner
    loop without recomputing — although in practice they're equal because
    we use ``min(...)`` in :func:`_projection_origin`.
    """
    min_world_x = float(bundle.get("min_world_x", 0.0))
    min_world_y = float(bundle.get("min_world_y", 0.0))
    world_width = max(1e-9, float(bundle.get("world_width", 1.0)))
    world_height = max(1e-9, float(bundle.get("world_height", 1.0)))
    content_w = max(1.0, float(rect_w))
    content_h = max(1.0, float(rect_h))
    scale = min(content_w / world_width, content_h / world_height)
    return (
        origin_x - min_world_x * scale,
        origin_y - min_world_y * scale,
        scale,
        scale,
    )


def _draw_water_polygons(
    target: PixelCanvas,
    bundle: dict[str, Any],
    color: Color,
    origin_x: float,
    origin_y: float,
    rect_w: int,
    rect_h: int,
) -> None:
    """Fill water polygons. Skips lone waterway LineStrings — at 40-px
    resolution they'd just speckle without conveying anything.
    """
    base_x, base_y, scale_x, scale_y = _projection_params(
        bundle, rect_w, rect_h, origin_x, origin_y,
    )
    for tile in bundle.get("tiles", []):
        data = tile.get("data") or {}
        tile_x = int(tile.get("x_unwrapped", tile.get("x", 0)))
        tile_y = int(tile.get("y", 0))
        layer = data.get("water")
        if not layer:
            continue
        extent = max(1, int(layer.get("extent", 4096)))
        inv_extent = 1.0 / extent
        # Per-tile constants combine with per-bundle scale so each vertex
        # only pays a multiply + an add.
        tile_offset_x = base_x + tile_x * scale_x
        tile_offset_y = base_y + tile_y * scale_y
        sx = scale_x * inv_extent
        sy = scale_y * inv_extent
        for feature in layer.get("features", []):
            geometry = feature.get("geometry", {})
            geom_type = geometry.get("type")
            coords = geometry.get("coordinates", [])
            if geom_type == "Polygon":
                rings = [coords]
            elif geom_type == "MultiPolygon":
                rings = list(coords)
            else:
                continue
            for poly in rings:
                if not poly:
                    continue
                outer_ring = [
                    (tile_offset_x + point[0] * sx, tile_offset_y + point[1] * sy)
                    for point in poly[0]
                ]
                holes = [
                    [
                        (tile_offset_x + point[0] * sx, tile_offset_y + point[1] * sy)
                        for point in hole
                    ]
                    for hole in poly[1:]
                ]
                _fill_polygon(target, outer_ring, holes, color, rect_w, rect_h)


def _draw_admin_lines(
    target: PixelCanvas,
    bundle: dict[str, Any],
    color: Color,
    origin_x: float,
    origin_y: float,
    rect_w: int,
    rect_h: int,
) -> None:
    """Draw admin LineStrings (state and country boundaries) only."""
    zoom = int(bundle.get("zoom", 4))
    base_x, base_y, scale_x, scale_y = _projection_params(
        bundle, rect_w, rect_h, origin_x, origin_y,
    )
    for tile in bundle.get("tiles", []):
        data = tile.get("data") or {}
        admin = data.get("admin")
        if not admin:
            continue
        extent = max(1, int(admin.get("extent", 4096)))
        tile_x = int(tile.get("x_unwrapped", tile.get("x", 0)))
        tile_y = int(tile.get("y", 0))
        tile_offset_x = base_x + tile_x * scale_x
        tile_offset_y = base_y + tile_y * scale_y
        inv_extent = 1.0 / extent
        sx = scale_x * inv_extent
        sy = scale_y * inv_extent
        for feature in admin.get("features", []):
            props = feature.get("properties") or {}
            if not _admin_visible(props, zoom):
                continue
            geometry = feature.get("geometry", {})
            geom_type = geometry.get("type")
            coords = geometry.get("coordinates", [])
            if geom_type == "LineString":
                _draw_polyline(target, coords, tile_offset_x, tile_offset_y, sx, sy, color)
            elif geom_type == "MultiLineString":
                for line in coords:
                    _draw_polyline(target, line, tile_offset_x, tile_offset_y, sx, sy, color)


def _draw_polyline(
    target: PixelCanvas,
    points: list[list[float]],
    base_x: float,
    base_y: float,
    sx: float,
    sy: float,
    color: Color,
) -> None:
    """Draw a polyline using a precomputed affine projection (no dict lookups)."""
    if len(points) < 2:
        return
    px0, py0 = points[0]
    x_prev = int(round(base_x + px0 * sx))
    y_prev = int(round(base_y + py0 * sy))
    for i in range(1, len(points)):
        pxi, pyi = points[i]
        x_next = int(round(base_x + pxi * sx))
        y_next = int(round(base_y + pyi * sy))
        _draw_line(target, x_prev, y_prev, x_next, y_next, color)
        x_prev = x_next
        y_prev = y_next


def _admin_visible(props: dict[str, Any], zoom: int) -> bool:
    """Show country borders always; show state lines once we're zoomed in."""
    raw = props.get("admin_level")
    try:
        level = int(str(raw))
    except (TypeError, ValueError):
        return True
    if level <= 2:
        return True
    if level <= 4:
        return zoom >= 4
    return zoom >= 7


def _fill_polygon(
    target: PixelCanvas,
    outer: list[tuple[float, float]],
    holes: list[list[tuple[float, float]]],
    color: Color,
    rect_w: int,
    rect_h: int,
) -> None:
    """Even-odd scanline fill with hole support, one ``hline`` call per span.

    Replaces the previous O(pixels × ring_size) point-in-polygon loop.
    For our routes a single 38×20 cache fill is on the order of 100×
    faster — bounding the cache-miss frame on the Pi to a few ms instead
    of half a second.
    """
    if len(outer) < 3:
        return
    min_y = max(0, int(min(p[1] for p in outer)))
    max_y = min(rect_h - 1, int(math.ceil(max(p[1] for p in outer))))
    if max_y < min_y:
        return

    rings: list[list[tuple[float, float]]] = [outer]
    rings.extend(h for h in holes if len(h) >= 3)

    for y in range(min_y, max_y + 1):
        py = y + 0.5
        intersections: list[float] = []
        for ring in rings:
            n = len(ring)
            j = n - 1
            for i in range(n):
                xi, yi = ring[i]
                xj, yj = ring[j]
                if (yi > py) != (yj > py):
                    denom = yj - yi
                    if denom == 0:
                        denom = 1e-9
                    intersections.append((xj - xi) * (py - yi) / denom + xi)
                j = i
        if len(intersections) < 2:
            continue
        intersections.sort()
        # Pair up consecutive intersections into fill spans (even-odd rule).
        for k in range(0, len(intersections) - 1, 2):
            x_start = intersections[k]
            x_end = intersections[k + 1]
            ix_start = max(0, int(math.ceil(x_start - 0.5)))
            ix_end = min(rect_w - 1, int(math.floor(x_end - 0.5)))
            if ix_end >= ix_start:
                target.hline(ix_start, y, ix_end - ix_start + 1, color)


def _draw_dot(canvas: PixelCanvas, x: int, y: int, color: Color) -> None:
    """2x2 dot anchored at (x, y) — visible at small sizes without smearing."""
    canvas.pixel(x, y, color)
    canvas.pixel(x + 1, y, color)
    canvas.pixel(x, y + 1, color)
    canvas.pixel(x + 1, y + 1, color)


@dataclass
class RouteMap(Map):
    """Map with a flown-path overlay and aircraft marker.

    Inherits ``Map``'s constructor for color/zoom field plumbing but does
    its own simplified rendering (water + admin only) so the basemap is
    legible at 40-pixel-wide and the per-frame cost stays bounded.

    The cache holds the basemap (water + admin) only — origin/destination
    dots, the flown path, and the live plane marker are stamped on top
    each frame so a new track point doesn't trigger a multi-tile rebuild.
    """

    origin_lat: float | None = None
    origin_lon: float | None = None
    dest_lat: float | None = None
    dest_lon: float | None = None
    plane_lat: float | None = None
    plane_lon: float | None = None
    # Ordered list of ``(lat, lon)`` points the aircraft has been observed
    # at, oldest first. Used for the flown-path polyline; an empty list
    # falls back to a great-circle interpolation between origin and the
    # current plane position.
    path_points: list[tuple[float, float]] | None = None
    line_color: Color = colors.WHITE
    endpoint_color: Color = colors.WHITE
    plane_color: Color = (255, 60, 60)

    def draw(self, canvas: PixelCanvas, rect: Rect) -> None:
        if rect.width <= 2 or rect.height <= 2:
            return

        # 1-pixel bg frame: draw the perimeter only so we don't overdraw the
        # whole content rect with bg just to overwrite it again with the
        # cached map (~290 µs/frame on the Mac of pure overdraw).
        right = rect.x + rect.width - 1
        bottom = rect.y + rect.height - 1
        canvas.hline(rect.x, rect.y, rect.width, self.bg)
        canvas.hline(rect.x, bottom, rect.width, self.bg)
        canvas.vline(rect.x, rect.y + 1, max(0, rect.height - 2), self.bg)
        canvas.vline(right, rect.y + 1, max(0, rect.height - 2), self.bg)

        content = Rect(rect.x + 1, rect.y + 1, rect.width - 2, rect.height - 2)
        if content.width <= 0 or content.height <= 0:
            return

        if (
            self.origin_lat is None
            or self.origin_lon is None
            or self.dest_lat is None
            or self.dest_lon is None
        ):
            canvas.rect(content, fill=self.land_color, outline=None)
            return

        bundle = self.tile_data if isinstance(self.tile_data, dict) else None
        cached_basemap = self._get_cached_basemap(content.width, content.height, bundle)
        if cached_basemap is not None:
            _replay_runs(canvas, content, cached_basemap)
        else:
            canvas.rect(content, fill=self.land_color, outline=None)

        if bundle is None:
            return

        ox, oy, _ = _projection_origin(bundle, content.width - 1, content.height - 1)

        def project(lat: float, lon: float) -> tuple[int, int]:
            px, py = _project_lat_lon(
                lat, lon, bundle, content.width - 1, content.height - 1, ox, oy,
            )
            return content.x + int(round(px)), content.y + int(round(py))

        # Build the polyline: known origin → great-circle gap up to the
        # first observed point → linear segments through the recorded
        # samples → current plane position. When we've never seen this
        # aircraft (path_points empty), fall back to a single great
        # circle from origin to current position so something is shown.
        with canvas.clip(content):
            self._draw_path(canvas, project)
            ox_screen = project(self.origin_lat, self.origin_lon)
            dx_screen = project(self.dest_lat, self.dest_lon)
            _draw_dot(canvas, ox_screen[0], ox_screen[1], self.endpoint_color)
            _draw_dot(canvas, dx_screen[0], dx_screen[1], self.endpoint_color)

            if self.plane_lat is not None and self.plane_lon is not None:
                px, py = project(self.plane_lat, self.plane_lon)
                _draw_dot(canvas, px, py, self.plane_color)

    def _draw_path(self, canvas: PixelCanvas, project: Any) -> None:
        """Connect origin → flown samples → current plane position.

        ``project`` is a closure that maps (lat, lon) → integer pixel
        coords on the live canvas. The caller has already pushed a clip
        rect for the map content area.
        """
        if self.origin_lat is None or self.origin_lon is None:
            return
        observed = list(self.path_points or [])

        # If we have no breadcrumbs yet, stub in the current plane
        # position so the line is at least one segment long.
        if not observed and self.plane_lat is not None and self.plane_lon is not None:
            observed.append((self.plane_lat, self.plane_lon))

        if not observed:
            return

        # Great-circle interpolation from the origin to the first
        # observed sample bridges the part of the flight we missed.
        first_lat, first_lon = observed[0]
        gap_pts = _great_circle_points(
            self.origin_lat, self.origin_lon, first_lat, first_lon,
        )
        # ``gap_pts`` ends at ``observed[0]``, so skip that index in
        # observed to avoid drawing a zero-length segment.
        polyline_pts = gap_pts + observed[1:]

        prev: tuple[int, int] | None = None
        for lat, lon in polyline_pts:
            x, y = project(lat, lon)
            if prev is not None and (x != prev[0] or y != prev[1]):
                _draw_line(canvas, prev[0], prev[1], x, y, self.line_color)
            prev = (x, y)

    def _get_cached_basemap(
        self,
        width: int,
        height: int,
        bundle: dict[str, Any] | None,
    ) -> list[_RouteRun] | None:
        """Return cached basemap RLE runs (water + admin only).

        The path and endpoints are drawn each frame so adding a new
        breadcrumb doesn't invalidate the basemap cache. ``bundle`` may
        be tile-less while tiles are still loading — in that case we
        return runs covering a solid land-coloured rect so the live
        path can still draw on top of something.
        """
        bundle_sig = _bundle_signature(bundle) if bundle is not None else ()
        key = (
            int(width),
            int(height),
            self.land_color,
            self.water_color,
            self.border_color,
            bundle_sig,
        )
        cached = _cache_get(key)
        if cached is not None:
            return cached

        base = PixelCanvas(width, height, self.land_color)
        if bundle is not None and bundle.get("tiles"):
            origin_x, origin_y, _ = _projection_origin(bundle, width - 1, height - 1)
            _draw_water_polygons(
                base, bundle, self.water_color, origin_x, origin_y,
                width - 1, height - 1,
            )
            _draw_admin_lines(
                base, bundle, self.border_color, origin_x, origin_y,
                width - 1, height - 1,
            )

        runs = _encode_runs(base, width, height)
        _cache_put(key, runs)
        return runs


def _replay_runs(canvas: PixelCanvas, rect: Rect, runs: list[_RouteRun]) -> None:
    """Stamp a cached run list back onto the live canvas via ``hline`` calls."""
    if rect.width <= 0 or rect.height <= 0:
        return
    with canvas.clip(rect):
        for x, y, run_w, color in runs:
            canvas.hline(rect.x + x, rect.y + y, run_w, color)
