"""Tkinter-based mock RGB LED matrix renderer."""

from __future__ import annotations

import sys
import tkinter as tk
from functools import lru_cache

from standard_led_matrix_interface import RGBMatrixOptions


class MockRGBMatrix:
    """A small subset of the rpi-rgb-led-matrix API for desktop development."""

    LED_DIAMETER = 6
    LED_GAP = 6
    LED_PITCH = LED_DIAMETER + LED_GAP
    GLOW_SPREAD = 2
    LED_RENDER_RADIUS = LED_DIAMETER / 2 + 0.5
    GLOW_RENDER_RADIUS = LED_RENDER_RADIUS + GLOW_SPREAD
    BORDER = 12
    BACKGROUND = "#000000"
    OFF_COLOR = "#080808"
    OUTLINE_COLOR = "#3a3a3a"
    GLOW_MIN_INTENSITY = 0

    def __init__(self, options: RGBMatrixOptions | None = None) -> None:
        self.options = options or RGBMatrixOptions()
        self.width = self.options.width
        self.height = self.options.height

        if sys.platform == "darwin" and tk.TkVersion < 8.6:
            raise RuntimeError(
                "Tkinter 8.6 or newer is required on macOS. "
                f"The current interpreter ({sys.executable}) is linked against Tk {tk.TkVersion}. "
                "Use a python.org or Homebrew Python build with a newer Tk."
            )

        if (self.width, self.height) != (128, 64):
            raise ValueError(
                "This emulator targets a single 128x64 panel; "
                f"got {self.width}x{self.height}."
            )

        self._frame_delay_ms = max(
            1, int(round(1000 / max(1, self.options.limit_refresh_rate_hz)))
        )
        self._brightness = max(0, min(100, int(self.options.brightness)))
        self._glow_ids: list[int] = []
        self._pixel_ids: list[int] = []
        self._framebuffer = bytearray(self.width * self.height * 3)
        self._dirty_pixels: set[int] = set()
        self._lit_pixels: set[int] = set()
        self._closed = False

        self.root = tk.Tk()
        self.root.title("Mock RGB Matrix 128x64")
        self.root.configure(bg=self.BACKGROUND)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Escape>", lambda _event: self.close())

        canvas_width = self.BORDER * 2 + (self.width - 1) * self.LED_PITCH + self.LED_DIAMETER
        canvas_height = self.BORDER * 2 + (self.height - 1) * self.LED_PITCH + self.LED_DIAMETER
        self.canvas = tk.Canvas(
            self.root,
            width=canvas_width,
            height=canvas_height,
            bg=self.BACKGROUND,
            highlightthickness=0,
        )
        self.canvas.pack()

        self._build_panel()
        self.root.after(0, self._render)

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:
        if self._closed or not (0 <= x < self.width and 0 <= y < self.height):
            return

        index = y * self.width + x
        base = index * 3
        r = self._clamp_channel(r)
        g = self._clamp_channel(g)
        b = self._clamp_channel(b)

        if (
            self._framebuffer[base] == r
            and self._framebuffer[base + 1] == g
            and self._framebuffer[base + 2] == b
        ):
            return

        self._framebuffer[base] = r
        self._framebuffer[base + 1] = g
        self._framebuffer[base + 2] = b
        self._dirty_pixels.add(index)

        if r or g or b:
            self._lit_pixels.add(index)
        else:
            self._lit_pixels.discard(index)

    def Clear(self) -> None:
        if self._closed or not self._lit_pixels:
            return

        cleared = tuple(self._lit_pixels)
        for index in cleared:
            base = index * 3
            self._framebuffer[base] = 0
            self._framebuffer[base + 1] = 0
            self._framebuffer[base + 2] = 0

        self._dirty_pixels.update(cleared)
        self._lit_pixels.clear()

    def CreateFrameCanvas(self) -> "MockRGBMatrix":
        return self

    def SwapOnVSync(self, canvas: "MockRGBMatrix") -> "MockRGBMatrix":
        return canvas

    def process(self) -> bool:
        if self._closed:
            return False

        self.root.update_idletasks()
        self.root.update()
        return not self._closed

    def mainloop(self) -> None:
        if not self._closed:
            self.root.mainloop()

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        if self._closed:
            return

        self._closed = True
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _build_panel(self) -> None:
        for y in range(self.height):
            center_y = self.BORDER + y * self.LED_PITCH + self.LED_DIAMETER / 2
            for x in range(self.width):
                center_x = self.BORDER + x * self.LED_PITCH + self.LED_DIAMETER / 2
                glow_id = self.canvas.create_oval(
                    center_x - self.GLOW_RENDER_RADIUS,
                    center_y - self.GLOW_RENDER_RADIUS,
                    center_x + self.GLOW_RENDER_RADIUS,
                    center_y + self.GLOW_RENDER_RADIUS,
                    fill=self.BACKGROUND,
                    outline="",
                )
                pixel_id = self.canvas.create_oval(
                    center_x - self.LED_RENDER_RADIUS,
                    center_y - self.LED_RENDER_RADIUS,
                    center_x + self.LED_RENDER_RADIUS,
                    center_y + self.LED_RENDER_RADIUS,
                    fill=self.OFF_COLOR,
                    outline=self.OUTLINE_COLOR,
                    width=1,
                )
                self._glow_ids.append(glow_id)
                self._pixel_ids.append(pixel_id)

    def _render(self) -> None:
        if self._closed:
            return

        if self._dirty_pixels:
            dirty = tuple(self._dirty_pixels)
            self._dirty_pixels.clear()
            for index in dirty:
                base = index * 3
                color = scale_rgb_to_hex(
                    self._framebuffer[base],
                    self._framebuffer[base + 1],
                    self._framebuffer[base + 2],
                    self._brightness,
                )
                led_is_lit = color != self.OFF_COLOR
                outline = "" if led_is_lit else self.OUTLINE_COLOR
                outline_width = 0 if led_is_lit else 1
                self.canvas.itemconfig(self._glow_ids[index], fill=self.BACKGROUND)
                self.canvas.itemconfig(
                    self._pixel_ids[index],
                    fill=color,
                    outline=outline,
                    width=outline_width,
                )

        self.root.after(self._frame_delay_ms, self._render)

    @staticmethod
    def _clamp_channel(value: int) -> int:
        return max(0, min(255, int(value)))


@lru_cache(maxsize=4096)
def scale_rgb_to_hex(r: int, g: int, b: int, brightness: int) -> str:
    if not (r or g or b):
        return MockRGBMatrix.OFF_COLOR

    factor = brightness / 100.0
    return "#{:02x}{:02x}{:02x}".format(
        int(r * factor),
        int(g * factor),
        int(b * factor),
    )


@lru_cache(maxsize=4096)
def glow_rgb_to_hex(r: int, g: int, b: int, brightness: int) -> str:
    if not (r or g or b):
        return MockRGBMatrix.BACKGROUND

    factor = brightness / 100.0
    return "#{:02x}{:02x}{:02x}".format(
        glow_channel(r, factor),
        glow_channel(g, factor),
        glow_channel(b, factor),
    )


def glow_channel(value: int, factor: float) -> int:
    led_scaled = int(value * factor)
    scaled = int(value * factor * 1.35)
    # Keep glow clearly secondary to the LED core while still using stronger scaling.
    capped = min(scaled, int(led_scaled * 0.55))
    return max(MockRGBMatrix.GLOW_MIN_INTENSITY, min(255, capped))


RGBMatrix = MockRGBMatrix
