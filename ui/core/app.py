"""Runtime app shell for rendering core widgets to the LED matrix mock."""

from __future__ import annotations

from collections import deque
from typing import Any

from mock_led_matrix import MockRGBMatrix
from standard_led_matrix_interface import InteractiveLEDMatrix, LEDMatrix, RGBMatrixOptions

from ui.core.canvas import PixelCanvas, Rect
from ui.core.colors import colors
from ui.core.widgets import Widget


class App:
    _REPEAT_INITIAL_DELAY_MS = 110
    _REPEAT_INTERVAL_MS = 65

    def __init__(
        self,
        matrix: InteractiveLEDMatrix | None = None,
        options: RGBMatrixOptions | None = None,
    ) -> None:
        self.options = options or RGBMatrixOptions(limit_refresh_rate_hz=20)
        self.matrix = matrix or MockRGBMatrix(self.options)
        self.canvas = PixelCanvas(self.options.width, self.options.height, colors.BLACK)
        self._event_queue: deque[str] = deque()
        self._held_nav_keys: set[str] = set()
        self._repeat_jobs: dict[str, str] = {}
        self._bind_inputs()

    def Render(self, root: Widget, auto_close_ms: int | None = None) -> None:
        del auto_close_ms
        self.canvas.clear(colors.BLACK)
        root.draw(self.canvas, Rect(0, 0, self.canvas.width, self.canvas.height))
        self._push_canvas_to_matrix(self.matrix)

    def render(self, root: Widget, auto_close_ms: int | None = None) -> None:
        self.Render(root, auto_close_ms=auto_close_ms)

    def poll_input(self) -> str | None:
        if self.matrix.closed:
            return "quit"
        if not self.matrix.process():
            return "quit"
        if self._event_queue:
            return self._event_queue.popleft()
        return None

    def _bind_inputs(self) -> None:
        root = getattr(self.matrix, "root", None)
        if root is None:
            return

        root.bind("<KeyPress-Left>", lambda event: self._on_nav_press(event, "left"))
        root.bind("<KeyRelease-Left>", lambda event: self._on_nav_release(event, "left"))
        root.bind("<KeyPress-Right>", lambda event: self._on_nav_press(event, "right"))
        root.bind("<KeyRelease-Right>", lambda event: self._on_nav_release(event, "right"))
        root.bind("<KeyPress-Escape>", lambda _event: self._event_queue.append("quit"))

    def _on_nav_press(self, event: Any, direction: str) -> None:
        del event
        if direction in self._held_nav_keys:
            return

        self._held_nav_keys.add(direction)
        self._event_queue.append(direction)
        self._schedule_repeat(direction, self._REPEAT_INITIAL_DELAY_MS)

    def _on_nav_release(self, event: Any, direction: str) -> None:
        del event
        self._held_nav_keys.discard(direction)

        job_id = self._repeat_jobs.pop(direction, None)
        if job_id is None:
            return

        root = getattr(self.matrix, "root", None)
        if root is None:
            return
        try:
            root.after_cancel(job_id)
        except Exception:
            # Ignore stale after ids if the root is closing.
            pass

    def _schedule_repeat(self, direction: str, delay_ms: int) -> None:
        root = getattr(self.matrix, "root", None)
        if root is None:
            return
        self._repeat_jobs[direction] = root.after(
            delay_ms,
            lambda: self._repeat_nav(direction),
        )

    def _repeat_nav(self, direction: str) -> None:
        if direction not in self._held_nav_keys:
            self._repeat_jobs.pop(direction, None)
            return

        self._event_queue.append(direction)
        self._schedule_repeat(direction, self._REPEAT_INTERVAL_MS)

    def _push_canvas_to_matrix(self, matrix: LEDMatrix) -> None:
        pixels = self.canvas.image.load()
        for y in range(self.canvas.height):
            for x in range(self.canvas.width):
                matrix.SetPixel(x, y, *pixels[x, y])
