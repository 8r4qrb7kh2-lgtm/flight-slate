
from __future__ import annotations

from ui.fonts.import_util import ALNUM_PUNCT_94, ImportOptions, import_bitmap_font_from_module
from ui.fonts.generated import font_3x5 as raw_font_3x5
from ui.fonts.generated import font_4x6 as raw_font_4x6
from ui.fonts.generated import font_5x7 as raw_font_5x7


FONT_3X5 = import_bitmap_font_from_module(
	raw_font_3x5,
	ALNUM_PUNCT_94,
	options=ImportOptions(trim_empty_columns=True, spacing=1, fallback_char="?"),
)

FONT_4X6 = import_bitmap_font_from_module(
	raw_font_4x6,
	ALNUM_PUNCT_94,
	options=ImportOptions(trim_empty_columns=True, spacing=1, fallback_char="?"),
)

FONT_5X7 = import_bitmap_font_from_module(
	raw_font_5x7,
	ALNUM_PUNCT_94,
	options=ImportOptions(trim_empty_columns=True, spacing=1, fallback_char="?"),
)
