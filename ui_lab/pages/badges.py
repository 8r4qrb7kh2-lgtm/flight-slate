"""Badge proofs."""

from __future__ import annotations

from ui_lab.analysis import basic_analysis
from ui_lab.bitmap_font import FONT_5X7
from ui_lab.canvas import PixelCanvas, Rect
from ui_lab.pages.base import FeaturePage, PageFrame
from ui_lab.pages.common import draw_page_shell, three_column_rects
from ui_lab.palette import Palette
from ui_lab.widgets import draw_badge


class BadgesPage(FeaturePage):
    key = "badges"
    title = "Badges"
    animated = False

    def __init__(self) -> None:
        self.palette = Palette()

    def render(self, canvas: PixelCanvas, frame: PageFrame) -> None:
        palette = self.palette
        draw_page_shell(canvas, palette, "BADGES", f"{frame.index + 1:02d}/{frame.total:02d}")
        top_live, top_stale, top_error = three_column_rects(20, 12)
        bot_cruise, bot_alert, _spare = three_column_rects(38, 12)
        draw_badge(canvas, top_live, "LIVE", palette, palette.success)
        draw_badge(canvas, top_stale, "STALE", palette, palette.accent_alt)
        draw_badge(canvas, top_error, "ERROR", palette, palette.error)
        draw_badge(canvas, bot_cruise, "CRUISE", palette, palette.accent)
        draw_badge(canvas, bot_alert, "ALERT", palette, palette.accent_alt)

    def analyze(self, canvas: PixelCanvas) -> dict[str, object]:
        palette = self.palette
        allowed = {
            palette.background,
            palette.panel,
            palette.panel_edge,
            palette.text,
            palette.text_dim,
            palette.success,
            palette.accent,
            palette.accent_alt,
            palette.error,
        }
        return basic_analysis(canvas, allowed)
