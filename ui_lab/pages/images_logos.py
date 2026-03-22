"""Bitmap images and logos proofs."""

from __future__ import annotations

from ui_lab.analysis import basic_analysis
from ui_lab.assets import image_registry, logo_registry
from ui_lab.bitmap_font import FONT_5X7
from ui_lab.canvas import PixelCanvas, Rect
from ui_lab.pages.base import FeaturePage, PageFrame
from ui_lab.pages.common import draw_bitmap_centered, draw_footer_note, draw_page_shell, draw_surface, three_column_rects, two_column_rects
from ui_lab.palette import Palette


class ImagesLogosPage(FeaturePage):
    key = "images_logos"
    title = "Images/Logos"
    animated = False

    def __init__(self) -> None:
        self.palette = Palette()
        self.logos = logo_registry()
        self.images = image_registry()

    def render(self, canvas: PixelCanvas, frame: PageFrame) -> None:
        palette = self.palette
        draw_page_shell(canvas, palette, "IMAGES/LOGOS", f"{frame.index + 1:02d}/{frame.total:02d}")
        top_boxes = three_column_rects(20, 16)
        for box in top_boxes:
            draw_surface(canvas, box, palette)
        for box, key in zip(top_boxes, ("slate", "meridian", "harbor")):
            draw_bitmap_centered(self.logos[key], canvas, box)

        image_box, label_box = two_column_rects(40, 16)
        draw_surface(canvas, image_box, palette)
        draw_surface(canvas, label_box, palette)
        draw_bitmap_centered(self.images["skyline"], canvas, image_box)
        FONT_5X7.draw_boxed(canvas, label_box.x, 42, label_box.width, "BITMAP", palette.accent, align="center")
        FONT_5X7.draw_boxed(canvas, label_box.x, 50, label_box.width, "LOGO FIT", palette.text_dim, align="center")
        draw_footer_note(canvas, "SCALED BITMAP + STORED LOGO", palette)

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
            palette.success,
        }
        return basic_analysis(canvas, allowed, logo_count=len(self.logos), image_count=len(self.images))
