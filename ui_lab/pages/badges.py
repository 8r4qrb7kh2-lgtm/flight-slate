"""Badge proofs."""

from __future__ import annotations

from dataclasses import dataclass

from ui_lab.analysis import basic_analysis
from ui_lab.bitmap_font import FONT_5X7
from ui_lab.canvas import PixelCanvas, Rect
from ui_lab.layout_checks import center_offset_x, find_overlaps, rect_within_bounds
from ui_lab.pages.base import FeaturePage, PageFrame
from ui_lab.pages.common import draw_footer_note, draw_page_shell, three_column_rects, two_column_rects
from ui_lab.palette import Color
from ui_lab.palette import Palette
from ui_lab.widgets import draw_badge


@dataclass(frozen=True)
class BadgeSpec:
    key: str
    rect: Rect
    text: str
    accent: Color


class BadgesPage(FeaturePage):
    key = "badges"
    title = "Badges"
    animated = False

    STATUS_HEADER_Y = 14
    STATUS_ROW_Y = 24
    MODE_HEADER_Y = 37
    MODE_ROW_Y = 44
    BADGE_HEIGHT = 10

    def __init__(self) -> None:
        self.palette = Palette()
        self.center_offsets: list[float] = []
        self.overlap_pairs: list[tuple[str, str]] = []
        self.out_of_bounds_regions: list[str] = []

    def _record_centering(self, rect: Rect, rendered_text: str) -> None:
        text_width = FONT_5X7.measure(rendered_text)[0]
        inner_x = rect.x + 2
        inner_width = rect.width - 4
        draw_x = inner_x + max(0, (inner_width - text_width) // 2)
        self.center_offsets.append(center_offset_x(rect, draw_x, text_width))

    def render(self, canvas: PixelCanvas, frame: PageFrame) -> None:
        self._reset_frame_state()
        palette = self.palette
        draw_page_shell(canvas, palette, "BADGES", f"{frame.index + 1:02d}/{frame.total:02d}")
        FONT_5X7.draw_boxed(canvas, 8, self.STATUS_HEADER_Y, 112, "LIVE STATUS", palette.accent, align="center")
        FONT_5X7.draw_boxed(canvas, 8, self.MODE_HEADER_Y, 112, "OPERATING MODE", palette.accent_alt, align="center")

        specs = self._build_badge_specs()
        self._capture_layout_validation(specs, canvas)
        self._draw_badges(canvas, specs)
        draw_footer_note(canvas, "STATUS / PRIORITY / MODE", palette)

    def _reset_frame_state(self) -> None:
        self.center_offsets = []
        self.overlap_pairs = []
        self.out_of_bounds_regions = []

    def _build_badge_specs(self) -> list[BadgeSpec]:
        palette = self.palette
        live_box, stale_box, error_box = three_column_rects(self.STATUS_ROW_Y, self.BADGE_HEIGHT)
        cruise_box, alert_box = two_column_rects(self.MODE_ROW_Y, self.BADGE_HEIGHT)
        return [
            BadgeSpec(key="live", rect=live_box, text="LIVE", accent=palette.success),
            BadgeSpec(key="stale", rect=stale_box, text="STALE", accent=palette.accent_alt),
            BadgeSpec(key="error", rect=error_box, text="ERROR", accent=palette.error),
            BadgeSpec(key="cruise", rect=cruise_box, text="CRUISE", accent=palette.accent),
            BadgeSpec(key="alert", rect=alert_box, text="ALERT", accent=palette.accent_alt),
        ]

    def _capture_layout_validation(self, specs: list[BadgeSpec], canvas: PixelCanvas) -> None:
        regions = {spec.key: spec.rect for spec in specs}
        self.overlap_pairs = find_overlaps(regions)
        self.out_of_bounds_regions = [
            key
            for key, rect in regions.items()
            if not rect_within_bounds(rect, canvas.width, canvas.height)
        ]

    def _draw_badges(self, canvas: PixelCanvas, specs: list[BadgeSpec]) -> None:
        for spec in specs:
            rendered = draw_badge(canvas, spec.rect, spec.text, self.palette, spec.accent)
            self._record_centering(spec.rect, rendered)

    def analyze(self, canvas: PixelCanvas) -> dict[str, object]:
        palette = self.palette
        allowed = {
            palette.background,
            palette.panel,
            palette.panel_edge,
            palette.text,
            palette.text_dim,
            palette.success,
            palette.accent,
            palette.accent_alt,
            palette.error,
        }
        return basic_analysis(
            canvas,
            allowed,
            badge_center_offsets=self.center_offsets,
            overlap_pairs=self.overlap_pairs,
            out_of_bounds_regions=self.out_of_bounds_regions,
        )
