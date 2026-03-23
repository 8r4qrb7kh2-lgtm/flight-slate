"""4x6 bitmap font imported from generated raw frames."""

from __future__ import annotations

from ui.fonts.import_util import ALNUM_PUNCT_94, ImportOptions, import_bitmap_font_from_module
from ui.fonts.generated import font_4x6 as raw_font_4x6

FONT_4X6 = import_bitmap_font_from_module(
	raw_font_4x6,
	ALNUM_PUNCT_94,
	options=ImportOptions(trim_empty_columns=True, spacing=1, fallback_char="?"),
)

