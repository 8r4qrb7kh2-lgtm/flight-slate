"""Single-screen text demo built from simple retained layout primitives."""

from __future__ import annotations

from ui_lab.analysis import content_bounds, non_background_pixels, unexpected_colors
from ui_lab.canvas import PixelCanvas, Rect
from ui_lab.layout import BODY, MUTED, TITLE, Column, Label, Row
from ui_lab.layout_checks import find_overlaps, rect_within_bounds
from ui_lab.pages.base import FeaturePage, PageFrame
from ui_lab.palette import Palette


class TextPage(FeaturePage):
    key = "text"
    title = "Text"
    animated = False

    def __init__(self) -> None:
        self.palette = Palette()
        self.glyph_lines: list[str] = []
        self.overlap_pairs: list[tuple[str, str]] = []
        self.out_of_bounds_regions: list[str] = []

    def render(self, canvas: PixelCanvas, frame: PageFrame) -> None:
        del frame
        canvas.clear(self.palette.background)
        self._draw_frame(canvas)
        self._draw_demo(canvas)

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
            "glyph_lines": self.glyph_lines,
            "overlap_pairs": self.overlap_pairs,
            "out_of_bounds_regions": self.out_of_bounds_regions,
        }

    def _draw_frame(self, canvas: PixelCanvas) -> None:
        palette = self.palette
        regions = {
            "demo_panel": Rect(0, 0, 128, 64),
        }
        self.overlap_pairs = find_overlaps(regions)
        self.out_of_bounds_regions = [
            key
            for key, rect in regions.items()
            if not rect_within_bounds(rect, canvas.width, canvas.height)
        ]
        canvas.rect(regions["demo_panel"], fill=palette.panel)

    def _draw_demo(self, canvas: PixelCanvas) -> None:
        self.glyph_lines = [
            "A B C D E F G H",
            "I J K L M N O P",
            "Q R S T U V W X",
            "Y Z",
            "0 1 2 3 4 5 6 7",
            "8 9",
            ". , : ; ! ? - /",
        ]
        screen = Column(
            children=[
                Row(children=[Label("TEXT", style=TITLE), Label("5X7", style=MUTED)], gap=4),
                *[Label(line, style=BODY) for line in self.glyph_lines[:4]],
                *[Label(line, style=BODY) for line in self.glyph_lines[4:]],
            ],
            padding=2,
            gap=0,
        )
        screen.render(canvas, Rect(0, 0, 128, 64), self.palette)


SmallTextPage = TextPage
