"""Surface/container primitive proofs."""

from __future__ import annotations

from ui_lab.analysis import basic_analysis, row_color_count
from ui_lab.bitmap_font import FONT_5X7
from ui_lab.canvas import PixelCanvas, Rect
from ui_lab.pages.base import FeaturePage, PageFrame
from ui_lab.pages.common import draw_footer_note, draw_page_shell, draw_surface
from ui_lab.palette import Palette


class ContainerPage(FeaturePage):
    key = "container"
    title = "Container"
    animated = False

    def __init__(self) -> None:
        self.palette = Palette()

    def render(self, canvas: PixelCanvas, frame: PageFrame) -> None:
        palette = self.palette
        draw_page_shell(canvas, palette, "CONTAINER", f"{frame.index + 1:02d}/{frame.total:02d}")
        outer = Rect(8, 18, 112, 40)
        mid_left = Rect(14, 24, 46, 26)
        mid_right = Rect(68, 24, 46, 26)
        inner = Rect(21, 31, 32, 12)
        for box in (outer, mid_left, mid_right, inner):
            draw_surface(canvas, box, palette)
        FONT_5X7.draw_boxed(canvas, mid_left.x, 25, mid_left.width, "BASE", palette.accent, align="center")
        FONT_5X7.draw_boxed(canvas, mid_right.x, 25, mid_right.width, "NEST", palette.accent_alt, align="center")
        FONT_5X7.draw_boxed(canvas, inner.x, 34, inner.width, "EDGE", palette.text, align="center")
        FONT_5X7.draw_boxed(canvas, mid_right.x, 36, mid_right.width, "PAD", palette.text_dim, align="center")
        draw_footer_note(canvas, "SHARED PANEL + INSET", palette)

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
        }
        return basic_analysis(canvas, allowed, border_pixels=row_color_count(canvas, 18, palette.panel_edge))
