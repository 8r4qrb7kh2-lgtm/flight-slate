"""Bitmap images and logos proofs."""

from __future__ import annotations

from ui_lab.analysis import basic_analysis
from ui_lab.assets import image_registry, logo_registry
from ui_lab.bitmap_font import FONT_5X7
from ui_lab.canvas import PixelCanvas, Rect
from ui_lab.pages.base import FeaturePage, PageFrame
from ui_lab.pages.common import draw_bitmap_centered, draw_page_shell, draw_surface, three_column_rects, two_column_rects
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
        top_boxes = three_column_rects(20, 14)
        for box in top_boxes:
            draw_surface(canvas, box, palette)
        for box, key in zip(top_boxes, ("slate", "meridian", "harbor")):
            draw_bitmap_centered(self.logos[key], canvas, Rect(box.x + 2, box.y + 2, box.width - 4, box.height - 4))

        image_box, fit_box = two_column_rects(40, 16)
        draw_surface(canvas, image_box, palette)
        draw_surface(canvas, fit_box, palette)
        draw_bitmap_centered(self.images["skyline"], canvas, Rect(image_box.x + 2, image_box.y + 2, image_box.width - 4, image_box.height - 4))
        draw_bitmap_centered(self.logos["meridian"], canvas, Rect(fit_box.x + 2, fit_box.y + 2, fit_box.width - 4, fit_box.height - 4))

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
