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
