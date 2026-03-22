"""Single-feature page for validating the small text system."""

from __future__ import annotations

from ui_lab.analysis import content_bounds, non_background_pixels, unexpected_colors
from ui_lab.bitmap_font import FONT_5X7
from ui_lab.canvas import PixelCanvas, Rect
from ui_lab.pages.base import FeaturePage, PageFrame
from ui_lab.pages.common import draw_page_shell, draw_footer_note, three_column_rects, two_column_rects
from ui_lab.palette import Palette


class TextPage(FeaturePage):
    key = "text"
    title = "Text"
    animated = False

    def __init__(self) -> None:
        self.palette = Palette()
        self.small_width = 0
        self.medium_width = 0
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
            "small_width": self.small_width,
            "medium_width": self.medium_width,
            "large_width": self.large_width,
        }

    def _draw_frame(self, canvas: PixelCanvas) -> None:
        palette = self.palette
        canvas.rect(Rect(8, 18, 112, 24), fill=palette.panel, outline=palette.panel_edge)
        canvas.rect(Rect(8, 46, 112, 10), fill=palette.panel, outline=palette.panel_edge)

    def _draw_scale_proofs(self, canvas: PixelCanvas) -> None:
        palette = self.palette
        small_box, medium_box, large_box = three_column_rects(24, 14)
        FONT_5X7.draw_boxed(canvas, small_box.x, 17, small_box.width, "SM", palette.text_dim, align="center")
        FONT_5X7.draw_boxed(canvas, medium_box.x, 17, medium_box.width, "MD", palette.text_dim, align="center")
        FONT_5X7.draw_boxed(canvas, large_box.x, 17, large_box.width, "LG", palette.text_dim, align="center")
        for box in (small_box, medium_box, large_box):
            canvas.rect(box, outline=palette.panel_edge)
        FONT_5X7.draw_boxed(
            canvas,
            small_box.x + 1,
            small_box.y + 1,
            small_box.width - 2,
            "JFK",
            palette.text,
            align="center",
            height=small_box.height - 2,
            valign="middle",
        )
        FONT_5X7.draw_boxed(
            canvas,
            medium_box.x + 1,
            medium_box.y + 1,
            medium_box.width - 2,
            "45",
            palette.accent,
            scale=2,
            align="center",
            height=medium_box.height - 2,
            valign="middle",
        )
        FONT_5X7.draw_boxed(
            canvas,
            large_box.x + 1,
            large_box.y + 1,
            large_box.width - 2,
            "GO",
            palette.success,
            scale=2,
            align="center",
            height=large_box.height - 2,
            valign="middle",
        )
        self.small_width = FONT_5X7.measure("JFK")[0]
        self.medium_width = FONT_5X7.measure("45", scale=2)[0]
        self.large_width = FONT_5X7.measure("GO", scale=2)[0]

    def _draw_glyph_proofs(self, canvas: PixelCanvas) -> None:
        palette = self.palette
        alpha_box, numeric_box = two_column_rects(46, 10)
        FONT_5X7.draw_boxed(canvas, alpha_box.x, 47, alpha_box.width, "ABCDE", palette.text, align="center")
        FONT_5X7.draw_boxed(canvas, numeric_box.x, 47, numeric_box.width, "01234", palette.text_dim, align="center")
        draw_footer_note(canvas, "ALPHA / NUMERIC PROOF", palette)


SmallTextPage = TextPage
