"""Runtime app shell for rendering core widgets to the LED matrix mock."""

from __future__ import annotations

from collections import deque
import importlib
import os
import time
from typing import Any

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
        self.matrix = matrix or _build_default_matrix(self.options)
        self.canvas = PixelCanvas(self.options.width, self.options.height, colors.BLACK)
        self._last_frame_bytes = bytearray(self.options.width * self.options.height * 3)
        self._frame_initialized = False
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
        frame_bytes = self.canvas.to_bytes()
        bulk_uploader = getattr(matrix, "SetPixelsFromBytes", None)
        if callable(bulk_uploader):
            bulk_uploader(frame_bytes)
            self._last_frame_bytes[:] = frame_bytes
            self._frame_initialized = True
            return

        width = self.canvas.width

        for index in range(width * self.canvas.height):
            base = index * 3
            r = frame_bytes[base]
            g = frame_bytes[base + 1]
            b = frame_bytes[base + 2]
            if self._frame_initialized:
                if (
                    self._last_frame_bytes[base] == r
                    and self._last_frame_bytes[base + 1] == g
                    and self._last_frame_bytes[base + 2] == b
                ):
                    continue
            x = index % width
            y = index // width
            matrix.SetPixel(x, y, r, g, b)

        self._last_frame_bytes[:] = frame_bytes
        self._frame_initialized = True


def _build_default_matrix(options: RGBMatrixOptions) -> InteractiveLEDMatrix:
    hardware_mapping = (options.hardware_mapping or "mock").strip().lower()
    if hardware_mapping == "mock":
        from mock_led_matrix import MockRGBMatrix

        return MockRGBMatrix(options)

    return _RPiRGBMatrix(options)


class _RPiRGBMatrix:
    """Thin adapter around rpi-rgb-led-matrix for headless board rendering."""

    def __init__(self, options: RGBMatrixOptions) -> None:
        try:
            rgbmatrix = importlib.import_module("rgbmatrix")
        except Exception as exc:
            raise RuntimeError(
                "rpi-rgb-led-matrix is required for non-mock hardware mapping. "
                "Install it on the Pi or set FLIGHT_SLATE_HARDWARE_MAPPING=mock."
            ) from exc

        native_options = rgbmatrix.RGBMatrixOptions()
        native_options.rows = int(options.rows)
        native_options.cols = int(options.cols)
        native_options.chain_length = int(options.chain_length)
        native_options.parallel = int(options.parallel)
        native_options.brightness = int(options.brightness)
        native_options.hardware_mapping = options.hardware_mapping
        native_options.pwm_bits = int(options.pwm_bits)

        # Allow board-specific tuning without changing code.
        gpio_slowdown = os.environ.get("FLIGHT_SLATE_LED_GPIO_SLOWDOWN")
        if gpio_slowdown:
            native_options.gpio_slowdown = int(gpio_slowdown)
        pwm_lsb_ns = os.environ.get("FLIGHT_SLATE_LED_PWM_LSB_NANOSECONDS")
        if pwm_lsb_ns:
            native_options.pwm_lsb_nanoseconds = int(pwm_lsb_ns)

        self._matrix = rgbmatrix.RGBMatrix(options=native_options)
        self.width = int(getattr(self._matrix, "width", options.width))
        self.height = int(getattr(self._matrix, "height", options.height))
        self._closed = False

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:
        if self._closed:
            return
        self._matrix.SetPixel(x, y, int(r), int(g), int(b))

    def Clear(self) -> None:
        if self._closed:
            return
        self._matrix.Clear()

    def process(self) -> bool:
        if self._closed:
            return False
        # Keep interactive API compatible with the desktop mock loop.
        time.sleep(0)
        return True

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._matrix.Clear()
        except Exception:
            pass
