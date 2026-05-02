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


_RENDER_CACHE: "OrderedDict[tuple, bytes]" = OrderedDict()


def _cache_get(key: tuple) -> bytes | None:
    cached = _RENDER_CACHE.get(key)
    if cached is not None:
        _RENDER_CACHE.move_to_end(key)
    return cached


def _cache_put(key: tuple, value: bytes) -> None:
    _RENDER_CACHE[key] = value
    _RENDER_CACHE.move_to_end(key)
    while len(_RENDER_CACHE) > _RENDER_CACHE_MAX:
        _RENDER_CACHE.popitem(last=False)


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


def _draw_water_polygons(
    target: PixelCanvas,
    bundle: dict[str, Any],
    color: Color,
    origin_x: float,
    origin_y: float,
    rect_w: int,
    rect_h: int,
) -> None:
    """Fill water/waterway polygons from each tile in the bundle.

    Skips lone water LineStrings (small streams) — at 40-pixel resolution
    they'd just speckle the map without conveying anything useful.
    """
    zoom = int(bundle.get("zoom", 4))
    n = max(1, 2**zoom)
    for tile in bundle.get("tiles", []):
        data = tile.get("data") or {}
        tile_x = int(tile.get("x_unwrapped", tile.get("x", 0)))
        tile_y = int(tile.get("y", 0))
        for layer_name in ("water", "waterway"):
            layer = data.get(layer_name)
            if not layer:
                continue
            extent = max(1, int(layer.get("extent", 4096)))
            for feature in layer.get("features", []):
                geometry = feature.get("geometry", {})
                geom_type = geometry.get("type")
                coords = geometry.get("coordinates", [])
                rings: list[list[list[float]]] = []
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
                        _tile_to_pixel(
                            point, extent, tile_x, tile_y, bundle,
                            rect_w, rect_h, origin_x, origin_y,
                        )
                        for point in poly[0]
                    ]
                    holes = [
                        [
                            _tile_to_pixel(
                                point, extent, tile_x, tile_y, bundle,
                                rect_w, rect_h, origin_x, origin_y,
                            )
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
    for tile in bundle.get("tiles", []):
        data = tile.get("data") or {}
        admin = data.get("admin")
        if not admin:
            continue
        extent = max(1, int(admin.get("extent", 4096)))
        tile_x = int(tile.get("x_unwrapped", tile.get("x", 0)))
        tile_y = int(tile.get("y", 0))
        for feature in admin.get("features", []):
            props = feature.get("properties") or {}
            if not _admin_visible(props, zoom):
                continue
            geometry = feature.get("geometry", {})
            geom_type = geometry.get("type")
            coords = geometry.get("coordinates", [])
            if geom_type == "LineString":
                _draw_line_in_tile(
                    target, coords, extent, tile_x, tile_y, bundle, color,
                    origin_x, origin_y, rect_w, rect_h,
                )
            elif geom_type == "MultiLineString":
                for line in coords:
                    _draw_line_in_tile(
                        target, line, extent, tile_x, tile_y, bundle, color,
                        origin_x, origin_y, rect_w, rect_h,
                    )


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


def _tile_to_pixel(
    point: list[float],
    extent: int,
    tile_x: int,
    tile_y: int,
    bundle: dict[str, Any],
    rect_w: int,
    rect_h: int,
    origin_x: float,
    origin_y: float,
) -> tuple[float, float]:
    denom = max(1, extent - 1)
    local_x = min(max(point[0] / denom, 0.0), 1.0)
    local_y = min(max(point[1] / denom, 0.0), 1.0)
    world_x = tile_x + local_x
    world_y = tile_y + local_y
    min_world_x = float(bundle.get("min_world_x", 0.0))
    min_world_y = float(bundle.get("min_world_y", 0.0))
    world_width = max(1e-9, float(bundle.get("world_width", 1.0)))
    world_height = max(1e-9, float(bundle.get("world_height", 1.0)))
    content_w = max(1.0, float(rect_w))
    content_h = max(1.0, float(rect_h))
    scale = min(content_w / world_width, content_h / world_height)
    return (
        origin_x + ((world_x - min_world_x) * scale),
        origin_y + ((world_y - min_world_y) * scale),
    )


def _draw_line_in_tile(
    target: PixelCanvas,
    line: list[list[float]],
    extent: int,
    tile_x: int,
    tile_y: int,
    bundle: dict[str, Any],
    color: Color,
    origin_x: float,
    origin_y: float,
    rect_w: int,
    rect_h: int,
) -> None:
    if len(line) < 2:
        return
    pts = [
        _tile_to_pixel(p, extent, tile_x, tile_y, bundle, rect_w, rect_h, origin_x, origin_y)
        for p in line
    ]
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        _draw_line(target, int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1)), color)


def _fill_polygon(
    target: PixelCanvas,
    outer: list[tuple[float, float]],
    holes: list[list[tuple[float, float]]],
    color: Color,
    rect_w: int,
    rect_h: int,
) -> None:
    if len(outer) < 3:
        return
    min_x = max(0, int(min(p[0] for p in outer)))
    max_x = min(rect_w - 1, int(max(p[0] for p in outer)))
    min_y = max(0, int(min(p[1] for p in outer)))
    max_y = min(rect_h - 1, int(max(p[1] for p in outer)))
    for y in range(min_y, max_y + 1):
        for x in range(min_x, max_x + 1):
            px = x + 0.5
            py = y + 0.5
            if not _point_in_ring(px, py, outer):
                continue
            if any(_point_in_ring(px, py, hole) for hole in holes):
                continue
            target.pixel(x, y, color)


