"""Simple shared color constants for core UI code."""

from __future__ import annotations

from dataclasses import dataclass

Color = tuple[int, int, int]


@dataclass(frozen=True)
class ColorPalette:
    BLACK: Color = (0, 0, 0)
    BLUE: Color = (0, 64, 255)
    WHITE: Color = (255, 255, 255)
    CYAN: Color = (94, 225, 255)
    DIM_WHITE: Color = (180, 190, 200)


colors = ColorPalette()
