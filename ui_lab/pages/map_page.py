"""Map viewport proofs."""

from __future__ import annotations

from dataclasses import dataclass

from ui_lab.analysis import basic_analysis
from ui_lab.assets import icon_registry
from ui_lab.bitmap_font import FONT_5X7
from ui_lab.canvas import PixelCanvas, Rect
from ui_lab.pages.base import FeaturePage, PageFrame
from ui_lab.pages.common import draw_footer_note, draw_page_shell, draw_surface
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


USA_POLY = (
    (49.0, -124.0),
    (42.0, -124.0),
    (34.0, -118.0),
    (29.0, -107.0),
    (27.0, -82.0),
    (35.0, -77.0),
    (42.0, -70.0),
    (49.0, -90.0),
    (49.0, -124.0),
)


class MapPage(FeaturePage):
    key = "map"
    title = "Map"
    animated = False

    def __init__(self) -> None:
        self.palette = Palette()
        self.icons = icon_registry()
        self.land = rgb("#1d3a2d")
        self.grid = rgb("#163047")
        self.route = rgb("#5ee1ff")

    def render(self, canvas: PixelCanvas, frame: PageFrame) -> None:
        palette = self.palette
        draw_page_shell(canvas, palette, "MAP", f"{frame.index + 1:02d}/{frame.total:02d}")
        panel = Rect(6, 18, 116, 40)
        draw_surface(canvas, panel, palette)
        viewport = MapViewport(40.0, -88.0, 1.4, panel.width - 2, panel.height - 2)
        inner = Rect(panel.x + 1, panel.y + 1, panel.width - 2, panel.height - 2)
        canvas.rect(inner, fill=palette.background)
        for x in range(inner.x + 8, inner.right, 16):
            canvas.vline(x, inner.y, inner.height, self.grid)
        for y in range(inner.y + 6, inner.bottom, 12):
            canvas.hline(inner.x, y, inner.width, self.grid)
        poly = []
        for lat, lon in USA_POLY:
            px, py = viewport.project(lat, lon)
            poly.append((inner.x + px, inner.y + py))
        canvas.polyline(poly, self.land, closed=True)
        dep = (40.6413, -73.7781)
        arr = (41.9742, -87.9073)
        ac = (41.3, -80.4)
        dep_p = viewport.project(*dep)
        arr_p = viewport.project(*arr)
        ac_p = viewport.project(*ac)
        dep_xy = (inner.x + dep_p[0], inner.y + dep_p[1])
        arr_xy = (inner.x + arr_p[0], inner.y + arr_p[1])
        ac_xy = (inner.x + ac_p[0], inner.y + ac_p[1])
        canvas.line(dep_xy[0], dep_xy[1], arr_xy[0], arr_xy[1], self.route)
        self.icons["pin"].draw(canvas, dep_xy[0] - 4, dep_xy[1] - 8)
        self.icons["pin"].draw(canvas, arr_xy[0] - 4, arr_xy[1] - 8)
        self.icons["plane"].draw(canvas, ac_xy[0] - 4, ac_xy[1] - 4)
        canvas.circle(ac_xy[0], ac_xy[1], 5, palette.text, fill=False)
        draw_footer_note(canvas, "FOCUS + PINS + ZOOM", palette, y=52)

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
