"""Map viewport proofs."""

from __future__ import annotations

from dataclasses import dataclass

from ui_lab.analysis import basic_analysis
from ui_lab.canvas import PixelCanvas, Rect
from ui_lab.pages.base import FeaturePage, PageFrame
from ui_lab.pages.common import draw_page_shell, full_width_rect, draw_surface
from ui_lab.palette import Palette, rgb


@dataclass(frozen=True)
class MapViewport:
    center_lat: float
    center_lon: float
    zoom: float
    width: int
    height: int

    def project(self, lat: float, lon: float) -> tuple[int, int]:
        scale = 2.2 * (2 ** self.zoom)
        x = int(self.width / 2 + (lon - self.center_lon) * scale)
        y = int(self.height / 2 - (lat - self.center_lat) * scale * 1.4)
        return x, y


def _clamp_point(x: int, y: int, rect: Rect, margin: int = 0) -> tuple[int, int]:
    return (
        max(rect.x + margin, min(rect.right - 1 - margin, x)),
        max(rect.y + margin, min(rect.bottom - 1 - margin, y)),
    )


class MapPage(FeaturePage):
    key = "map"
    title = "Map"
    animated = False

    def __init__(self) -> None:
        self.palette = Palette()
        self.land = rgb("#1d3a2d")
        self.grid = rgb("#163047")
        self.route = rgb("#5ee1ff")

    def render(self, canvas: PixelCanvas, frame: PageFrame) -> None:
        palette = self.palette
        draw_page_shell(canvas, palette, "MAP", f"{frame.index + 1:02d}/{frame.total:02d}")
        panel = full_width_rect(20, 32)
        draw_surface(canvas, panel, palette)
        inner = Rect(panel.x + 1, panel.y + 1, panel.width - 2, panel.height - 2)
        canvas.rect(inner, fill=palette.background)
        for x in range(inner.x + 10, inner.right, 18):
            canvas.vline(x, inner.y, inner.height, self.grid)
        for y in range(inner.y + 7, inner.bottom, 13):
            canvas.hline(inner.x, y, inner.width, self.grid)
        viewport = MapViewport(41.6, -88.1, 1.6, inner.width, inner.height)
        route_points = [
            (42.7, -89.0),
            (41.6, -88.1),
            (41.1, -86.6),
            (40.0, -88.9),
        ]
        pin_points = route_points
        route = []
        for lat, lon in route_points:
            px, py = viewport.project(lat, lon)
            route.append(_clamp_point(inner.x + px, inner.y + py, inner, margin=2))
        canvas.polyline(route, self.route)
        for lat, lon in pin_points:
            px, py = viewport.project(lat, lon)
            x, y = _clamp_point(inner.x + px, inner.y + py, inner, margin=3)
            canvas.circle(x, y, 1, palette.text, fill=True)
        focus_px, focus_py = viewport.project(41.6, -88.1)
        focus_x, focus_y = _clamp_point(inner.x + focus_px, inner.y + focus_py, inner, margin=4)
        canvas.circle(focus_x, focus_y, 2, palette.text, fill=True)
        canvas.circle(focus_x, focus_y, 5, palette.text, fill=False)

    def analyze(self, canvas: PixelCanvas) -> dict[str, object]:
        palette = self.palette
        allowed = {
            palette.background,
            palette.panel,
            palette.panel_edge,
            palette.text,
            palette.text_dim,
            palette.error,
            self.route,
            self.grid,
            self.land,
        }
        return basic_analysis(canvas, allowed)
