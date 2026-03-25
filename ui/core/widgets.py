"""Declarative core widgets: Panel and Text."""

from __future__ import annotations

from dataclasses import dataclass
from math import floor

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
    overflow_axis: str = "x"
    overflow_offset: float = 0.0
    overflow_gap: int | None = None
    color: Color = colors.WHITE
    line_spacing: int | None = None

    def draw(self, canvas: PixelCanvas, rect: Rect) -> None:
        if rect.width <= 0 or rect.height <= 0:
            return

        if self.overflow == "overflow":
            self._draw_overflow(canvas, rect)
            return

        line_height = self.font.height
        line_spacing = self.font.spacing * 2 if self.line_spacing is None else max(0, self.line_spacing)
        lines = self._resolve_lines(rect.width)
        draw_y = rect.y

        with canvas.clip(rect):
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

    def _draw_overflow(self, canvas: PixelCanvas, rect: Rect) -> None:
        axis = "y" if self.overflow_axis == "y" else "x"
        gap = self.font.spacing * 4 if self.overflow_gap is None else max(0, self.overflow_gap)

        if axis == "x":
            content_extent = self.font.measure(self.text)[0]
            child = Text(
                text=self.text,
                font=self.font,
                align="left",
                overflow="clip",
                color=self.color,
                line_spacing=self.line_spacing,
            )
        else:
            line_spacing = self.font.spacing * 2 if self.line_spacing is None else max(0, self.line_spacing)
            lines = _wrap_text(self.font, self.text, rect.width)
            line_count = max(1, len(lines))
            content_extent = (line_count * self.font.height) + ((line_count - 1) * line_spacing)
            child = Text(
                text=self.text,
                font=self.font,
                align=self.align,
                overflow="wrap",
                color=self.color,
                line_spacing=self.line_spacing,
            )

        Marquee(
            child=child,
            axis=axis,
            offset=self.overflow_offset,
            content_extent=content_extent,
            gap=gap,
        ).draw(canvas, rect)

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

        border_inset = 1 if self.border is not None else 0
        inset = self.padding + border_inset
        inner_x = rect.x + inset
        inner_y = rect.y + inset
        inner_width = max(0, rect.width - inset * 2)
        inner_height = max(0, rect.height - inset * 2)
        if self.child is None or inner_width == 0 or inner_height == 0:
            return

        self.child.draw(canvas, Rect(inner_x, inner_y, inner_width, inner_height))


@dataclass
class Marquee(Widget):
    child: Widget
    axis: str = "x"
    offset: float = 0.0
    content_extent: int | None = None
    gap: int = 0

    def draw(self, canvas: PixelCanvas, rect: Rect) -> None:
        if rect.width <= 0 or rect.height <= 0 or self.child is None:
            return

        axis = "y" if self.axis == "y" else "x"
        axis_total = rect.height if axis == "y" else rect.width
        if axis_total <= 0:
            return

        gap = max(0, self.gap)
        content_extent = self.content_extent
        if content_extent is None:
            content_extent = _estimate_axis_extent(self.child, rect, axis)
        if content_extent is None or content_extent <= 0:
            self.child.draw(canvas, rect)
            return

        step = content_extent + gap
        if step <= 0:
            self.child.draw(canvas, rect)
            return

        integer_offset = int(floor(self.offset))
        self._draw_integer(canvas, rect, axis, axis_total, content_extent, step, integer_offset)

    def _draw_integer(
        self,
        canvas: PixelCanvas,
        rect: Rect,
        axis: str,
        axis_total: int,
        content_extent: int,
        step: int,
        offset: int,
    ) -> None:
        shift = offset % step
        start = -shift
        with canvas.clip(rect):
            while start < axis_total:
                if axis == "x":
                    child_rect = Rect(rect.x + start, rect.y, content_extent, rect.height)
                else:
                    child_rect = Rect(rect.x, rect.y + start, rect.width, content_extent)
                self.child.draw(canvas, child_rect)
                start += step


@dataclass
class Column(Widget):
    children: list[Widget]
    gap: int = 0
    sizes: list[int] | None = None

    def draw(self, canvas: PixelCanvas, rect: Rect) -> None:
        if rect.width <= 0 or rect.height <= 0 or not self.children:
            return

        if self.sizes is not None:
            _draw_weighted_stack(
                canvas=canvas,
                rect=rect,
                children=self.children,
                gap=self.gap,
                sizes=self.sizes,
                horizontal=False,
            )
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


