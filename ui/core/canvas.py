"""Pixel drawing primitives for the standalone core UI layer."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

try:
    from PIL import Image
except Exception:  # pragma: no cover - Pillow is optional for save-only paths.
    Image = None

from ui.native import native_backend

Color = tuple[int, int, int]


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height


class PixelCanvas:
    def __init__(self, width: int, height: int, background: Color) -> None:
        self.width = width
        self.height = height
        self.background = background
        self._clip_stack: list[Rect] = []
        self._native = self._create_native_backend(width, height, background)
        self._buffer = bytearray(width * height * 3)
        self.clear(background)
        self.image = _ImageView(self)

    @staticmethod
    def _create_native_backend(width: int, height: int, background: Color):
        if native_backend is None:
            return None
        try:
            return native_backend.NativeCanvas(width, height, background)
        except Exception:
            return None

    def clear(self, color: Color | None = None) -> None:
        fill = color or self.background
        if self._native is not None:
            self._native.clear(fill)
            return
        r, g, b = fill
        for base in range(0, len(self._buffer), 3):
            self._buffer[base] = r
            self._buffer[base + 1] = g
            self._buffer[base + 2] = b

    def pixel(self, x: int, y: int, color: Color) -> None:
        if self._native is not None:
            self._native.pixel(x, y, color)
            return
        if 0 <= x < self.width and 0 <= y < self.height and self._inside_clip(x, y):
            base = self._pixel_base(x, y)
            self._buffer[base] = color[0]
            self._buffer[base + 1] = color[1]
            self._buffer[base + 2] = color[2]

    def blend_pixel(self, x: int, y: int, color: Color, alpha: float) -> None:
        if self._native is not None:
            self._native.blend_pixel(x, y, color, alpha)
            return
        if not (0 <= x < self.width and 0 <= y < self.height and self._inside_clip(x, y)):
            return
        if alpha <= 0:
            return
        if alpha >= 1:
            self.pixel(x, y, color)
            return

        base = self._pixel_base(x, y)
        base_r, base_g, base_b = self._buffer[base], self._buffer[base + 1], self._buffer[base + 2]
        blend_r = int(round(base_r + ((color[0] - base_r) * alpha)))
        blend_g = int(round(base_g + ((color[1] - base_g) * alpha)))
        blend_b = int(round(base_b + ((color[2] - base_b) * alpha)))
        self._buffer[base] = blend_r
        self._buffer[base + 1] = blend_g
        self._buffer[base + 2] = blend_b

    @contextmanager
    def clip(self, rect: Rect):
        self._clip_stack.append(rect)
        if self._native is not None:
            self._native.push_clip(rect.x, rect.y, rect.width, rect.height)
        try:
            yield
        finally:
            if self._native is not None:
                self._native.pop_clip()
            self._clip_stack.pop()

    def _inside_clip(self, x: int, y: int) -> bool:
        if not self._clip_stack:
            return True
        for clip in self._clip_stack:
            if not (clip.x <= x < clip.right and clip.y <= y < clip.bottom):
                return False
        return True

    def hline(self, x: int, y: int, width: int, color: Color) -> None:
        if self._native is not None:
            self._native.hline(x, y, width, color)
            return
        for offset in range(max(0, width)):
            self.pixel(x + offset, y, color)

    def vline(self, x: int, y: int, height: int, color: Color) -> None:
        if self._native is not None:
            self._native.vline(x, y, height, color)
            return
        for offset in range(max(0, height)):
            self.pixel(x, y + offset, color)

    def rect(self, rect: Rect, fill: Color | None = None, outline: Color | None = None) -> None:
        if rect.width <= 0 or rect.height <= 0:
            return
        if fill is not None:
            if self._native is not None:
                self._native.fill_rect(rect.x, rect.y, rect.width, rect.height, fill)
            else:
                for row in range(rect.y, rect.bottom):
                    self.hline(rect.x, row, rect.width, fill)
        if outline is not None:
            if self._native is not None:
                self._native.outline_rect(rect.x, rect.y, rect.width, rect.height, outline)
            else:
                self.hline(rect.x, rect.y, rect.width, outline)
                self.hline(rect.x, rect.bottom - 1, rect.width, outline)
                self.vline(rect.x, rect.y, rect.height, outline)
                self.vline(rect.right - 1, rect.y, rect.height, outline)

    def draw_text_native(
        self,
        *,
        x: int,
        y: int,
        text: str,
        color: Color,
        scale: int,
        spacing: int,
        space_width: int,
        glyph_map: dict[str, tuple[int, tuple[int, ...]]],
        fallback_glyph: tuple[int, tuple[int, ...]],
    ) -> bool:
        if self._native is None:
            return False
        self._native.draw_text(
            x,
            y,
            text,
            color,
            scale,
            spacing,
            space_width,
            glyph_map,
            fallback_glyph,
        )
        return True

    def to_bytes(self) -> bytes:
        if self._native is not None:
            return self._native.to_bytes()
        return bytes(self._buffer)

    def get_pixel(self, x: int, y: int) -> Color:
        if self._native is not None:
            pixel = self._native.get_pixel(x, y)
            return int(pixel[0]), int(pixel[1]), int(pixel[2])
        base = self._pixel_base(x, y)
        return self._buffer[base], self._buffer[base + 1], self._buffer[base + 2]

    def _pixel_base(self, x: int, y: int) -> int:
        return ((y * self.width) + x) * 3

    def save(self, path: Path) -> None:
        self.image.save(path)


class _PixelAccess:
    def __init__(self, canvas: PixelCanvas) -> None:
        self._canvas = canvas

    def __getitem__(self, key: tuple[int, int]) -> Color:
        x, y = key
        return self._canvas.get_pixel(x, y)


class _ImageView:
    def __init__(self, canvas: PixelCanvas) -> None:
        self._canvas = canvas

    def load(self) -> _PixelAccess:
        return _PixelAccess(self._canvas)

    def tobytes(self) -> bytes:
        return self._canvas.to_bytes()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if Image is None:
            raise RuntimeError("Pillow is required for image export")
        image = Image.frombytes("RGB", (self._canvas.width, self._canvas.height), self.tobytes())
        image.save(path)