def _point_in_ring(px: float, py: float, ring: list[tuple[float, float]]) -> bool:
    if len(ring) < 3:
        return False
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        intersects = ((yi > py) != (yj > py)) and (
            px < ((xj - xi) * (py - yi) / ((yj - yi) if (yj - yi) != 0 else 1e-9) + xi)
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def _draw_dot(canvas: PixelCanvas, x: int, y: int, color: Color) -> None:
    """2x2 dot anchored at (x, y) — visible at small sizes without smearing."""
    canvas.pixel(x, y, color)
    canvas.pixel(x + 1, y, color)
    canvas.pixel(x, y + 1, color)
    canvas.pixel(x + 1, y + 1, color)


@dataclass
class RouteMap(Map):
    """Map with a great-circle path and aircraft marker overlay.

    Inherits ``Map``'s constructor for color/zoom field plumbing but does
    its own simplified rendering (water + admin only) so the basemap is
    legible at 40-pixel-wide and the per-frame cost stays bounded.
    """

    origin_lat: float | None = None
    origin_lon: float | None = None
    dest_lat: float | None = None
    dest_lon: float | None = None
    plane_lat: float | None = None
    plane_lon: float | None = None
    line_color: Color = colors.WHITE
    endpoint_color: Color = colors.WHITE
    plane_color: Color = (255, 60, 60)

    def draw(self, canvas: PixelCanvas, rect: Rect) -> None:
        if rect.width <= 2 or rect.height <= 2:
            return

        # Outer 1-pixel bg frame so the content sits inset from the column edge.
        canvas.rect(rect, fill=self.bg, outline=None)
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
        cached_pixels = self._get_cached_base(content.width, content.height, bundle)
        if cached_pixels is not None:
            self._blit_cached(canvas, content, cached_pixels)
        else:
            canvas.rect(content, fill=self.land_color, outline=None)

        # Plane dot is the only thing that moves between frames; draw it on
        # top of the cached base every render.
        if self.plane_lat is not None and self.plane_lon is not None and bundle is not None:
            origin_x, origin_y, _ = _projection_origin(bundle, content.width - 1, content.height - 1)
            px, py = _project_lat_lon(
                self.plane_lat,
                self.plane_lon,
                bundle,
                content.width - 1,
                content.height - 1,
                origin_x,
                origin_y,
            )
            _draw_dot(
                canvas,
                content.x + int(round(px)),
                content.y + int(round(py)),
                self.plane_color,
            )

    def _get_cached_base(
        self,
        width: int,
        height: int,
        bundle: dict[str, Any] | None,
    ) -> bytes | None:
        """Return cached base pixels (water + admin + path + endpoints).

        Builds on cache miss using a fresh off-screen canvas, stores the
        rendered bytes keyed by route + size + bundle fingerprint, and
        returns them. Returns None only if the route lacks endpoints.
        """
        if (
            self.origin_lat is None
            or self.origin_lon is None
            or self.dest_lat is None
            or self.dest_lon is None
        ):
            return None

        bundle_sig = _bundle_signature(bundle) if bundle is not None else ()
        key = (
            round(self.origin_lat, 3),
            round(self.origin_lon, 3),
            round(self.dest_lat, 3),
            round(self.dest_lon, 3),
            int(width),
            int(height),
            self.land_color,
            self.water_color,
            self.border_color,
            self.line_color,
            self.endpoint_color,
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

        if bundle is not None:
            origin_x, origin_y, _ = _projection_origin(bundle, width - 1, height - 1)
            path = _great_circle_points(
                self.origin_lat, self.origin_lon,
                self.dest_lat, self.dest_lon,
            )
            screen = [
                _project_lat_lon(lat, lon, bundle, width - 1, height - 1, origin_x, origin_y)
                for lat, lon in path
            ]
            for index in range(len(screen) - 1):
                x0, y0 = screen[index]
                x1, y1 = screen[index + 1]
                _draw_line(
                    base,
                    int(round(x0)), int(round(y0)),
                    int(round(x1)), int(round(y1)),
                    self.line_color,
                )
            for lat, lon in (
                (self.origin_lat, self.origin_lon),
                (self.dest_lat, self.dest_lon),
            ):
                ex, ey = _project_lat_lon(lat, lon, bundle, width - 1, height - 1, origin_x, origin_y)
                _draw_dot(base, int(round(ex)), int(round(ey)), self.endpoint_color)

        pixels = base.to_bytes()
        _cache_put(key, pixels)
        return pixels

    @staticmethod
    def _blit_cached(canvas: PixelCanvas, rect: Rect, pixels: bytes) -> None:
        """Copy a cached RGB byte buffer back onto the live canvas, pixel by pixel."""
        if rect.width <= 0 or rect.height <= 0:
            return
        expected = rect.width * rect.height * 3
        if len(pixels) != expected:
            return
        with canvas.clip(rect):
            row_stride = rect.width * 3
            for y in range(rect.height):
                row_base = y * row_stride
                for x in range(rect.width):
                    base = row_base + (x * 3)
                    canvas.pixel(
                        rect.x + x,
                        rect.y + y,
                        (pixels[base], pixels[base + 1], pixels[base + 2]),
                    )