@dataclass
class Row(Widget):
    children: list[Widget]
    gap: int = 0
    sizes: list[int] | None = None

    def draw(self, canvas: PixelCanvas, rect: Rect) -> None:
        if rect.width <= 0 or rect.height <= 0 or not self.children:
            return

        if self.sizes is None:
            slot_count = len(self.children)
            sizes = [1] * slot_count
        else:
            slot_count = len(self.sizes)
            sizes = self.sizes

        _draw_weighted_stack(
            canvas=canvas,
            rect=rect,
            children=self.children,
            gap=self.gap,
            sizes=sizes,
            horizontal=True,
        )


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
        border_inset = 1 if widget.border is not None else 0
        inset = widget.padding + border_inset
        inner_width = max(0, width - inset * 2)
        child_height = _estimate_height(widget.child, inner_width)
        return child_height + (inset * 2)
    if isinstance(widget, Column):
        total = 0
        for idx, child in enumerate(widget.children):
            total += _estimate_height(child, width)
            if idx != len(widget.children) - 1:
                total += widget.gap
        return total
    return 0


def _draw_weighted_stack(
    canvas: PixelCanvas,
    rect: Rect,
    children: list[Widget],
    gap: int,
    sizes: list[int],
    horizontal: bool,
) -> None:
    if not sizes:
        raise ValueError("sizes must contain at least one slot")

    if len(children) > len(sizes):
        raise ValueError("children exceed configured slot count")

    if any(size < 0 for size in sizes):
        raise ValueError("sizes must be non-negative")

    size_total = sum(sizes)
    if size_total <= 0:
        raise ValueError("sizes must sum to a positive value")

    gap = max(0, gap)
    slot_count = len(sizes)
    axis_total = rect.width if horizontal else rect.height
    usable_total = max(0, axis_total - (gap * (slot_count - 1)))
    slot_extents = _allocate_weighted_extents(usable_total, sizes)

    cursor_x = rect.x
    cursor_y = rect.y
    for index, slot_extent in enumerate(slot_extents):
        if index < len(children) and slot_extent > 0:
            if horizontal:
                child_rect = Rect(cursor_x, rect.y, slot_extent, rect.height)
            else:
                child_rect = Rect(rect.x, cursor_y, rect.width, slot_extent)
            children[index].draw(canvas, child_rect)

        if horizontal:
            cursor_x += slot_extent
            if index != slot_count - 1:
                cursor_x += gap
        else:
            cursor_y += slot_extent
            if index != slot_count - 1:
                cursor_y += gap


def _allocate_weighted_extents(total: int, sizes: list[int]) -> list[int]:
    if total <= 0:
        return [0] * len(sizes)

    size_total = sum(sizes)
    cumulative = 0
    previous_edge = 0
    extents: list[int] = []

    # Derive slot edges from cumulative integer proportions.
    for size in sizes:
        cumulative += size
        edge = (total * cumulative) // size_total
        extents.append(edge - previous_edge)
        previous_edge = edge

    return extents


def _estimate_axis_extent(widget: Widget, rect: Rect, axis: str) -> int:
    if isinstance(widget, Text):
        if axis == "x":
            return widget.font.measure(widget.text)[0]

        line_spacing = widget.font.spacing * 2 if widget.line_spacing is None else max(0, widget.line_spacing)
        lines = widget._resolve_lines(rect.width)
        line_count = max(1, len(lines))
        return (line_count * widget.font.height) + ((line_count - 1) * line_spacing)

    if isinstance(widget, Panel):
        border_inset = 1 if widget.border is not None else 0
        inset = widget.padding + border_inset
        inner_rect = Rect(
            rect.x,
            rect.y,
            max(0, rect.width - inset * 2),
            max(0, rect.height - inset * 2),
        )
        return _estimate_axis_extent(widget.child, inner_rect, axis) + (inset * 2)

    if isinstance(widget, Row):
        if axis == "y":
            return rect.height
        total = 0
        for index, child in enumerate(widget.children):
            total += _estimate_axis_extent(child, rect, axis)
            if index != len(widget.children) - 1:
                total += widget.gap
        return total

    if isinstance(widget, Column):
        if axis == "x":
            widest = 0
            for child in widget.children:
                widest = max(widest, _estimate_axis_extent(child, rect, axis))
            return widest
        total = 0
        for index, child in enumerate(widget.children):
            total += _estimate_axis_extent(child, rect, axis)
            if index != len(widget.children) - 1:
                total += widget.gap
        return total

    return rect.height if axis == "y" else rect.width
