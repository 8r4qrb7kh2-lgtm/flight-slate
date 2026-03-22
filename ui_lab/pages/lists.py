"""List item proofs."""

from __future__ import annotations

from ui_lab.analysis import basic_analysis
from ui_lab.assets import logo_registry
from ui_lab.canvas import PixelCanvas, Rect
from ui_lab.pages.base import FeaturePage, PageFrame
from ui_lab.pages.common import draw_page_shell, full_width_rect
from ui_lab.palette import Palette
from ui_lab.widgets import draw_list_item


class ListsPage(FeaturePage):
    key = "lists"
    title = "Lists"
    animated = False

    def __init__(self) -> None:
        self.palette = Palette()
        self.logos = logo_registry()

    def render(self, canvas: PixelCanvas, frame: PageFrame) -> None:
        palette = self.palette
        draw_page_shell(canvas, palette, "LISTS", f"{frame.index + 1:02d}/{frame.total:02d}")
        draw_list_item(canvas, full_width_rect(18, 20), "JFK-ORD", "SL128", "452", palette, palette.accent, self.logos["slate"], selected=True)
        draw_list_item(canvas, full_width_rect(42, 20), "BOS-DCA", "MR205", "401", palette, palette.accent_alt, self.logos["meridian"])

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
            palette.success,
        }
        return basic_analysis(canvas, allowed, row_count=2)
