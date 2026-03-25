"""Tkinter-based mock RGB LED matrix renderer."""

from __future__ import annotations

import sys
import tkinter as tk

from PIL import Image, ImageTk

from standard_led_matrix_interface import RGBMatrixOptions


class MockRGBMatrix:
    """A small subset of the rpi-rgb-led-matrix API for desktop development."""

    LED_DIAMETER = 4
    LED_GAP = 4
    LED_PITCH = LED_DIAMETER + LED_GAP
    BORDER = 12
    BACKGROUND = "#000000"

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

        self._brightness = max(0, min(100, int(self.options.brightness)))
        self._framebuffer = bytearray(self.width * self.height * 3)
        self._dirty_pixels: set[int] = set()
        self._lit_pixels: set[int] = set()
        self._frame_dirty = False
        self._tk_image: ImageTk.PhotoImage | None = None
        self._panel_image_id: int | None = None
        self._closed = False
        self._channel_lut = [int((value * self._brightness) / 100) for value in range(256)]
        self._resample_nearest = (
            Image.Resampling.NEAREST if hasattr(Image, "Resampling") else Image.NEAREST
        )

        self.root = tk.Tk()
        self.root.title("Mock RGB Matrix 128x64")
        self.root.configure(bg=self.BACKGROUND)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Escape>", lambda _event: self.close())

        self._panel_width = self.width * self.LED_PITCH
        self._panel_height = self.height * self.LED_PITCH
        canvas_width = self.BORDER * 2 + self._panel_width
        canvas_height = self.BORDER * 2 + self._panel_height
        self.canvas = tk.Canvas(
            self.root,
            width=canvas_width,
            height=canvas_height,
            bg=self.BACKGROUND,
            highlightthickness=0,
        )
        self.canvas.pack()

        self._panel_background = Image.new("RGB", (self._panel_width, self._panel_height), (0, 0, 0))
        self._led_area_mask = self._build_led_area_mask()

        self._panel_image_id = self.canvas.create_image(
            self.BORDER,
            self.BORDER,
            anchor="nw",
            image="",
        )
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
        self._frame_dirty = True

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
        self._frame_dirty = True

    def SetPixelsFromBytes(self, frame_bytes: bytes) -> None:
        if self._closed:
            return
        if len(frame_bytes) != len(self._framebuffer):
            raise ValueError(
                f"frame_bytes must contain {len(self._framebuffer)} bytes; got {len(frame_bytes)}"
            )
        if frame_bytes == self._framebuffer:
            return

        self._framebuffer[:] = frame_bytes
        self._dirty_pixels.clear()
        self._frame_dirty = True

    def CreateFrameCanvas(self) -> "MockRGBMatrix":
        return self

    def SwapOnVSync(self, canvas: "MockRGBMatrix") -> "MockRGBMatrix":
        return canvas

    def process(self) -> bool:
        if self._closed:
            return False

        self._blit_frame_if_needed()
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

    def _blit_frame_if_needed(self) -> None:
        if self._frame_dirty:
            self._dirty_pixels.clear()
            self._frame_dirty = False

            source = Image.frombuffer(
                "RGB",
                (self.width, self.height),
                self._framebuffer,
                "raw",
                "RGB",
                0,
                1,
            )
            if self._brightness < 100:
                source = source.point(self._channel_lut * 3)

            display = source.resize(
                (self._panel_width, self._panel_height),
                self._resample_nearest,
            )

            # Re-apply LED spacing so the mock still resembles discrete diodes.
            if self.LED_GAP > 0:
                display = Image.composite(display, self._panel_background, self._led_area_mask)

            if self._tk_image is None:
                self._tk_image = ImageTk.PhotoImage(display)
            else:
                self._tk_image.paste(display)
            if self._panel_image_id is not None:
                self.canvas.itemconfig(self._panel_image_id, image=self._tk_image)

    @staticmethod
    def _clamp_channel(value: int) -> int:
        return max(0, min(255, int(value)))

    def _build_led_area_mask(self) -> Image.Image:
        mask = Image.new("L", (self._panel_width, self._panel_height), 0)
        pixels = mask.load()
        radius = self.LED_DIAMETER / 2.0
        center_offset = (self.LED_DIAMETER - 1) / 2.0
        radius_sq = radius * radius
        for y in range(self.height):
            top = y * self.LED_PITCH
            for x in range(self.width):
                left = x * self.LED_PITCH
                for dy in range(self.LED_DIAMETER):
                    row = top + dy
                    for dx in range(self.LED_DIAMETER):
                        fx = dx - center_offset
                        fy = dy - center_offset
                        if (fx * fx) + (fy * fy) <= radius_sq:
                            pixels[left + dx, row] = 255
        return mask


RGBMatrix = MockRGBMatrix
