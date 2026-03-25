"""Pixel drawing primitives for the standalone core UI layer."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

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
        self.image = Image.new("RGB", (width, height), background)
        self._clip_stack: list[Rect] = []

    def clear(self, color: Color | None = None) -> None:
        self.image.paste(color or self.background, (0, 0, self.width, self.height))

    def pixel(self, x: int, y: int, color: Color) -> None:
        if 0 <= x < self.width and 0 <= y < self.height and self._inside_clip(x, y):
            self.image.putpixel((x, y), color)

    def blend_pixel(self, x: int, y: int, color: Color, alpha: float) -> None:
        if not (0 <= x < self.width and 0 <= y < self.height and self._inside_clip(x, y)):
            return
        if alpha <= 0:
            return
        if alpha >= 1:
            self.image.putpixel((x, y), color)
            return

        base_r, base_g, base_b = self.image.getpixel((x, y))
        blend_r = int(round(base_r + ((color[0] - base_r) * alpha)))
        blend_g = int(round(base_g + ((color[1] - base_g) * alpha)))
        blend_b = int(round(base_b + ((color[2] - base_b) * alpha)))
        self.image.putpixel((x, y), (blend_r, blend_g, blend_b))

    @contextmanager
    def clip(self, rect: Rect):
        self._clip_stack.append(rect)
        try:
            yield
        finally:
            self._clip_stack.pop()

    def _inside_clip(self, x: int, y: int) -> bool:
        if not self._clip_stack:
            return True
        for clip in self._clip_stack:
            if not (clip.x <= x < clip.right and clip.y <= y < clip.bottom):
                return False
        return True

    def hline(self, x: int, y: int, width: int, color: Color) -> None:
        for offset in range(max(0, width)):
            self.pixel(x + offset, y, color)

    def vline(self, x: int, y: int, height: int, color: Color) -> None:
        for offset in range(max(0, height)):
            self.pixel(x, y + offset, color)

    def rect(self, rect: Rect, fill: Color | None = None, outline: Color | None = None) -> None:
        if rect.width <= 0 or rect.height <= 0:
            return
        if fill is not None:
            for row in range(rect.y, rect.bottom):
                self.hline(rect.x, row, rect.width, fill)
        if outline is not None:
            self.hline(rect.x, rect.y, rect.width, outline)
            self.hline(rect.x, rect.bottom - 1, rect.width, outline)
            self.vline(rect.x, rect.y, rect.height, outline)
            self.vline(rect.right - 1, rect.y, rect.height, outline)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.image.save(path)
