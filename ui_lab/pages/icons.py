"""Icon system proofs."""

from __future__ import annotations

from ui_lab.analysis import basic_analysis
from ui_lab.assets import icon_registry
from ui_lab.bitmap_font import FONT_3X5
from ui_lab.canvas import PixelCanvas, Rect
from ui_lab.pages.base import FeaturePage, PageFrame
from ui_lab.pages.common import draw_bitmap_centered, draw_page_shell, draw_surface, three_column_rects
from ui_lab.palette import Palette


class IconsPage(FeaturePage):
    key = "icons"
    title = "Icons"
    animated = False

    def __init__(self) -> None:
        self.palette = Palette()
        self.icons = icon_registry()

    def render(self, canvas: PixelCanvas, frame: PageFrame) -> None:
        palette = self.palette
        draw_page_shell(canvas, palette, "ICONS", f"{frame.index + 1:02d}/{frame.total:02d}")
        labels = [("plane", "PLAN"), ("clock", "CLOCK"), ("pin", "PIN"), ("warning", "WARN"), ("live", "LIVE"), ("list", "LIST")]
        for index, (key, label) in enumerate(labels):
            column = index % 3
            row = index // 3
            label_y = 18 + row * 20
            tile = three_column_rects(24 + row * 20, 11)[column]
            FONT_3X5.draw_boxed(canvas, tile.x, label_y, tile.width, label, palette.text, align="center")
            draw_surface(canvas, tile, palette)
            icon_area = Rect(tile.x + 2, tile.y + 1, tile.width - 4, tile.height - 2)
            draw_bitmap_centered(self.icons[key], canvas, icon_area)

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
        return basic_analysis(canvas, allowed, icon_count=len(self.icons))
