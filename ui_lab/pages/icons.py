"""Icon system proofs."""

from __future__ import annotations

from ui_lab.analysis import basic_analysis
from ui_lab.assets import icon_registry
from ui_lab.bitmap_font import FONT_5X7
from ui_lab.canvas import PixelCanvas, Rect
from ui_lab.pages.base import FeaturePage, PageFrame
from ui_lab.pages.common import draw_bitmap_centered, draw_footer_note, draw_page_shell, draw_surface, three_column_rects
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
        keys = ["plane", "clock", "pin", "warning", "live", "list"]
        for index, key in enumerate(keys):
            column = index % 3
            row = index // 3
            tile = three_column_rects(20 + row * 18, 16)[column]
            draw_surface(canvas, tile, palette)
            icon_area = Rect(tile.x + 2, tile.y + 1, 10, 14)
            text_area = Rect(tile.x + 14, tile.y + 1, tile.width - 17, 14)
            draw_bitmap_centered(self.icons[key], canvas, icon_area)
            FONT_5X7.draw_boxed(
                canvas,
                text_area.x,
                text_area.y,
                text_area.width,
                key[:4],
                palette.text,
                align="left",
                height=text_area.height,
                valign="middle",
            )
        draw_footer_note(canvas, "CUSTOM ICON GRID", palette)

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
