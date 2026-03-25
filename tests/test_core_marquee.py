import unittest

from ui.core.bitmap_font import BitmapFont, Glyph
from ui.core.canvas import PixelCanvas, Rect
from ui.core.widgets import Marquee, Text, Widget

RED = (255, 0, 0)
BLACK = (0, 0, 0)


class Solid(Widget):
    def __init__(self, color: tuple[int, int, int]) -> None:
        self.color = color

    def draw(self, canvas: PixelCanvas, rect: Rect) -> None:
        canvas.rect(rect, fill=self.color)


def _count_color(canvas: PixelCanvas, color: tuple[int, int, int]) -> int:
    pixels = canvas.image.load()
    count = 0
    for y in range(canvas.height):
        for x in range(canvas.width):
            if pixels[x, y] == color:
                count += 1
    return count


class CoreMarqueeTests(unittest.TestCase):
    def test_marquee_repeats_small_content_across_width(self) -> None:
        canvas = PixelCanvas(7, 1, BLACK)
        marquee = Marquee(
            child=Solid(RED),
            axis="x",
            offset=0,
            content_extent=2,
            gap=1,
        )

        marquee.draw(canvas, Rect(0, 0, 7, 1))

        pixels = canvas.image.load()
        self.assertEqual(_count_color(canvas, RED), 5)
        self.assertEqual(pixels[0, 0], RED)
        self.assertEqual(pixels[1, 0], RED)
        self.assertEqual(pixels[2, 0], BLACK)
        self.assertEqual(pixels[3, 0], RED)
        self.assertEqual(pixels[4, 0], RED)
        self.assertEqual(pixels[5, 0], BLACK)
        self.assertEqual(pixels[6, 0], RED)

    def test_marquee_offset_scrolls_in_x(self) -> None:
        canvas = PixelCanvas(7, 1, BLACK)
        marquee = Marquee(
            child=Solid(RED),
            axis="x",
            offset=1,
            content_extent=2,
            gap=1,
        )

        marquee.draw(canvas, Rect(0, 0, 7, 1))

        pixels = canvas.image.load()
        self.assertEqual(_count_color(canvas, RED), 5)
        self.assertEqual(pixels[0, 0], RED)
        self.assertEqual(pixels[1, 0], BLACK)
        self.assertEqual(pixels[2, 0], RED)
        self.assertEqual(pixels[3, 0], RED)
        self.assertEqual(pixels[4, 0], BLACK)
        self.assertEqual(pixels[5, 0], RED)
        self.assertEqual(pixels[6, 0], RED)

    def test_text_overflow_overflow_scrolls_and_repeats(self) -> None:
        glyphs = {
            "A": Glyph(width=1, rows=("#",)),
            "?": Glyph(width=1, rows=("#",)),
        }
        font = BitmapFont(glyphs=glyphs, height=1, spacing=0)
        text = Text(
            text="A",
            font=font,
            overflow="overflow",
            overflow_axis="x",
            overflow_offset=0,
            overflow_gap=1,
            color=RED,
        )

        canvas = PixelCanvas(5, 1, BLACK)
        text.draw(canvas, Rect(0, 0, 5, 1))

        pixels = canvas.image.load()
        self.assertEqual(_count_color(canvas, RED), 3)
        self.assertEqual(pixels[0, 0], RED)
        self.assertEqual(pixels[1, 0], BLACK)
        self.assertEqual(pixels[2, 0], RED)
        self.assertEqual(pixels[3, 0], BLACK)
        self.assertEqual(pixels[4, 0], RED)

    def test_marquee_clips_nested_text_to_viewport(self) -> None:
        glyphs = {
            "A": Glyph(width=1, rows=("#",)),
            "?": Glyph(width=1, rows=("#",)),
        }
        font = BitmapFont(glyphs=glyphs, height=1, spacing=0)
        text = Text(
            text="AAAAA",
            font=font,
            overflow="clip",
            color=RED,
        )
        marquee = Marquee(
            child=text,
            axis="x",
            offset=0,
            content_extent=5,
            gap=1,
        )

        canvas = PixelCanvas(8, 1, BLACK)
        marquee.draw(canvas, Rect(2, 0, 3, 1))

        pixels = canvas.image.load()
        # Only viewport x=2..4 may be touched.
        self.assertEqual(pixels[0, 0], BLACK)
        self.assertEqual(pixels[1, 0], BLACK)
        self.assertEqual(pixels[2, 0], RED)
        self.assertEqual(pixels[3, 0], RED)
        self.assertEqual(pixels[4, 0], RED)
        self.assertEqual(pixels[5, 0], BLACK)
        self.assertEqual(pixels[6, 0], BLACK)
        self.assertEqual(pixels[7, 0], BLACK)

if __name__ == "__main__":
    unittest.main()
