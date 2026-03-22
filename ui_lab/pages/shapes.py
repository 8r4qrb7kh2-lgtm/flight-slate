"""Shape primitive proofs."""

from __future__ import annotations

from ui_lab.analysis import basic_analysis
from ui_lab.assets import icon_registry
from ui_lab.bitmap_font import FONT_5X7
from ui_lab.canvas import PixelCanvas, Rect
from ui_lab.pages.base import FeaturePage, PageFrame
from ui_lab.pages.common import draw_bitmap_centered, draw_page_shell, draw_surface, full_width_rect, three_column_rects
from ui_lab.palette import Palette


class ShapesPage(FeaturePage):
    key = "shapes"
    title = "Shapes"
    animated = False

    def __init__(self) -> None:
        self.palette = Palette()
        self.icons = icon_registry()

    def render(self, canvas: PixelCanvas, frame: PageFrame) -> None:
        palette = self.palette
        draw_page_shell(canvas, palette, "SHAPES", f"{frame.index + 1:02d}/{frame.total:02d}")
        line_box, dot_box, pin_box = three_column_rects(24, 12)
        route_box = full_width_rect(46, 12)
        for box in (line_box, dot_box, pin_box, route_box):
            draw_surface(canvas, box, palette)

        FONT_5X7.draw_boxed(canvas, line_box.x, 18, line_box.width, "LINE", palette.accent, align="center")
        canvas.line(line_box.x + 7, line_box.y + 6, line_box.right - 11, line_box.y + 6, palette.accent)
        canvas.line(line_box.right - 11, line_box.y + 6, line_box.right - 7, line_box.y + 4, palette.accent)
        canvas.line(line_box.right - 11, line_box.y + 6, line_box.right - 7, line_box.y + 8, palette.accent)

        FONT_5X7.draw_boxed(canvas, dot_box.x, 18, dot_box.width, "DOT", palette.success, align="center")
        canvas.circle(dot_box.x + 14, dot_box.y + 6, 2, palette.success, fill=False)
        canvas.circle(dot_box.right - 13, dot_box.y + 6, 1, palette.success, fill=True)

        FONT_5X7.draw_boxed(canvas, pin_box.x, 18, pin_box.width, "PIN", palette.accent_alt, align="center")
        draw_bitmap_centered(self.icons["pin"], canvas, Rect(pin_box.x + 10, pin_box.y + 1, 16, 10))

        FONT_5X7.draw_boxed(canvas, route_box.x, 40, route_box.width, "ROUTE", palette.text_dim, align="center")
        canvas.line(route_box.x + 16, route_box.y + 6, route_box.x + 40, route_box.y + 6, palette.text)
        canvas.line(route_box.x + 40, route_box.y + 6, route_box.x + 64, route_box.y + 4, palette.text)
        canvas.line(route_box.x + 64, route_box.y + 4, route_box.x + 90, route_box.y + 6, palette.text)
        canvas.circle(route_box.x + 40, route_box.y + 6, 1, palette.text, fill=True)
        canvas.circle(route_box.x + 64, route_box.y + 4, 1, palette.text, fill=True)

    def analyze(self, canvas: PixelCanvas) -> dict[str, object]:
        palette = self.palette
        allowed = {
            palette.background,
            palette.panel,
            palette.panel_edge,
            palette.text,
            palette.text_dim,
            palette.accent,
            palette.accent_alt,
            palette.error,
            palette.success,
        }
        return basic_analysis(canvas, allowed)
