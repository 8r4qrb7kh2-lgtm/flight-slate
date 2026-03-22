"""Shared drawing helpers for feature pages."""

from __future__ import annotations

from ui_lab.assets import PixelBitmap
from ui_lab.bitmap_font import FONT_5X7
from ui_lab.canvas import PixelCanvas, Rect
from ui_lab.palette import Color, Palette

PAGE_INSET_X = 8
CONTENT_TOP = 18
CONTENT_WIDTH = 112
FOOTER_Y = 53
THREE_COL_WIDTH = 36
THREE_COL_GAP = 2
TWO_COL_WIDTH = 54
TWO_COL_GAP = 4


def draw_surface(canvas: PixelCanvas, rect: Rect, palette: Palette, fill: Color | None = None, edge: Color | None = None) -> None:
    canvas.rect(rect, fill=fill or palette.panel, outline=edge or palette.panel_edge)


def draw_page_shell(canvas: PixelCanvas, palette: Palette, title: str, page_number: str) -> None:
    canvas.clear(palette.background)
    canvas.rect(Rect(0, 0, 128, 64), outline=palette.panel_edge)
    canvas.rect(Rect(1, 1, 126, 62), outline=palette.panel)
    header = Rect(4, 4, 120, 11)
    draw_surface(canvas, header, palette)
    FONT_5X7.draw_boxed(canvas, 8, header.y, 76, title, palette.text, align="left", height=header.height, valign="middle")
    FONT_5X7.draw_boxed(canvas, 88, header.y, 32, page_number, palette.text_dim, align="right", height=header.height, valign="middle")


def draw_bitmap(bitmap: PixelBitmap, canvas: PixelCanvas, x: int, y: int, scale: int = 1) -> None:
    bitmap.draw(canvas, x, y, scale=scale)


def draw_bitmap_centered(bitmap: PixelBitmap, canvas: PixelCanvas, rect: Rect, scale: int = 1) -> tuple[int, int]:
    draw_x = rect.x + max(0, (rect.width - bitmap.content_width * scale) // 2)
    draw_y = rect.y + max(0, (rect.height - bitmap.content_height * scale) // 2)
    bitmap.draw_trimmed(canvas, draw_x, draw_y, scale=scale)
    return draw_x, draw_y


def draw_caption(canvas: PixelCanvas, x: int, y: int, text: str, palette: Palette, accent: Color | None = None) -> None:
    FONT_5X7.render(canvas, x, y, text, accent or palette.accent)


def full_width_rect(y: int, height: int) -> Rect:
    return Rect(PAGE_INSET_X, y, CONTENT_WIDTH, height)


def three_column_rects(y: int, height: int) -> tuple[Rect, Rect, Rect]:
    return (
        Rect(PAGE_INSET_X, y, THREE_COL_WIDTH, height),
        Rect(PAGE_INSET_X + THREE_COL_WIDTH + THREE_COL_GAP, y, THREE_COL_WIDTH, height),
        Rect(PAGE_INSET_X + (THREE_COL_WIDTH + THREE_COL_GAP) * 2, y, THREE_COL_WIDTH, height),
    )


def two_column_rects(y: int, height: int) -> tuple[Rect, Rect]:
    return (
        Rect(PAGE_INSET_X, y, TWO_COL_WIDTH, height),
        Rect(PAGE_INSET_X + TWO_COL_WIDTH + TWO_COL_GAP, y, TWO_COL_WIDTH, height),
    )


def draw_footer_note(
    canvas: PixelCanvas,
    text: str,
    palette: Palette,
    color: Color | None = None,
    y: int = 53,
) -> None:
    FONT_5X7.draw_boxed(canvas, PAGE_INSET_X, y, CONTENT_WIDTH, text, color or palette.text_dim, align="center")
