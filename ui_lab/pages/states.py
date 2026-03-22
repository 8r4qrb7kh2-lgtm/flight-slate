"""State card proofs."""

from __future__ import annotations

from ui_lab.analysis import basic_analysis
from ui_lab.assets import icon_registry
from ui_lab.canvas import PixelCanvas, Rect
from ui_lab.pages.base import FeaturePage, PageFrame
from ui_lab.pages.common import draw_page_shell, full_width_rect
from ui_lab.palette import Palette
from ui_lab.widgets import draw_state_card


class StatesPage(FeaturePage):
    key = "states"
    title = "States"
    animated = False

    def __init__(self) -> None:
        self.palette = Palette()
        self.icons = icon_registry()

    def render(self, canvas: PixelCanvas, frame: PageFrame) -> None:
        palette = self.palette
        draw_page_shell(canvas, palette, "STATES", f"{frame.index + 1:02d}/{frame.total:02d}")
        draw_state_card(canvas, full_width_rect(19, 11), "LOADING", "", palette, palette.accent, self.icons["live"])
        draw_state_card(canvas, full_width_rect(34, 11), "EMPTY", "", palette, palette.accent_alt, self.icons["list"])
        draw_state_card(canvas, full_width_rect(49, 11), "ERROR", "", palette, palette.error, self.icons["warning"])

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
            palette.error,
        }
        return basic_analysis(canvas, allowed, state_count=2)
