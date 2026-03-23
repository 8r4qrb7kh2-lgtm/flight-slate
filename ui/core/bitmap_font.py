"""Bitmap font primitives used by standalone core UI widgets."""

from __future__ import annotations

from dataclasses import dataclass

from ui.core.canvas import PixelCanvas

GlyphRows = tuple[str, ...]
Color = tuple[int, int, int]


@dataclass(frozen=True)
class Glyph:
    width: int
    rows: GlyphRows

    @property
    def height(self) -> int:
        return len(self.rows)


class BitmapFont:
    def __init__(
        self,
        glyphs: dict[str, Glyph],
        height: int,
        spacing: int = 1,
        character_order: str | tuple[str, ...] | None = None,
    ) -> None:
        self.glyphs = glyphs
        self.height = height
        self.spacing = spacing
        # Persist the source character order used during import so mapping can be inspected/debugged.
        if character_order is None:
            self.character_order = tuple(glyphs.keys())
        else:
            self.character_order = tuple(character_order)
        # Provide a sensible blank-width for fonts that do not explicitly include a space glyph.
        self.space_width = max(1, height // 2)
        self._fallback_glyph = self.glyphs.get("?") or next(iter(self.glyphs.values()))
        self._blank_rows = tuple("." * self.space_width for _ in range(self.height))

    def measure(self, text: str, scale: int = 1) -> tuple[int, int]:
        width = 0
        for index, char in enumerate(text):
            glyph = self._resolve_glyph(char)
            width += glyph.width * scale
            if index != len(text) - 1:
                width += self.spacing * scale
        return width, self.height * scale

    def render(self, canvas: PixelCanvas, x: int, y: int, text: str, color: Color, scale: int = 1) -> None:
        cursor_x = x
        for index, char in enumerate(text):
            glyph = self._resolve_glyph(char)
            # Whitespace glyphs are blank by design and only advance width.
            if not char.isspace() and char not in {"\n", "\r"}:
                self._render_glyph(canvas, cursor_x, y, glyph, color, scale)
            cursor_x += glyph.width * scale
            if index != len(text) - 1:
                cursor_x += self.spacing * scale

    def clip(self, text: str, width: int, scale: int = 1) -> str:
        if self.measure(text, scale=scale)[0] <= width:
            return text
        candidate = text
        while candidate and self.measure(candidate, scale=scale)[0] > width:
            candidate = candidate[:-1]
        return candidate

    def _render_glyph(self, canvas: PixelCanvas, x: int, y: int, glyph: Glyph, color: Color, scale: int) -> None:
        for row_index, row in enumerate(glyph.rows):
            for column_index, value in enumerate(row):
                if value != "#":
                    continue
                for scale_y in range(scale):
                    for scale_x in range(scale):
                        canvas.pixel(
                            x + column_index * scale + scale_x,
                            y + row_index * scale + scale_y,
                            color,
                        )

    def _resolve_glyph(self, char: str) -> Glyph:
        glyph = self.glyphs.get(char)
        if glyph is not None:
            return glyph

        if char == "\t":
            return Glyph(width=self.space_width * 4, rows=self._blank_rows)
        if char.isspace() and char not in {"\n", "\r"}:
            return Glyph(width=self.space_width, rows=self._blank_rows)

        return self._fallback_glyph
