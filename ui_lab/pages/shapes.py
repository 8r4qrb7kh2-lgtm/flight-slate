"""Shape primitive proofs."""

from __future__ import annotations

from ui_lab.analysis import basic_analysis
from ui_lab.assets import icon_registry
from ui_lab.bitmap_font import FONT_5X7
from ui_lab.canvas import PixelCanvas, Rect
from ui_lab.pages.base import FeaturePage, PageFrame
from ui_lab.pages.common import draw_footer_note, draw_page_shell, draw_surface
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
        draw_surface(canvas, Rect(8, 18, 112, 40), palette)
        canvas.line(14, 27, 50, 27, palette.accent)
        canvas.line(50, 27, 58, 23, palette.accent)
        canvas.line(50, 27, 58, 31, palette.accent)
        canvas.line(14, 42, 58, 52, palette.text)
        canvas.circle(86, 28, 4, palette.success, fill=False)
        canvas.circle(101, 28, 2, palette.success, fill=True)
        self.icons["pin"].draw(canvas, 76, 40)
        self.icons["plane"].draw(canvas, 96, 42)
        FONT_5X7.render(canvas, 16, 20, "LINE", palette.accent)
        FONT_5X7.render(canvas, 76, 20, "DOT PIN", palette.accent_alt)
        FONT_5X7.render(canvas, 16, 47, "ROUTE", palette.text_dim)
        draw_footer_note(canvas, "LINE / DOT / PIN / ROUTE", palette)

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
