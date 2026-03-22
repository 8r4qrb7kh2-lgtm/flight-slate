"""Animation proofs with multi-frame export support."""

from __future__ import annotations

import math

from ui_lab.analysis import basic_analysis
from ui_lab.assets import icon_registry
from ui_lab.bitmap_font import FONT_5X7
from ui_lab.canvas import PixelCanvas, Rect
from ui_lab.pages.base import FeaturePage, PageFrame
from ui_lab.pages.common import draw_footer_note, draw_page_shell, draw_surface, full_width_rect, three_column_rects
from ui_lab.palette import Palette
from ui_lab.widgets import draw_badge, draw_progress_bar


class AnimationPage(FeaturePage):
    key = "animation"
    title = "Animation"
    animated = True

    def __init__(self) -> None:
        self.palette = Palette()
        self.icons = icon_registry()
        self.blink_on = False
        self.progress_width = 0
        self.marquee_offset = 0

    def render(self, canvas: PixelCanvas, frame: PageFrame) -> None:
        palette = self.palette
        draw_page_shell(canvas, palette, "ANIMATION", f"{frame.index + 1:02d}/{frame.total:02d}")
        pulse_box, blink_box, scroll_box = three_column_rects(22, 10)
        FONT_5X7.draw_boxed(canvas, pulse_box.x, 15, pulse_box.width, "PULSE", palette.accent, align="center")
        FONT_5X7.draw_boxed(canvas, blink_box.x, 15, blink_box.width, "BLINK", palette.error, align="center")
        FONT_5X7.draw_boxed(canvas, scroll_box.x, 15, scroll_box.width, "SCROLL", palette.success, align="center")
        draw_surface(canvas, pulse_box, palette)
        draw_surface(canvas, blink_box, palette)
        draw_surface(canvas, scroll_box, palette)

        pulse_phase = math.sin(frame.elapsed_s * 2.4) * 0.5 + 0.5
        pulse_color = palette.accent if pulse_phase > 0.5 else palette.text_dim
        draw_badge(canvas, pulse_box, "ON", palette, pulse_color)
        self.blink_on = int(frame.elapsed_s * 2) % 2 == 0
        if self.blink_on:
            draw_badge(canvas, blink_box, "ON", palette, palette.error)
        else:
            draw_badge(canvas, blink_box, "OFF", palette, palette.panel_edge)

        scroll_text = "MOVE "
        self.marquee_offset = int(frame.elapsed_s * 10) % FONT_5X7.measure(scroll_text)[0]
        cursor = scroll_box.x + 2 - self.marquee_offset
        while cursor < scroll_box.right:
            FONT_5X7.render_clipped(
                canvas,
                cursor,
                scroll_box.y + 2,
                scroll_text,
                palette.success,
                scroll_box.x + 2,
                scroll_box.width - 4,
            )
            cursor += FONT_5X7.measure(scroll_text)[0]

        FONT_5X7.render(canvas, 8, 40, "MOTION", palette.accent_alt)
        self.progress_width = draw_progress_bar(
            canvas,
            full_width_rect(48, 8),
            (math.sin(frame.elapsed_s) * 0.5 + 0.5),
            palette,
            palette.accent_alt,
        )
        marker_x = 10 + min(108, self.progress_width)
        canvas.circle(marker_x, 45, 2, palette.text, fill=True)
        draw_footer_note(canvas, "PULSE / BLINK / MARQUEE", palette)

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
            palette.error,
        }
        return basic_analysis(
            canvas,
            allowed,
            blink_on=self.blink_on,
            progress_width=self.progress_width,
            marquee_offset=self.marquee_offset,
        )
