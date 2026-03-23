"""Bitmap assets used by the minimal 3-page UI lab."""

from __future__ import annotations

from dataclasses import dataclass

from ui_lab.canvas import PixelCanvas
from ui_lab.palette import Color, rgb


@dataclass(frozen=True)
class PixelBitmap:
    rows: tuple[str, ...]
    palette: dict[str, Color]

    @property
    def width(self) -> int:
        return max((len(row) for row in self.rows), default=0)

    @property
    def height(self) -> int:
        return len(self.rows)

    def draw(self, canvas: PixelCanvas, x: int, y: int, scale: int = 1) -> None:
        for row_index, row in enumerate(self.rows):
            for column_index, key in enumerate(row):
                if key == ".":
                    continue
                color = self.palette[key]
                for offset_y in range(scale):
                    for offset_x in range(scale):
                        canvas.pixel(
                            x + column_index * scale + offset_x,
                            y + row_index * scale + offset_y,
                            color,
                        )


def _bitmap(rows: tuple[str, ...], palette: dict[str, str]) -> PixelBitmap:
    return PixelBitmap(rows=rows, palette={key: rgb(value) for key, value in palette.items()})


def icon_registry() -> dict[str, PixelBitmap]:
    return {
        "live": _bitmap(
            (
                "...1.....",
                "..111....",
                ".11111...",
                "1111111..",
                ".11111...",
                "..111....",
                "...1.....",
                ".........",
                "...1.....",
            ),
            {"1": "#92ff9a"},
        ),
        "list": _bitmap(
            (
                "111111111",
                ".........",
                "111111111",
                ".........",
                "111111111",
                ".........",
                "111111111",
                ".........",
                "111111111",
            ),
            {"1": "#5ee1ff"},
        ),
    }
