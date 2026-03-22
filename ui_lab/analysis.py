"""Reusable page analysis helpers."""

from __future__ import annotations

from ui_lab.canvas import PixelCanvas
from ui_lab.palette import Color


def non_background_pixels(canvas: PixelCanvas) -> int:
    pixels = canvas.image.load()
    count = 0
    for y in range(canvas.height):
        for x in range(canvas.width):
            if pixels[x, y] != canvas.background:
                count += 1
    return count


def content_bounds(canvas: PixelCanvas) -> tuple[int, int, int, int] | None:
    pixels = canvas.image.load()
    lit = [
        (x, y)
        for y in range(canvas.height)
        for x in range(canvas.width)
        if pixels[x, y] != canvas.background
    ]
    if not lit:
        return None
    xs = [x for x, _y in lit]
    ys = [y for _x, y in lit]
    return min(xs), min(ys), max(xs), max(ys)


def unexpected_colors(canvas: PixelCanvas, allowed_colors: set[Color]) -> list[Color]:
    return sorted(canvas.used_colors() - allowed_colors)


def row_color_count(canvas: PixelCanvas, y: int, color: Color) -> int:
    pixels = canvas.image.load()
    return sum(1 for x in range(canvas.width) if pixels[x, y] == color)


def column_color_count(canvas: PixelCanvas, x: int, color: Color) -> int:
    pixels = canvas.image.load()
    return sum(1 for y in range(canvas.height) if pixels[x, y] == color)


def basic_analysis(canvas: PixelCanvas, allowed_colors: set[Color], **extra: object) -> dict[str, object]:
    return {
        "used_colors": sorted(canvas.used_colors()),
        "unexpected_colors": unexpected_colors(canvas, allowed_colors),
        "non_background_pixels": non_background_pixels(canvas),
        "content_bounds": content_bounds(canvas),
        **extra,
    }
