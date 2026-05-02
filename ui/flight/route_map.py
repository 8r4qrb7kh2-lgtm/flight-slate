"""Tiny route-preview map widget with great-circle path overlay.

Wraps :class:`ui.core.widgets.Map` to draw the same Mapbox vector tiles,
then overlays an origin → destination great-circle path in white plus a
small marker for the live aircraft position. The base map renders
identically to the demo map page so colour treatment stays consistent.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from ui.core.canvas import PixelCanvas, Rect
from ui.core.colors import Color, colors
from ui.core.widgets import Map

from ui.flight.maps import lon_lat_to_world_tile


# Ground-track segments. 32 is plenty for transcontinental hops; the line on
# a 40-pixel map only ever shows a few-pixel arc at most.
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


def _draw_line_aa(
    canvas: PixelCanvas,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    color: Color,
) -> None:
    """1-pixel-wide Bresenham line. Local copy avoids importing private helpers."""
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


@dataclass
class RouteMap(Map):
    """Map with a great-circle path and aircraft marker overlay.

    Inherits from ``Map`` so the base land/water/road rendering is reused
    verbatim. The ``draw`` override paints the route line on top of the
    base layer and skips the loading spinner — when tiles are missing we
    just show the bare bg colour with the line, which still tells the
    viewer the route shape without waiting for the network.
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
        super().draw(canvas, rect)
        if rect.width <= 4 or rect.height <= 4:
            return

        bundle = self.tile_data if isinstance(self.tile_data, dict) else None
        if bundle is None or "tiles" not in bundle:
            return
        if (
            self.origin_lat is None
            or self.origin_lon is None
            or self.dest_lat is None
            or self.dest_lon is None
        ):
            return

        # Match Map.draw's 1-pixel inset so the overlay sits inside the
        # bg-colored border instead of overwriting it.
        content = Rect(
            rect.x + 1,
            rect.y + 1,
            max(0, rect.width - 2),
            max(0, rect.height - 2),
        )
        if content.width <= 0 or content.height <= 0:
            return

        path = _great_circle_points(
            self.origin_lat,
            self.origin_lon,
            self.dest_lat,
            self.dest_lon,
        )
        screen = [
            self._project(lat, lon, content, bundle) for lat, lon in path
        ]

        with canvas.clip(content):
            for index in range(len(screen) - 1):
                x0, y0 = screen[index]
                x1, y1 = screen[index + 1]
                _draw_line_aa(
                    canvas,
                    int(round(x0)),
                    int(round(y0)),
                    int(round(x1)),
                    int(round(y1)),
                    self.line_color,
                )

            # Endpoint markers: 2x2 dots so they read as endpoints rather
            # than as part of the route line itself.
            for lat, lon in (
                (self.origin_lat, self.origin_lon),
                (self.dest_lat, self.dest_lon),
            ):
                ex, ey = self._project(lat, lon, content, bundle)
                _draw_dot(canvas, int(round(ex)), int(round(ey)), self.endpoint_color)

            if self.plane_lat is not None and self.plane_lon is not None:
                px, py = self._project(self.plane_lat, self.plane_lon, content, bundle)
                _draw_dot(canvas, int(round(px)), int(round(py)), self.plane_color)

    @staticmethod
    def _project(
        lat: float,
        lon: float,
        rect: Rect,
        bundle: dict[str, Any],
    ) -> tuple[float, float]:
        """Match Map's tile-bundle projection so overlays land on the same pixels."""
        zoom = int(bundle.get("zoom", 4))
        wx, wy = lon_lat_to_world_tile(lon, lat, zoom)
        min_world_x = float(bundle.get("min_world_x", 0.0))
        min_world_y = float(bundle.get("min_world_y", 0.0))
        world_width = max(1e-9, float(bundle.get("world_width", 1.0)))
        world_height = max(1e-9, float(bundle.get("world_height", 1.0)))

        content_w = max(1.0, float(rect.width - 1))
        content_h = max(1.0, float(rect.height - 1))
        scale = min(content_w / world_width, content_h / world_height)
        draw_w = world_width * scale
        draw_h = world_height * scale
        origin_x = rect.x + ((content_w - draw_w) * 0.5)
        origin_y = rect.y + ((content_h - draw_h) * 0.5)
        return (
            origin_x + ((wx - min_world_x) * scale),
            origin_y + ((wy - min_world_y) * scale),
        )


def _draw_dot(canvas: PixelCanvas, x: int, y: int, color: Color) -> None:
    """2x2 dot anchored at (x, y) — visible at small sizes without smearing."""
    canvas.pixel(x, y, color)
    canvas.pixel(x + 1, y, color)
    canvas.pixel(x, y + 1, color)
    canvas.pixel(x + 1, y + 1, color)
