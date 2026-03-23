"""Single-screen text demo runner."""

from __future__ import annotations

import time

from mock_led_matrix import MockRGBMatrix
from standard_led_matrix_interface import InteractiveLEDMatrix, LEDMatrix, RGBMatrixOptions
from ui_lab.canvas import PixelCanvas
from ui_lab.pages.base import FeaturePage, PageFrame
from ui_lab.pages.small_text import TextPage
from ui_lab.palette import Palette


class FeatureLabApp:
    def __init__(self) -> None:
        self.palette = Palette()
        self.canvas = PixelCanvas(128, 64, self.palette.background)
        self.pages: list[FeaturePage] = [TextPage()]
        self.page_index = 0
        self._inputs_bound = False

    @property
    def current_page(self) -> FeaturePage:
        return self.pages[self.page_index]

    def bind_inputs(self, matrix: InteractiveLEDMatrix) -> None:
        self._inputs_bound = True

    def next_page(self) -> None:
        self.page_index = (self.page_index + 1) % len(self.pages)

    def previous_page(self) -> None:
        self.page_index = (self.page_index - 1) % len(self.pages)

    def select_page(self, index: int) -> None:
        self.page_index = index % len(self.pages)

    def render(self, elapsed_s: float = 0.0) -> PixelCanvas:
        frame = PageFrame(index=self.page_index, total=len(self.pages), elapsed_s=elapsed_s)
        self.current_page.render(self.canvas, frame)
        return self.canvas

    def render_to_matrix(self, matrix: LEDMatrix, elapsed_s: float = 0.0) -> None:
        self.render(elapsed_s)
        pixels = self.canvas.image.load()
        for y in range(self.canvas.height):
            for x in range(self.canvas.width):
                matrix.SetPixel(x, y, *pixels[x, y])


def run_feature_lab(
    matrix: InteractiveLEDMatrix | None = None,
    options: RGBMatrixOptions | None = None,
    auto_close_ms: int | None = None,
) -> None:
    options = options or RGBMatrixOptions(limit_refresh_rate_hz=20)
    matrix = matrix or MockRGBMatrix(options)
    app = FeatureLabApp()
    app.bind_inputs(matrix)
    start = time.monotonic()
    deadline = start + (auto_close_ms / 1000.0) if auto_close_ms and auto_close_ms > 0 else None
    frame_delay = 1.0 / max(1, options.limit_refresh_rate_hz)

    while True:
        if matrix.closed:
            break
        if deadline is not None and time.monotonic() >= deadline:
            matrix.close()
            break

        frame_start = time.monotonic()
        app.render_to_matrix(matrix, frame_start - start)
        if not matrix.process():
            break

        sleep_time = frame_delay - (time.monotonic() - frame_start)
        if sleep_time > 0:
            time.sleep(sleep_time)
