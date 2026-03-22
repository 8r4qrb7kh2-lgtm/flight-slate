"""Overflow system proofs: clip, ellipsis, and marquee."""

from __future__ import annotations

from ui_lab.analysis import basic_analysis
from ui_lab.bitmap_font import FONT_5X7
from ui_lab.canvas import PixelCanvas, Rect
from ui_lab.pages.base import FeaturePage, PageFrame
from ui_lab.pages.common import draw_footer_note, draw_page_shell, full_width_rect, draw_surface
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
        clip_box = full_width_rect(20, 10)
        fit_box = full_width_rect(33, 10)
        scroll_box = full_width_rect(46, 10)
        label_width = 24
        for box in (clip_box, fit_box, scroll_box):
            draw_surface(canvas, box, palette)

        FONT_5X7.draw_boxed(canvas, clip_box.x + 2, clip_box.y + 1, label_width, "CLIP", palette.accent, align="left")
        FONT_5X7.draw_boxed(canvas, fit_box.x + 2, fit_box.y + 1, label_width, "CUT", palette.accent_alt, align="left")
        FONT_5X7.draw_boxed(canvas, scroll_box.x + 2, scroll_box.y + 1, label_width, "MOVE", palette.success, align="left")

        text_x = clip_box.x + label_width + 6
        text_width = clip_box.width - label_width - 8
        self.clip_render = FONT_5X7.clip(long_text, text_width)
        self.fit_render = FONT_5X7.fit(long_text, text_width)
        FONT_5X7.render(canvas, text_x, clip_box.y + 1, self.clip_render, palette.text)
        FONT_5X7.render(canvas, text_x, fit_box.y + 1, self.fit_render, palette.text_dim)

        marquee_text = "LIVE  JFK -> ORD  ALT 321  SPD 452KT  "
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
        draw_footer_note(canvas, "CLIP / ELLIPSIS / MARQUEE", palette)

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
