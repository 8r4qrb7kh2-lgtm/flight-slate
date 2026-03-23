"""Runtime app shell for rendering core widgets to the LED matrix mock."""

from __future__ import annotations

from collections import deque

from mock_led_matrix import MockRGBMatrix
from standard_led_matrix_interface import InteractiveLEDMatrix, LEDMatrix, RGBMatrixOptions

from ui.core.canvas import PixelCanvas, Rect
from ui.core.colors import colors
from ui.core.widgets import Widget


class App:
    def __init__(
        self,
        matrix: InteractiveLEDMatrix | None = None,
        options: RGBMatrixOptions | None = None,
    ) -> None:
        self.options = options or RGBMatrixOptions(limit_refresh_rate_hz=20)
        self.matrix = matrix or MockRGBMatrix(self.options)
        self.canvas = PixelCanvas(self.options.width, self.options.height, colors.BLACK)
        self._event_queue: deque[str] = deque()
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

        root.bind("<Left>", lambda _event: self._event_queue.append("left"))
        root.bind("<Right>", lambda _event: self._event_queue.append("right"))
        root.bind("<Escape>", lambda _event: self._event_queue.append("quit"))

    def _push_canvas_to_matrix(self, matrix: LEDMatrix) -> None:
        pixels = self.canvas.image.load()
        for y in range(self.canvas.height):
            for x in range(self.canvas.width):
                matrix.SetPixel(x, y, *pixels[x, y])
