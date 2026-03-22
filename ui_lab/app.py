"""Single-page feature lab runner."""

from __future__ import annotations

import time
from pathlib import Path

from mock_led_matrix import MockRGBMatrix
from standard_led_matrix_interface import InteractiveLEDMatrix, LEDMatrix, RGBMatrixOptions
from ui_lab.canvas import PixelCanvas
from ui_lab.export import export_canvas
from ui_lab.pages.base import FeaturePage, PageFrame
from ui_lab.pages.animation import AnimationPage
from ui_lab.pages.badges import BadgesPage
from ui_lab.pages.container import ContainerPage
from ui_lab.pages.icons import IconsPage
from ui_lab.pages.images_logos import ImagesLogosPage
from ui_lab.pages.lists import ListsPage
from ui_lab.pages.map_page import MapPage
from ui_lab.pages.overflow import OverflowPage
from ui_lab.pages.progress import ProgressPage
from ui_lab.pages.shapes import ShapesPage
from ui_lab.pages.small_text import TextPage
from ui_lab.pages.states import StatesPage
from ui_lab.pages.stats import StatsPage
from ui_lab.palette import Palette


class FeatureLabApp:
    def __init__(self) -> None:
        self.palette = Palette()
        self.canvas = PixelCanvas(128, 64, self.palette.background)
        self.pages: list[FeaturePage] = [
            TextPage(),
            OverflowPage(),
            IconsPage(),
            ImagesLogosPage(),
            ContainerPage(),
            ShapesPage(),
            BadgesPage(),
            ProgressPage(),
            StatsPage(),
            ListsPage(),
            StatesPage(),
            MapPage(),
            AnimationPage(),
        ]
        self.page_index = 0
        self._inputs_bound = False

    @property
    def current_page(self) -> FeaturePage:
        return self.pages[self.page_index]

    def bind_inputs(self, matrix: InteractiveLEDMatrix) -> None:
        if self._inputs_bound:
            return
        root = getattr(matrix, "root", None)
        if root is None:
            return
        root.bind("<Right>", lambda _event: self.next_page())
        root.bind("<Left>", lambda _event: self.previous_page())
        for index in range(min(9, len(self.pages))):
            root.bind(str(index + 1), lambda _event, value=index: self.select_page(value))
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

    def export_current_page(self, output_root: Path, stem: str = "frame_000") -> tuple[dict[str, Path], dict[str, object]]:
        self.render(0.0)
        analysis = self.current_page.analyze(self.canvas)
        paths = export_canvas(self.canvas, output_root / self.current_page.key, stem, analysis)
        return paths, analysis

    def export_all_pages(self, output_root: Path) -> dict[str, list[dict[str, object]]]:
        report: dict[str, list[dict[str, object]]] = {}
        for index, page in enumerate(self.pages):
            self.page_index = index
            frame_times = [0.0]
            if page.animated:
                frame_times = [0.0, 0.25, 0.5, 0.75]
            page_entries: list[dict[str, object]] = []
            for frame_index, elapsed_s in enumerate(frame_times):
                self.render(elapsed_s)
                analysis = page.analyze(self.canvas)
                paths = export_canvas(self.canvas, output_root / page.key, f"frame_{frame_index:03d}", analysis)
                page_entries.append(
                    {
                        "elapsed_s": elapsed_s,
                        "analysis": analysis,
                        "paths": {key: str(value) for key, value in paths.items()},
                    }
                )
            report[page.key] = page_entries
        return report


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
