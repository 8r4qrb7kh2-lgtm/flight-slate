"""Bitmap assets for icons, images, and logos."""

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
        "plane": _bitmap(
            (
                "...1.....",
                "...11....",
                "111111111",
                ".1111111.",
                "...11....",
                "...1.....",
                "..1......",
                ".1.......",
                "1........",
            ),
            {"1": "#f2f8ff"},
        ),
        "clock": _bitmap(
            (
                "..11111..",
                ".11...11.",
                "11.....11",
                "11..1..11",
                "11..11.11",
                "11.....11",
                ".11...11.",
                "..11111..",
                "....1....",
            ),
            {"1": "#ffd166"},
        ),
        "pin": _bitmap(
            (
                "...111...",
                "..11111..",
                "..11111..",
                "..11111..",
                "...111...",
                "...111...",
                "...1.1...",
                "..1...1..",
                ".1.....1.",
            ),
            {"1": "#ff6f7c"},
        ),
        "warning": _bitmap(
            (
                "....1....",
                "...111...",
                "..11111..",
                ".1111111.",
                ".1111111.",
                "...111...",
                "...111...",
                ".........",
                "...111...",
            ),
            {"1": "#ffd166"},
        ),
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


def logo_registry() -> dict[str, PixelBitmap]:
    return {
        "slate": _bitmap(
            (
                "...1111........",
                "..11..11.......",
                "......11.......",
                "....111........",
                "..111..........",
                ".11............",
                ".111111........",
                ".....111.......",
                "......11.......",
                "..11..11.......",
                "...1111........",
            ),
            {"1": "#5ee1ff"},
        ),
        "meridian": _bitmap(
            (
                "11.......11....",
                "111.....111....",
                "1.11...11.1....",
                "1..11.11..1....",
                "1...111...1....",
                "1....1....1....",
                "1.........1....",
                "1.........1....",
                "1.........1....",
                "1.........1....",
                "1.........1....",
            ),
            {"1": "#ffd166"},
        ),
        "harbor": _bitmap(
            (
                "11.....11......",
                "11.....11......",
                "11.....11......",
                "111111111......",
                "111111111......",
                "11.....11......",
                "11.....11......",
                "11.....11......",
                "11.....11......",
                "11.....11......",
                "11.....11......",
            ),
            {"1": "#92ff9a"},
        ),
    }


def image_registry() -> dict[str, PixelBitmap]:
    return {
        "skyline": _bitmap(
            (
                "................",
                "................",
                ".1....22....1...",
                ".11...22...111..",
                ".11...22...111..",
                ".111..22..1111..",
                ".111..22..1111..",
                ".1111.22.11111..",
                ".1111.22.11111..",
                ".1111112211111..",
                ".1111112211111..",
                "111111122111111.",
                "111111122111111.",
                "3333333333333333",
                "3333333333333333",
                "................",
            ),
            {"1": "#8aa3b8", "2": "#5ee1ff", "3": "#102030"},
        ),
    }
