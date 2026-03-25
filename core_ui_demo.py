#!/usr/bin/env python3
"""Core UI demo launcher with Font, Layout, and Marquee pages."""

from __future__ import annotations

import ctypes
import sys
import time
from dataclasses import dataclass

from standard_led_matrix_interface import RGBMatrixOptions
from ui import App, Column, FONT_5X7, FONT_3X5, FONT_4X6, Marquee, Panel, Row, Text, colors
from ui.fonts.import_util import ALNUM_PUNCT_94


@dataclass
class AppState:
    page_index: int = 0
    marquee_x: float = 0.0
    marquee_y: float = 0.0


DEMO_PAGES = ["font-demo", "layout-demo", "marquee-demo"]
MARQUEE_X_PIXELS_PER_SECOND = 12
MARQUEE_Y_PIXELS_PER_SECOND = 10
TARGET_REFRESH_HZ = 120
MISS_LOG_INTERVAL_S = 1.0


class _HighResWindowsTimer:
    def __init__(self) -> None:
        self._enabled = False

    def __enter__(self) -> "_HighResWindowsTimer":
        if sys.platform == "win32":
            try:
                winmm = ctypes.WinDLL("winmm")
                if winmm.timeBeginPeriod(1) == 0:
                    self._enabled = True
            except Exception:
                self._enabled = False
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._enabled and sys.platform == "win32":
            try:
                ctypes.WinDLL("winmm").timeEndPeriod(1)
            except Exception:
                pass


def _sleep_until(deadline: float) -> None:
    while True:
        now = time.perf_counter()
        remaining = deadline - now
        if remaining <= 0:
            return
        if remaining > 0.002:
            time.sleep(remaining - 0.001)
        else:
            # Finish with a short spin to avoid timer quantization misses.
            while time.perf_counter() < deadline:
                pass
            return


def clamp_page(index: int) -> int:
    return max(0, min(index, len(DEMO_PAGES) - 1))


def _build_font_demo_page() -> Panel:
    return Panel(
        padding=2,
        bg=colors.BLACK,
        border=colors.BLUE,
        child=Column(
            gap=1,
            sizes=[8, 10, 10, 34],
            children=[
                Text(
                    align="center",
                    font=FONT_5X7,
                    overflow="clip",
                    text="FONT DEMO",
                ),
                Text(
                    align="left",
                    font=FONT_3X5,
                    overflow="wrap",
                    text="3x5: ABC123!?",
                ),
                Text(
                    align="left",
                    font=FONT_4X6,
                    overflow="wrap",
                    text="4x6: MERIDIAN",
                ),
                Text(
                    align="left",
                    font=FONT_5X7,
                    overflow="wrap",
                    text=f"{ALNUM_PUNCT_94}",
                ),
            ],
        ),
    )


