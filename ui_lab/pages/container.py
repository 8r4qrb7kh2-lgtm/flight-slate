"""Surface/container primitive proofs."""

from __future__ import annotations

from ui_lab.analysis import basic_analysis, row_color_count
from ui_lab.bitmap_font import FONT_5X7
from ui_lab.canvas import PixelCanvas, Rect
from ui_lab.pages.base import FeaturePage, PageFrame
from ui_lab.pages.common import draw_page_shell, draw_surface, two_column_rects
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
        left_box, right_box = two_column_rects(22, 28)
        left_inner = Rect(left_box.x + 6, left_box.y + 12, left_box.width - 12, 12)
        right_inner = Rect(right_box.x + 6, right_box.y + 12, right_box.width - 12, 12)
        for box in (left_box, right_box, left_inner, right_inner):
            draw_surface(canvas, box, palette)
        FONT_5X7.draw_boxed(
            canvas,
            left_box.x,
            left_box.y + 2,
            left_box.width,
            "BASE",
            palette.accent,
            align="center",
            height=8,
            valign="middle",
        )
        FONT_5X7.draw_boxed(
            canvas,
            right_box.x,
            right_box.y + 2,
            right_box.width,
            "PAD",
            palette.accent_alt,
            align="center",
            height=8,
            valign="middle",
        )
        FONT_5X7.draw_boxed(
            canvas,
            left_inner.x,
            left_inner.y,
            left_inner.width,
            "EDGE",
            palette.text,
            align="center",
            height=left_inner.height,
            valign="middle",
        )
        FONT_5X7.draw_boxed(
            canvas,
            right_inner.x,
            right_inner.y,
            right_inner.width,
            "INSET",
            palette.text_dim,
            align="center",
            height=right_inner.height,
            valign="middle",
        )

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
