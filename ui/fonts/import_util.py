"""Utilities for importing generated bitmap font frames into `BitmapFont`."""

from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType
from typing import Sequence

from ui.core.bitmap_font import BitmapFont, Glyph

ASCII_94 = (
    " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~"
)

ALNUM_PUNCT_94 = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
)


@dataclass(frozen=True)
class ImportOptions:
    """Simple import options for converting frame arrays into glyphs."""

    trim_empty_columns: bool = False
    min_width: int = 1
    spacing: int = 1
    fallback_char: str = "?"


def import_bitmap_font(
    frames: Sequence[Sequence[Sequence[int]]],
    chars: str,
    *,
    trim_empty_columns: bool = False,
    min_width: int = 1,
    spacing: int = 1,
    fallback_char: str = "?",
) -> BitmapFont:
    """Build a `BitmapFont` from a frame list and character order string."""

    if len(chars) != len(frames):
        raise ValueError(
            f"Character count ({len(chars)}) does not match frame count ({len(frames)})."
        )
    if min_width < 1:
        raise ValueError("min_width must be >= 1")
    if spacing < 0:
        raise ValueError("spacing must be >= 0")

    normalized_frames = [_normalize_frame(frame) for frame in frames]
    if not normalized_frames:
        raise ValueError("At least one frame is required.")

    height = len(normalized_frames[0])
    for frame in normalized_frames:
        if len(frame) != height:
            raise ValueError("All frames must have the same height.")

    glyphs: dict[str, Glyph] = {}
    for char, frame in zip(chars, normalized_frames):
        rows = frame
        if trim_empty_columns:
            rows = _trim_horizontal_padding(rows)

        if rows and len(rows[0]) < min_width:
            rows = _pad_to_width(rows, min_width)

        glyphs[char] = _rows_to_glyph(rows)

    if fallback_char not in glyphs:
        glyphs[fallback_char] = next(iter(glyphs.values()))

    return BitmapFont(
        glyphs=glyphs,
        height=height,
        spacing=spacing,
        character_order=chars,
    )


def import_bitmap_font_from_module(
    raw_module: ModuleType,
    chars: str,
    *,
    options: ImportOptions | None = None,
) -> BitmapFont:
    """Build a `BitmapFont` from a generated raw font module."""

    if not hasattr(raw_module, "frames"):
        raise ValueError("raw_module must expose a `frames` attribute")

    resolved = options or ImportOptions()
    return import_bitmap_font(
        frames=raw_module.frames,
        chars=chars,
        trim_empty_columns=resolved.trim_empty_columns,
        min_width=resolved.min_width,
        spacing=resolved.spacing,
        fallback_char=resolved.fallback_char,
    )


def _normalize_frame(frame: Sequence[Sequence[int]]) -> tuple[str, ...]:
    if not frame:
        raise ValueError("Frames cannot be empty.")

    width = len(frame[0])
    if width == 0:
        raise ValueError("Frames cannot contain empty rows.")

    rows: list[str] = []
    for row in frame:
        if len(row) != width:
            raise ValueError("All rows in a frame must have the same width.")
        rows.append("".join("#" if value else "." for value in row))
    return tuple(rows)


def _trim_horizontal_padding(rows: tuple[str, ...]) -> tuple[str, ...]:
    width = len(rows[0])
    left = 0
    right = width - 1

    while left <= right and all(row[left] == "." for row in rows):
        left += 1
    while right >= left and all(row[right] == "." for row in rows):
        right -= 1

    if left > right:
        return tuple("" for _ in rows)
    return tuple(row[left : right + 1] for row in rows)


def _pad_to_width(rows: tuple[str, ...], width: int) -> tuple[str, ...]:
    return tuple(row.ljust(width, ".") for row in rows)


def _rows_to_glyph(rows: tuple[str, ...]) -> Glyph:
    return Glyph(width=len(rows[0]), rows=rows)
