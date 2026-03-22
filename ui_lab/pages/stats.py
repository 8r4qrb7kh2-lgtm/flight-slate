"""Metric/stat block proofs."""

from __future__ import annotations

from ui_lab.analysis import basic_analysis
from ui_lab.assets import icon_registry
from ui_lab.canvas import PixelCanvas, Rect
from ui_lab.pages.base import FeaturePage, PageFrame
from ui_lab.pages.common import draw_footer_note, draw_page_shell, three_column_rects
from ui_lab.palette import Palette
from ui_lab.widgets import draw_stat_block


class StatsPage(FeaturePage):
    key = "stats"
    title = "Stats"
    animated = False

    def __init__(self) -> None:
        self.palette = Palette()
        self.icons = icon_registry()
        self.value_widths: list[int] = []

    def render(self, canvas: PixelCanvas, frame: PageFrame) -> None:
        palette = self.palette
        self.value_widths = []
        draw_page_shell(canvas, palette, "STATS", f"{frame.index + 1:02d}/{frame.total:02d}")
        for rect, label, value, accent, icon in zip(
            three_column_rects(20, 36),
            ("SPD", "ALT", "HDG"),
            ("452", "321", "281"),
            (palette.accent, palette.success, palette.accent_alt),
            (self.icons["plane"], self.icons["clock"], self.icons["pin"]),
        ):
            self.value_widths.append(draw_stat_block(canvas, rect, label, value, palette, accent, icon)["value_width"])
        draw_footer_note(canvas, "ICON + LABEL + VALUE", palette)

    def analyze(self, canvas: PixelCanvas) -> dict[str, object]:
        palette = self.palette
        allowed = {
            palette.background,
            palette.panel,
            palette.panel_edge,
            palette.text_dim,
            palette.accent,
            palette.accent_alt,
            palette.success,
            palette.text,
            palette.error,
        }
        return basic_analysis(canvas, allowed, value_widths=self.value_widths)
