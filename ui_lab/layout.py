"""Minimal retained-layout primitives for compact text-first screens."""

from __future__ import annotations

from dataclasses import dataclass

from ui_lab.bitmap_font import FONT_5X7
from ui_lab.canvas import PixelCanvas, Rect
from ui_lab.palette import Palette


@dataclass(frozen=True)
class TextStyle:
    color_name: str = "text"


TITLE = TextStyle(color_name="accent")
BODY = TextStyle(color_name="text")
MUTED = TextStyle(color_name="text_dim")


class Widget:
    def measure(self, palette: Palette) -> tuple[int, int]:
        raise NotImplementedError

    def render(self, canvas: PixelCanvas, rect: Rect, palette: Palette) -> None:
        raise NotImplementedError


@dataclass
class Label(Widget):
    text: str
    style: TextStyle = BODY

    def measure(self, palette: Palette) -> tuple[int, int]:
        del palette
        return FONT_5X7.measure(self.text)

    def render(self, canvas: PixelCanvas, rect: Rect, palette: Palette) -> None:
        FONT_5X7.render(canvas, rect.x, rect.y, self.text, getattr(palette, self.style.color_name))


@dataclass
class Row(Widget):
    children: list[Widget]
    gap: int = 0

    def measure(self, palette: Palette) -> tuple[int, int]:
        if not self.children:
            return 0, 0
        sizes = [child.measure(palette) for child in self.children]
        width = sum(child_width for child_width, _ in sizes) + self.gap * (len(sizes) - 1)
        height = max(child_height for _, child_height in sizes)
        return width, height

    def render(self, canvas: PixelCanvas, rect: Rect, palette: Palette) -> None:
        cursor_x = rect.x
        for child in self.children:
            child_width, child_height = child.measure(palette)
            offset_y = max(0, (rect.height - child_height) // 2)
            child.render(canvas, Rect(cursor_x, rect.y + offset_y, child_width, child_height), palette)
            cursor_x += child_width + self.gap


@dataclass
class Column(Widget):
    children: list[Widget]
    padding: int = 0
    gap: int = 0

    def measure(self, palette: Palette) -> tuple[int, int]:
        if not self.children:
            return self.padding * 2, self.padding * 2
        sizes = [child.measure(palette) for child in self.children]
        width = max(child_width for child_width, _ in sizes) + self.padding * 2
        height = sum(child_height for _, child_height in sizes) + self.padding * 2
        height += self.gap * (len(sizes) - 1)
        return width, height

    def render(self, canvas: PixelCanvas, rect: Rect, palette: Palette) -> None:
        cursor_y = rect.y + self.padding
        inner_x = rect.x + self.padding
        for child in self.children:
            child_width, child_height = child.measure(palette)
            child.render(canvas, Rect(inner_x, cursor_y, child_width, child_height), palette)
            cursor_y += child_height + self.gap
