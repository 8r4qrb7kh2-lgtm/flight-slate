"""Custom bitmap font primitives for pixel-perfect UI work."""

from __future__ import annotations

from dataclasses import dataclass

from ui_lab.canvas import PixelCanvas
from ui_lab.palette import Color

GlyphRows = tuple[str, ...]


@dataclass(frozen=True)
class Glyph:
    width: int
    rows: GlyphRows

    @property
    def height(self) -> int:
        return len(self.rows)


class BitmapFont:
    def __init__(self, glyphs: dict[str, Glyph], height: int, spacing: int = 1) -> None:
        self.glyphs = glyphs
        self.height = height
        self.spacing = spacing

    def measure(self, text: str, scale: int = 1) -> tuple[int, int]:
        width = 0
        for index, char in enumerate(text):
            glyph = self.glyphs.get(char, self.glyphs["?"])
            width += glyph.width * scale
            if index != len(text) - 1:
                width += self.spacing * scale
        return width, self.height * scale

    def render(self, canvas: PixelCanvas, x: int, y: int, text: str, color: Color, scale: int = 1) -> None:
        cursor_x = x
        for index, char in enumerate(text):
            glyph = self.glyphs.get(char, self.glyphs["?"])
            self._render_glyph(canvas, cursor_x, y, glyph, color, scale)
            cursor_x += glyph.width * scale
            if index != len(text) - 1:
                cursor_x += self.spacing * scale

    def render_clipped(
        self,
        canvas: PixelCanvas,
        x: int,
        y: int,
        text: str,
        color: Color,
        clip_x: int,
        clip_width: int,
        scale: int = 1,
    ) -> None:
        cursor_x = x
        clip_right = clip_x + clip_width
        for index, char in enumerate(text):
            glyph = self.glyphs.get(char, self.glyphs["?"])
            self._render_glyph_clipped(canvas, cursor_x, y, glyph, color, clip_x, clip_right, scale)
            cursor_x += glyph.width * scale
            if index != len(text) - 1:
                cursor_x += self.spacing * scale

    def draw_boxed(
        self,
        canvas: PixelCanvas,
        x: int,
        y: int,
        width: int,
        text: str,
        color: Color,
        scale: int = 1,
        align: str = "left",
        clip: bool = False,
        height: int | None = None,
        valign: str = "top",
    ) -> str:
        rendered = text if clip else self.fit(text, width, scale=scale)
        text_width, _ = self.measure(rendered, scale=scale)
        text_height = self.height * scale
        if align == "center":
            draw_x = x + max(0, (width - text_width) // 2)
        elif align == "right":
            draw_x = x + max(0, width - text_width)
        else:
            draw_x = x
        if height is None or valign == "top":
            draw_y = y
        elif valign == "middle":
            draw_y = y + max(0, (height - text_height) // 2)
        elif valign == "bottom":
            draw_y = y + max(0, height - text_height)
        else:
            raise ValueError(f"Unsupported vertical alignment: {valign}")

        if clip:
            self.render_clipped(canvas, draw_x, draw_y, rendered, color, x, width, scale=scale)
        else:
            self.render(canvas, draw_x, draw_y, rendered, color, scale=scale)
        return rendered

    def fit(self, text: str, width: int, scale: int = 1) -> str:
        if self.measure(text, scale=scale)[0] <= width:
            return text
        ellipsis = "..."
        if self.measure(ellipsis, scale=scale)[0] > width:
            return ""
        candidate = text
        while candidate and self.measure(candidate + ellipsis, scale=scale)[0] > width:
            candidate = candidate[:-1]
        return candidate + ellipsis

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

    def _render_glyph_clipped(
        self,
        canvas: PixelCanvas,
        x: int,
        y: int,
        glyph: Glyph,
        color: Color,
        clip_left: int,
        clip_right: int,
        scale: int,
    ) -> None:
        for row_index, row in enumerate(glyph.rows):
            for column_index, value in enumerate(row):
                if value != "#":
                    continue
                for scale_y in range(scale):
                    for scale_x in range(scale):
                        pixel_x = x + column_index * scale + scale_x
                        if clip_left <= pixel_x < clip_right:
                            canvas.pixel(pixel_x, y + row_index * scale + scale_y, color)


def _glyph(*rows: str) -> Glyph:
    return Glyph(width=len(rows[0]), rows=tuple(rows))


FONT_5X7 = BitmapFont(
    glyphs={
        " ": _glyph("000", "000", "000", "000", "000", "000", "000"),
        ".": _glyph("0", "0", "0", "0", "0", "#", "#"),
        ",": _glyph("0", "0", "0", "0", "0", "#", "1"),
        ":": _glyph("0", "#", "#", "0", "#", "#", "0"),
        ";": _glyph("0", "#", "#", "0", "#", "1", "0"),
        "!": _glyph("1", "1", "1", "1", "1", "0", "1"),
        "-": _glyph("000", "000", "000", "###", "000", "000", "000"),
        "/": _glyph("00001", "00010", "00100", "00100", "01000", "10000", "00000"),
        "?": _glyph("01110", "10001", "00010", "00100", "00100", "00000", "00100"),
        "0": _glyph("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
        "1": _glyph("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
        "2": _glyph("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
        "3": _glyph("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
        "4": _glyph("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
        "5": _glyph("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
        "6": _glyph("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
        "7": _glyph("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
        "8": _glyph("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
        "9": _glyph("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
        "A": _glyph("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
        "B": _glyph("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
        "C": _glyph("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
        "D": _glyph("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
        "E": _glyph("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
        "F": _glyph("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
        "G": _glyph("01110", "10001", "10000", "10111", "10001", "10001", "01110"),
        "H": _glyph("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
        "I": _glyph("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
        "J": _glyph("00001", "00001", "00001", "00001", "10001", "10001", "01110"),
        "K": _glyph("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
        "L": _glyph("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
        "M": _glyph("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
        "N": _glyph("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
        "O": _glyph("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
        "P": _glyph("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
        "Q": _glyph("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
        "R": _glyph("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
        "S": _glyph("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
        "T": _glyph("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
        "U": _glyph("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
        "V": _glyph("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
        "W": _glyph("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
        "X": _glyph("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
        "Y": _glyph("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
        "Z": _glyph("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    },
    height=7,
    spacing=1,
)


def normalize_font_glyphs() -> None:
    """Convert `1`/`0` rows into `#`/`.` rows after declaration."""

    normalized: dict[str, Glyph] = {}
    for key, glyph in FONT_5X7.glyphs.items():
        rows = tuple(row.replace("1", "#").replace("0", ".") for row in glyph.rows)
        normalized[key] = Glyph(width=glyph.width, rows=rows)
    FONT_5X7.glyphs.update(normalized)


normalize_font_glyphs()
