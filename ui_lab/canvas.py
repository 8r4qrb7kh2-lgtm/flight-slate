"""Pixel-perfect drawing primitives for 128x64 feature pages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from ui_lab.palette import Color


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

    def clear(self, color: Color | None = None) -> None:
        self.image.paste(color or self.background, (0, 0, self.width, self.height))

    def pixel(self, x: int, y: int, color: Color) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self.image.putpixel((x, y), color)

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

    def line(self, x0: int, y0: int, x1: int, y1: int, color: Color) -> None:
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        step_x = 1 if x0 < x1 else -1
        step_y = 1 if y0 < y1 else -1
        error = dx + dy
        while True:
            self.pixel(x0, y0, color)
            if x0 == x1 and y0 == y1:
                break
            double_error = error * 2
            if double_error >= dy:
                error += dy
                x0 += step_x
            if double_error <= dx:
                error += dx
                y0 += step_y

    def polyline(self, points: list[tuple[int, int]], color: Color, closed: bool = False) -> None:
        if len(points) < 2:
            return
        for start, end in zip(points, points[1:]):
            self.line(start[0], start[1], end[0], end[1], color)
        if closed:
            self.line(points[-1][0], points[-1][1], points[0][0], points[0][1], color)

    def circle(self, center_x: int, center_y: int, radius: int, color: Color, fill: bool = False) -> None:
        if radius < 0:
            return
        x = radius
        y = 0
        error = 1 - x
        while x >= y:
            if fill:
                self.hline(center_x - x, center_y + y, x * 2 + 1, color)
                self.hline(center_x - x, center_y - y, x * 2 + 1, color)
                self.hline(center_x - y, center_y + x, y * 2 + 1, color)
                self.hline(center_x - y, center_y - x, y * 2 + 1, color)
            else:
                for px, py in (
                    (center_x + x, center_y + y),
                    (center_x + y, center_y + x),
                    (center_x - y, center_y + x),
                    (center_x - x, center_y + y),
                    (center_x - x, center_y - y),
                    (center_x - y, center_y - x),
                    (center_x + y, center_y - x),
                    (center_x + x, center_y - y),
                ):
                    self.pixel(px, py, color)
            y += 1
            if error < 0:
                error += 2 * y + 1
            else:
                x -= 1
                error += 2 * (y - x + 1)

    def blit(self, source: Image.Image, x: int, y: int) -> None:
        self.image.paste(source, (x, y))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.image.save(path)

    def save_upscaled(self, path: Path, scale: int = 8) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        enlarged = self.image.resize((self.width * scale, self.height * scale), Image.Resampling.NEAREST)
        enlarged.save(path)

    def used_colors(self) -> set[Color]:
        pixels = self.image.load()
        return {pixels[x, y] for y in range(self.height) for x in range(self.width)}

    def ascii_dump(self, mapping: dict[Color, str]) -> str:
        pixels = self.image.load()
        lines: list[str] = []
        for y in range(self.height):
            row = []
            for x in range(self.width):
                color = pixels[x, y]
                row.append(mapping.get(color, "?"))
            lines.append("".join(row))
        return "\n".join(lines)
