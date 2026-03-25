
from __future__ import annotations

from ui.fonts.c_font_import import load_project_c_font
from ui.fonts.import_util import ALNUM_PUNCT_94
from ui.fonts.import_util import import_bitmap_font


def _load_font(filename: str):
    width, height, frames = load_project_c_font(filename)
    del width, height
    return import_bitmap_font(
        frames,
        ALNUM_PUNCT_94,
        trim_empty_columns=True,
        spacing=1,
        fallback_char="?",
    )


FONT_3X5 = _load_font("3x5 Font.c")
FONT_4X6 = _load_font("4x6 Font.c")
FONT_5X7 = _load_font("5x7 Font.c")
