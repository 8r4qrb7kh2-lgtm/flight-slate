"""Reusable UI widgets built from the lab primitives."""

from __future__ import annotations

from ui_lab.assets import PixelBitmap
from ui_lab.bitmap_font import FONT_5X7
from ui_lab.canvas import PixelCanvas, Rect
from ui_lab.pages.common import draw_surface
from ui_lab.palette import Color, Palette


def draw_badge(canvas: PixelCanvas, rect: Rect, text: str, palette: Palette, accent: Color) -> str:
    draw_surface(canvas, rect, palette, fill=palette.panel, edge=accent)
    return FONT_5X7.draw_boxed(
        canvas,
        rect.x + 2,
        rect.y + 1,
        rect.width - 4,
        text,
        accent,
        align="center",
        height=rect.height - 2,
        valign="middle",
    )


def draw_progress_bar(
    canvas: PixelCanvas,
    rect: Rect,
    progress: float,
    palette: Palette,
    accent: Color,
    segmented: bool = False,
) -> int:
    progress = max(0.0, min(1.0, progress))
    draw_surface(canvas, rect, palette)
    inner_width = max(0, rect.width - 2)
    fill_width = int(round(inner_width * progress))
    if segmented:
        segment_width = 6
        gap = 1
        cursor = rect.x + 1
        remaining = fill_width
        while remaining > 0:
            draw = min(segment_width, remaining)
            for row in range(rect.y + 1, rect.bottom - 1):
                canvas.hline(cursor, row, draw, accent)
            cursor += segment_width + gap
            remaining -= segment_width + gap
    elif fill_width > 0:
        canvas.rect(Rect(rect.x + 1, rect.y + 1, fill_width, rect.height - 2), fill=accent)
    if fill_width < inner_width:
        marker_x = rect.x + 1 + fill_width
        canvas.vline(marker_x, rect.y, rect.height, palette.text)
    return fill_width


def draw_stat_block(
    canvas: PixelCanvas,
    rect: Rect,
    label: str,
    value: str,
    palette: Palette,
    accent: Color,
    icon: PixelBitmap | None = None,
) -> dict[str, object]:
    draw_surface(canvas, rect, palette)
    text_x = rect.x + 2
    text_width = rect.width - 4
    if icon is not None:
        icon.draw(canvas, rect.x + (rect.width - icon.width) // 2, rect.y + 3)
    FONT_5X7.draw_boxed(canvas, text_x, rect.y + 15, text_width, label, palette.text_dim, align="center")
    FONT_5X7.draw_boxed(canvas, text_x, rect.y + 22, text_width, value, accent, scale=2, align="center")
    return {"value_width": FONT_5X7.measure(value, scale=2)[0]}


def draw_list_item(
    canvas: PixelCanvas,
    rect: Rect,
    title: str,
    subtitle: str,
    right_text: str,
    palette: Palette,
    accent: Color,
    bitmap: PixelBitmap | None = None,
    selected: bool = False,
) -> None:
    edge = palette.text if selected else palette.panel_edge
    draw_surface(canvas, rect, palette, fill=palette.panel, edge=edge)
    if bitmap is not None:
        bitmap.draw(canvas, rect.x + 2, rect.y + max(1, (rect.height - bitmap.height) // 2))
    text_x = rect.x + (14 if bitmap is not None else 3)
    text_width = rect.width - (text_x - rect.x) - 24
    title_y = rect.y + 1
    subtitle_y = rect.y + 8
    FONT_5X7.draw_boxed(canvas, text_x, title_y, text_width, title, palette.text, align="left")
    FONT_5X7.draw_boxed(canvas, text_x, subtitle_y, text_width, subtitle, palette.text_dim, align="left")
    FONT_5X7.draw_boxed(
        canvas,
        rect.right - 24,
        rect.y + 1,
        20,
        right_text,
        accent,
        align="right",
        height=rect.height - 2,
        valign="middle",
    )


def draw_state_card(
    canvas: PixelCanvas,
    rect: Rect,
    title: str,
    subtitle: str,
    palette: Palette,
    accent: Color,
    icon: PixelBitmap | None = None,
) -> None:
    draw_surface(canvas, rect, palette, fill=palette.panel, edge=accent)
    if icon is not None:
        icon.draw(canvas, rect.x + 4, rect.y + max(1, (rect.height - icon.height) // 2))
        text_x = rect.x + 20
    else:
        text_x = rect.x + 4
    text_width = rect.width - (text_x - rect.x) - 4
    FONT_5X7.draw_boxed(
        canvas,
        text_x,
        rect.y + 1,
        text_width,
        title,
        accent,
        align="left",
    )
    if rect.height >= 16:
        FONT_5X7.draw_boxed(
            canvas,
            text_x,
            rect.y + 8,
            text_width,
            subtitle,
            palette.text_dim,
            align="left",
            clip=True,
        )
