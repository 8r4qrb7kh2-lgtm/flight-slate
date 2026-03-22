"""Overflow system proofs: clip, ellipsis, and marquee."""

from __future__ import annotations

from ui_lab.analysis import basic_analysis
from ui_lab.bitmap_font import FONT_3X5, FONT_5X7
from ui_lab.canvas import PixelCanvas, Rect
from ui_lab.pages.base import FeaturePage, PageFrame
from ui_lab.pages.common import draw_page_shell, full_width_rect, draw_surface
from ui_lab.palette import Palette


class OverflowPage(FeaturePage):
    key = "overflow"
    title = "Overflow"
    animated = True

    def __init__(self) -> None:
        self.palette = Palette()
        self.clip_render = ""
        self.fit_render = ""
        self.scroll_offset = 0

    def render(self, canvas: PixelCanvas, frame: PageFrame) -> None:
        palette = self.palette
        draw_page_shell(canvas, palette, "OVERFLOW", f"{frame.index + 1:02d}/{frame.total:02d}")
        long_text = "MERIDIAN REGIONAL EXPRESS 452KT"
        clip_box = full_width_rect(20, 9)
        fit_box = full_width_rect(31, 9)
        scroll_box = full_width_rect(42, 9)
        label_width = 16
        for box in (clip_box, fit_box, scroll_box):
            draw_surface(canvas, box, palette)

        FONT_3X5.draw_boxed(canvas, clip_box.x + 3, clip_box.y, label_width, "CLIP", palette.accent, align="left", height=clip_box.height, valign="middle")
        FONT_3X5.draw_boxed(canvas, fit_box.x + 3, fit_box.y, label_width, "FIT", palette.accent_alt, align="left", height=fit_box.height, valign="middle")
        FONT_3X5.draw_boxed(canvas, scroll_box.x + 3, scroll_box.y, label_width, "MOVE", palette.success, align="left", height=scroll_box.height, valign="middle")

        text_x = clip_box.x + 21
        text_width = clip_box.right - text_x - 3
        self.clip_render = FONT_5X7.clip(long_text, text_width)
        self.fit_render = FONT_5X7.fit(long_text, text_width)
        FONT_5X7.draw_boxed(canvas, text_x, clip_box.y, text_width, self.clip_render, palette.text, clip=True, height=clip_box.height, valign="middle")
        FONT_5X7.draw_boxed(canvas, text_x, fit_box.y, text_width, self.fit_render, palette.text_dim, clip=True, height=fit_box.height, valign="middle")

        marquee_text = "LIVE  JFK ORD  ALT 321  SPD 452KT  "
        total_width = FONT_5X7.measure(marquee_text)[0]
        self.scroll_offset = int(frame.elapsed_s * 12) % max(1, total_width)
        cursor = text_x - self.scroll_offset
        while cursor < scroll_box.right:
            FONT_5X7.render_clipped(
                canvas,
                cursor,
                scroll_box.y + 1,
                marquee_text,
                palette.success,
                text_x,
                text_width,
            )
            cursor += total_width

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
        return basic_analysis(
            canvas,
            allowed,
            clip_width=FONT_5X7.measure(self.clip_render)[0],
            ellipsis_width=FONT_5X7.measure(self.fit_render)[0],
            scroll_offset=self.scroll_offset,
        )
