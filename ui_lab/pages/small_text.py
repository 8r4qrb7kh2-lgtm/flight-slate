"""Single-feature page for validating the small text system."""

from __future__ import annotations

from ui_lab.analysis import content_bounds, non_background_pixels, unexpected_colors
from ui_lab.bitmap_font import FONT_3X5, FONT_5X7
from ui_lab.canvas import PixelCanvas, Rect
from ui_lab.pages.base import FeaturePage, PageFrame
from ui_lab.pages.common import draw_page_shell, three_column_rects, two_column_rects
from ui_lab.palette import Palette


class TextPage(FeaturePage):
    key = "text"
    title = "Text"
    animated = False

    def __init__(self) -> None:
        self.palette = Palette()
        self.micro_width = 0
        self.regular_width = 0
        self.large_width = 0

    def render(self, canvas: PixelCanvas, frame: PageFrame) -> None:
        palette = self.palette
        draw_page_shell(canvas, palette, "TEXT", f"{frame.index + 1:02d}/{frame.total:02d}")
        self._draw_frame(canvas)
        self._draw_scale_proofs(canvas)
        self._draw_glyph_proofs(canvas)

    def analyze(self, canvas: PixelCanvas) -> dict[str, object]:
        palette = self.palette
        allowed_colors = {
            palette.background,
            palette.panel,
            palette.panel_edge,
            palette.text,
            palette.text_dim,
            palette.accent,
            palette.accent_alt,
            palette.success,
        }
        return {
            "used_colors": sorted(canvas.used_colors()),
            "unexpected_colors": unexpected_colors(canvas, allowed_colors),
            "non_background_pixels": non_background_pixels(canvas),
            "content_bounds": content_bounds(canvas),
            "micro_width": self.micro_width,
            "regular_width": self.regular_width,
            "large_width": self.large_width,
            "small_width": self.micro_width,
            "medium_width": self.regular_width,
        }

    def _draw_frame(self, canvas: PixelCanvas) -> None:
        palette = self.palette
        canvas.rect(Rect(8, 18, 112, 30), fill=palette.panel, outline=palette.panel_edge)
        canvas.rect(Rect(8, 50, 112, 8), fill=palette.panel, outline=palette.panel_edge)

    def _draw_scale_proofs(self, canvas: PixelCanvas) -> None:
        palette = self.palette
        micro_box, regular_box, large_box = three_column_rects(28, 16)
        FONT_3X5.draw_boxed(canvas, micro_box.x, 21, micro_box.width, "MICRO", palette.text_dim, align="center")
        FONT_3X5.draw_boxed(canvas, regular_box.x, 21, regular_box.width, "REG", palette.text_dim, align="center")
        FONT_3X5.draw_boxed(canvas, large_box.x, 21, large_box.width, "LARGE", palette.text_dim, align="center")
        for box in (micro_box, regular_box, large_box):
            canvas.rect(box, outline=palette.panel_edge)
        FONT_3X5.draw_boxed(
            canvas,
            micro_box.x + 1,
            micro_box.y + 1,
            micro_box.width - 2,
            "JFK",
            palette.text,
            align="center",
            height=micro_box.height - 2,
            valign="middle",
        )
        FONT_5X7.draw_boxed(
            canvas,
            regular_box.x + 1,
            regular_box.y + 1,
            regular_box.width - 2,
            "ALT",
            palette.accent,
            align="center",
            height=regular_box.height - 2,
            valign="middle",
        )
        FONT_5X7.draw_boxed(
            canvas,
            large_box.x + 1,
            large_box.y + 1,
            large_box.width - 2,
            "45",
            palette.success,
            scale=2,
            align="center",
            height=large_box.height - 2,
            valign="middle",
        )
        self.micro_width = FONT_3X5.measure("JFK")[0]
        self.regular_width = FONT_5X7.measure("ALT")[0]
        self.large_width = FONT_5X7.measure("45", scale=2)[0]

    def _draw_glyph_proofs(self, canvas: PixelCanvas) -> None:
        palette = self.palette
        alpha_box, numeric_box = two_column_rects(50, 8)
        FONT_3X5.draw_boxed(canvas, alpha_box.x, 52, alpha_box.width, "3X5  5X7  2X", palette.text, align="center")
        FONT_3X5.draw_boxed(canvas, numeric_box.x, 52, numeric_box.width, "ALIGN  FIT", palette.text_dim, align="center")


SmallTextPage = TextPage