def _build_layout_demo_page() -> Panel:
    return Panel(
        padding=1,
        bg=colors.BLACK,
        border=colors.CYAN,
        child=Column(
            gap=1,
            sizes=[8, 54],
            children=[
                Text(
                    align="center",
                    font=FONT_5X7,
                    overflow="clip",
                    text="ROW/COLUMN",
                ),
                Row(
                    gap=1,
                    sizes=[10, 90],
                    children=[
                        Panel(bg=colors.BLUE, border=colors.WHITE, child=None),
                        Column(
                            gap=1,
                            sizes=[1, 1, 1],
                            children=[
                                Row(
                                    gap=1,
                                    sizes=[1, 1],
                                    children=[
                                        Panel(bg=colors.CYAN, border=colors.WHITE, child=None),
                                        Panel(bg=colors.DIM_WHITE, border=colors.WHITE, child=None),
                                    ],
                                ),
                                Row(
                                    gap=1,
                                    sizes=[10, 90],
                                    children=[
                                        Panel(bg=colors.BLUE, border=colors.WHITE, child=None),
                                        Panel(bg=colors.DIM_WHITE, border=colors.WHITE, child=None),
                                    ],
                                ),
                                Row(
                                    gap=1,
                                    sizes=[1, 1, 1],
                                    children=[
                                        Panel(bg=colors.CYAN, border=colors.WHITE, child=None),
                                        Panel(bg=colors.BLUE, border=colors.WHITE, child=None),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        ),
    )


def _build_marquee_demo_page(state: AppState) -> Panel:
    horizontal_banner = Text(
        align="left",
        font=FONT_4X6,
        overflow="overflow",
        overflow_axis="x",
        overflow_offset=state.marquee_x,
        overflow_gap=4,
        text="  ARRIVALS: SEA 08:40  LAX 09:05  SFO 09:20  JFK 10:10  ",
    )
    vertical_feed = Text(
        align="left",
        font=FONT_3X5,
        overflow="overflow",
        overflow_axis="y",
        overflow_offset=state.marquee_y,
        overflow_gap=2,
        text="GATE A1 OPEN  GATE A3 BOARDING  GATE B4 DELAYED  GATE C2 NOW BOARDING  ",
    )
    generic_content = Marquee(
        axis="x",
        offset=state.marquee_x,
        content_extent=34,
        gap=2,
        child=Panel(
            padding=1,
            border=colors.WHITE,
            bg=colors.BLUE,
            child=Text(
                align="center",
                font=FONT_3X5,
                overflow="clip",
                text="GENERIC TILE",
                color=colors.WHITE,
            ),
        ),
    )
    return Panel(
        padding=1,
        bg=colors.BLACK,
        border=colors.WHITE,
        child=Column(
            gap=1,
            sizes=[8, 10, 20, 22],
            children=[
                Text(
                    align="center",
                    font=FONT_5X7,
                    overflow="clip",
                    text="MARQUEE",
                ),
                horizontal_banner,
                Panel(
                    padding=1,
                    bg=colors.BLACK,
                    border=colors.CYAN,
                    child=vertical_feed,
                ),
                generic_content,
            ],
        ),
    )


def build_pages(state: AppState) -> list[Panel]:
    return [_build_font_demo_page(), _build_layout_demo_page(), _build_marquee_demo_page(state)]


def _publish_perf_stats(
    app: App,
    *,
    target_hz: float,
    actual_hz: float,
    misses: int,
    frames: int,
    avg_overrun_ms: float,
    max_overrun_ms: float,
    minor_late: int,
    major_late: int,
) -> None:
    setter = getattr(app.matrix, "SetPerformanceStats", None)
    if callable(setter):
        setter(
            target_hz=target_hz,
            actual_hz=actual_hz,
            misses=misses,
            frames=frames,
            avg_overrun_ms=avg_overrun_ms,
            max_overrun_ms=max_overrun_ms,
            minor_late=minor_late,
            major_late=major_late,
        )
        return

    root = getattr(app.matrix, "root", None)
    if root is not None:
        root.title(
            "Mock RGB Matrix "
            f"{actual_hz:.1f}/{target_hz:.1f}Hz "
            f"miss {misses}/{frames} "
            f"avg {avg_overrun_ms:.2f}ms max {max_overrun_ms:.2f}ms"
        )


def main() -> int:
    try:
        with _HighResWindowsTimer():
            app = App(options=RGBMatrixOptions(limit_refresh_rate_hz=TARGET_REFRESH_HZ))
            state = AppState()
            start = time.perf_counter()
            frame_delay = 1.0 / max(1, app.options.limit_refresh_rate_hz)
            next_deadline = start + frame_delay
            stats_window_start = start
            frames_in_window = 0
            misses_in_window = 0
            max_overrun_ms = 0.0
            overrun_sum_ms = 0.0
            minor_late_in_window = 0
            major_late_in_window = 0
            needs_render = True

            while True:
                frame_start = time.perf_counter()
                event = app.poll_input()
                if event == "left":
                    state.page_index = clamp_page(state.page_index - 1)
                    needs_render = True
                elif event == "right":
                    state.page_index = clamp_page(state.page_index + 1)
                    needs_render = True
                elif event == "quit":
                    break

                elapsed_s = frame_start - start
                state.marquee_x = elapsed_s * MARQUEE_X_PIXELS_PER_SECOND
                state.marquee_y = elapsed_s * MARQUEE_Y_PIXELS_PER_SECOND

                if state.page_index == 2:
                    needs_render = True

                if needs_render:
                    pages = build_pages(state)
                    app.Render(pages[state.page_index])
                    needs_render = False

                now = time.perf_counter()
                frames_in_window += 1
                overrun = now - next_deadline
                if overrun > 0:
                    overrun_ms = overrun * 1000.0
                    misses_in_window += 1
                    max_overrun_ms = max(max_overrun_ms, overrun_ms)
                    overrun_sum_ms += overrun_ms
                    if overrun_ms <= 0.5:
                        minor_late_in_window += 1
                    elif overrun_ms >= 2.0:
                        major_late_in_window += 1
                    # Reset phase if we missed by more than one frame period.
                    if overrun > frame_delay:
                        next_deadline = now + frame_delay
                    else:
                        next_deadline += frame_delay
                else:
                    _sleep_until(next_deadline)
                    next_deadline += frame_delay

                now = time.perf_counter()
                window_elapsed = now - stats_window_start
                if window_elapsed >= MISS_LOG_INTERVAL_S:
                    actual_hz = frames_in_window / max(1e-9, window_elapsed)
                    avg_overrun_ms = (
                        overrun_sum_ms / misses_in_window if misses_in_window > 0 else 0.0
                    )
                    _publish_perf_stats(
                        app,
                        target_hz=float(app.options.limit_refresh_rate_hz),
                        actual_hz=actual_hz,
                        misses=misses_in_window,
                        frames=frames_in_window,
                        avg_overrun_ms=avg_overrun_ms,
                        max_overrun_ms=max_overrun_ms,
                        minor_late=minor_late_in_window,
                        major_late=major_late_in_window,
                    )
                    if misses_in_window > 0:
                        print(
                            "[timing] "
                            f"target={app.options.limit_refresh_rate_hz}Hz "
                            f"actual={actual_hz:.1f}Hz "
                            f"misses={misses_in_window}/{frames_in_window} "
                            f"avg_overrun={avg_overrun_ms:.2f}ms "
                            f"max_overrun={max_overrun_ms:.2f}ms "
                            f"minor={minor_late_in_window} "
                            f"major={major_late_in_window}"
                        )
                    stats_window_start = now
                    frames_in_window = 0
                    misses_in_window = 0
                    max_overrun_ms = 0.0
                    overrun_sum_ms = 0.0
                    minor_late_in_window = 0
                    major_late_in_window = 0

            if not app.matrix.closed:
                app.matrix.close()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
