#!/usr/bin/env python3
"""Bouncing-ball demo that uses the LED matrix interface."""

from __future__ import annotations

import colorsys
import os
import sys
import time
from dataclasses import dataclass, field

from mock_led_matrix import MockRGBMatrix
from standard_led_matrix_interface import InteractiveLEDMatrix, LEDMatrix, RGBMatrixOptions


@dataclass
class BouncingBallDemo:
    width: int
    height: int
    radius: int = 2
    position_x: int = field(init=False)
    position_y: int = field(init=False)
    velocity_x: int = 1
    velocity_y: int = 1
    hue: float = 0.0
    previous_pixels: set[tuple[int, int]] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.position_x = self.radius
        self.position_y = self.radius

    def draw_next_frame(self, matrix: LEDMatrix) -> None:
        for x, y in self.previous_pixels:
            matrix.SetPixel(x, y, 0, 0, 0)

        if self.position_x + self.velocity_x >= self.width - self.radius or self.position_x + self.velocity_x <= self.radius:
            self.velocity_x *= -1
        if self.position_y + self.velocity_y >= self.height - self.radius or self.position_y + self.velocity_y <= self.radius:
            self.velocity_y *= -1

        self.position_x += self.velocity_x
        self.position_y += self.velocity_y
        self.hue = (self.hue + 0.01) % 1.0
        red, green, blue = colorsys.hsv_to_rgb(self.hue, 1.0, 1.0)
        current_pixels = self._ball_pixels()
        for x, y in current_pixels:
            matrix.SetPixel(x, y, int(red * 255), int(green * 255), int(blue * 255))

        self.previous_pixels = current_pixels

    def _ball_pixels(self) -> set[tuple[int, int]]:
        pixels: set[tuple[int, int]] = set()
        for y in range(self.position_y - self.radius, self.position_y + self.radius + 1):
            for x in range(self.position_x - self.radius, self.position_x + self.radius + 1):
                if 0 <= x < self.width and 0 <= y < self.height:
                    if (x - self.position_x) ** 2 + (y - self.position_y) ** 2 <= self.radius ** 2:
                        pixels.add((x, y))
        return pixels


def run_bouncing_ball_demo(
    matrix: InteractiveLEDMatrix | None = None,
    options: RGBMatrixOptions | None = None,
    auto_close_ms: int | None = None,
) -> None:
    matrix = matrix or MockRGBMatrix(options or RGBMatrixOptions())
    if auto_close_ms is None:
        auto_close_value = os.environ.get("RGBMATRIX_AUTOCLOSE_MS")
        auto_close_ms = int(auto_close_value) if auto_close_value else None

    demo = BouncingBallDemo(matrix.width, matrix.height)
    frame_delay = 1.0 / max(1, (options or getattr(matrix, "options", RGBMatrixOptions())).limit_refresh_rate_hz)
    deadline = time.monotonic() + (auto_close_ms / 1000.0) if auto_close_ms and auto_close_ms > 0 else None

    matrix.Clear()
    while True:
        if matrix.closed:
            break
        if deadline is not None and time.monotonic() >= deadline:
            matrix.close()
            break

        frame_start = time.monotonic()
        demo.draw_next_frame(matrix)
        if not matrix.process():
            break

        sleep_time = frame_delay - (time.monotonic() - frame_start)
        if sleep_time > 0:
            time.sleep(sleep_time)


def main() -> int:
    try:
        run_bouncing_ball_demo()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
