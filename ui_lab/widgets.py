"""Reusable UI widgets built from the lab primitives."""

from __future__ import annotations

from ui_lab.assets import PixelBitmap
from ui_lab.bitmap_font import FONT_5X7
from ui_lab.canvas import PixelCanvas, Rect
from ui_lab.pages.common import draw_bitmap_centered, draw_surface
from ui_lab.palette import Color, Palette


def draw_badge(canvas: PixelCanvas, rect: Rect, text: str, palette: Palette, accent: Color) -> str:
    draw_surface(canvas, rect, palette, fill=palette.panel, edge=accent)
    return FONT_5X7.draw_boxed(
        canvas,
        rect.x + 2,
        rect.y,
        rect.width - 4,
        text,
        accent,
        align="center",
        height=rect.height,
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
    text_x = rect.x + 1
    text_width = rect.width - 2
    if icon is not None:
        draw_bitmap_centered(icon, canvas, Rect(rect.x + 2, rect.y + 3, rect.width - 4, 8))
    FONT_5X7.draw_boxed(canvas, text_x, rect.y + 14, text_width, value, accent, scale=2, align="center")
    FONT_5X7.draw_boxed(canvas, text_x, rect.y + 29, text_width, label, palette.text_dim, align="center")
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
        logo_box = Rect(rect.x + 3, rect.y + 2, 20, rect.height - 4)
        draw_bitmap_centered(bitmap, canvas, logo_box)
        text_x = logo_box.right + 4
    else:
        text_x = rect.x + 4
    right_width = 20
    text_width = rect.width - (text_x - rect.x) - right_width - 4
    title_y = rect.y + 2
    subtitle_y = rect.y + 11
    FONT_5X7.draw_boxed(canvas, text_x, title_y, text_width, title, palette.text, align="left")
    FONT_5X7.draw_boxed(canvas, text_x, subtitle_y, text_width, subtitle, palette.text_dim, align="left")
    FONT_5X7.draw_boxed(
        canvas,
        rect.right - right_width - 2,
        rect.y + 2,
        right_width,
        right_text,
        accent,
        align="right",
        height=rect.height - 4,
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
        draw_bitmap_centered(icon, canvas, Rect(rect.x + 4, rect.y + 2, 8, rect.height - 4))
        text_x = rect.x + 16
    else:
        text_x = rect.x + 4
    text_width = rect.width - (text_x - rect.x) - 4
    if subtitle and rect.height >= 16:
        FONT_5X7.draw_boxed(
            canvas,
            text_x,
            rect.y + 2,
            text_width,
            title,
            accent,
            align="left",
        )
        FONT_5X7.draw_boxed(
            canvas,
            text_x,
            rect.y + 9,
            text_width,
            subtitle,
            palette.text_dim,
            align="left",
            clip=True,
        )
    else:
        FONT_5X7.draw_boxed(
            canvas,
            text_x,
            rect.y,
            text_width,
            title,
            accent,
            align="left",
            height=rect.height,
            valign="middle",
        )
