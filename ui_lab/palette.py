"""Shared LED-safe colors for the feature lab."""

from __future__ import annotations

from dataclasses import dataclass

Color = tuple[int, int, int]


def rgb(value: str) -> Color:
    value = value.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


@dataclass(frozen=True)
class Palette:
    background: Color = rgb("#081018")
    panel: Color = rgb("#102030")
    panel_edge: Color = rgb("#28445c")
    text: Color = rgb("#f2f8ff")
    text_dim: Color = rgb("#8aa3b8")
    accent: Color = rgb("#5ee1ff")
    accent_alt: Color = rgb("#ffd166")
    success: Color = rgb("#92ff9a")
    error: Color = rgb("#ff6f7c")
