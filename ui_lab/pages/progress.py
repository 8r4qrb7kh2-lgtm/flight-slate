"""Progress indicator proofs."""

from __future__ import annotations

from ui_lab.analysis import basic_analysis
from ui_lab.bitmap_font import FONT_5X7
from ui_lab.canvas import PixelCanvas, Rect
from ui_lab.pages.base import FeaturePage, PageFrame
from ui_lab.pages.common import draw_page_shell, full_width_rect
from ui_lab.palette import Palette
from ui_lab.widgets import draw_progress_bar


class ProgressPage(FeaturePage):
    key = "progress"
    title = "Progress"
    animated = False

    def __init__(self) -> None:
        self.palette = Palette()
        self.fill_widths: list[int] = []

    def render(self, canvas: PixelCanvas, frame: PageFrame) -> None:
        palette = self.palette
        self.fill_widths = []
        draw_page_shell(canvas, palette, "PROGRESS", f"{frame.index + 1:02d}/{frame.total:02d}")
        FONT_5X7.render(canvas, 8, 18, "LINEAR", palette.accent)
        self.fill_widths.append(draw_progress_bar(canvas, full_width_rect(26, 8), 0.22, palette, palette.accent))
        FONT_5X7.render(canvas, 8, 38, "SEGMENT", palette.accent_alt)
        self.fill_widths.append(draw_progress_bar(canvas, full_width_rect(46, 8), 0.61, palette, palette.accent_alt, segmented=True))
        FONT_5X7.draw_boxed(canvas, 8, 54, 112, "22 / 61", palette.text_dim, align="center")

    def analyze(self, canvas: PixelCanvas) -> dict[str, object]:
        palette = self.palette
        allowed = {
            palette.background,
            palette.panel,
            palette.panel_edge,
            palette.text_dim,
            palette.text,
            palette.accent,
            palette.accent_alt,
        }
        return basic_analysis(canvas, allowed, fill_widths=self.fill_widths)
