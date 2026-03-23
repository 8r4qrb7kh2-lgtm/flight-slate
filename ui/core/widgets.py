"""Declarative core widgets: Panel and Text."""

from __future__ import annotations

from dataclasses import dataclass

from ui.core.bitmap_font import BitmapFont
from ui.core.canvas import PixelCanvas, Rect
from ui.core.colors import Color, colors


class Widget:
    def draw(self, canvas: PixelCanvas, rect: Rect) -> None:
        raise NotImplementedError


@dataclass
class Text(Widget):
    text: str
    font: BitmapFont
    align: str = "left"
    overflow: str = "clip"
    color: Color = colors.WHITE
    line_spacing: int | None = None

    def draw(self, canvas: PixelCanvas, rect: Rect) -> None:
        if rect.width <= 0 or rect.height <= 0:
            return

        line_height = self.font.height
        line_spacing = self.font.spacing * 2 if self.line_spacing is None else max(0, self.line_spacing)
        lines = self._resolve_lines(rect.width)
        draw_y = rect.y

        for line in lines:
            if draw_y + line_height > rect.bottom:
                break
            line_width, _ = self.font.measure(line)
            if self.align == "center":
                draw_x = rect.x + max(0, (rect.width - line_width) // 2)
            elif self.align == "right":
                draw_x = rect.x + max(0, rect.width - line_width)
            else:
                draw_x = rect.x
            self.font.render(canvas, draw_x, draw_y, line, self.color)
            draw_y += line_height + line_spacing

    def _resolve_lines(self, width: int) -> list[str]:
        if self.overflow == "wrap":
            return _wrap_text(self.font, self.text, width)
        return [self.font.clip(self.text, width)]


@dataclass
class Panel(Widget):
    child: Widget
    padding: int = 0
    bg: Color = colors.BLACK
    border: Color | None = None

    def draw(self, canvas: PixelCanvas, rect: Rect) -> None:
        canvas.rect(rect, fill=self.bg, outline=self.border)

        inner_x = rect.x + self.padding
        inner_y = rect.y + self.padding
        inner_width = max(0, rect.width - self.padding * 2)
        inner_height = max(0, rect.height - self.padding * 2)
        if self.child is None or inner_width == 0 or inner_height == 0:
            return

        self.child.draw(canvas, Rect(inner_x, inner_y, inner_width, inner_height))


@dataclass
class Column(Widget):
    children: list[Widget]
    gap: int = 0

    def draw(self, canvas: PixelCanvas, rect: Rect) -> None:
        if rect.width <= 0 or rect.height <= 0 or not self.children:
            return

        cursor_y = rect.y
        for index, child in enumerate(self.children):
            if cursor_y >= rect.bottom:
                break

            child_height = _estimate_height(child, rect.width)
            remaining = rect.bottom - cursor_y
            if child_height <= 0:
                child_height = remaining
            draw_height = min(child_height, remaining)
            child.draw(canvas, Rect(rect.x, cursor_y, rect.width, draw_height))
            cursor_y += draw_height
            if index != len(self.children) - 1:
                cursor_y += self.gap


def _wrap_text(font: BitmapFont, text: str, width: int) -> list[str]:
    if not text:
        return [""]

    wrapped: list[str] = []
    current = ""

    for char in text:
        candidate = current + char
        if not current:
            current = char
            continue

        if font.measure(candidate)[0] <= width:
            current = candidate
            continue

        wrapped.append(current)
        current = char

    if current:
        wrapped.append(current)

    return wrapped


def _estimate_height(widget: Widget, width: int) -> int:
    if isinstance(widget, Text):
        line_spacing = widget.font.spacing * 2 if widget.line_spacing is None else max(0, widget.line_spacing)
        line_count = len(widget._resolve_lines(width))
        if line_count <= 0:
            return 0
        return (line_count * widget.font.height) + ((line_count - 1) * line_spacing)
    if isinstance(widget, Panel):
        inner_width = max(0, width - widget.padding * 2)
        child_height = _estimate_height(widget.child, inner_width)
        return child_height + (widget.padding * 2)
    if isinstance(widget, Column):
        total = 0
        for idx, child in enumerate(widget.children):
            total += _estimate_height(child, width)
            if idx != len(widget.children) - 1:
                total += widget.gap
        return total
    return 0
