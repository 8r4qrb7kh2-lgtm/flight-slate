import unittest

from ui_lab.bitmap_font import FONT_5X7
from ui_lab.canvas import PixelCanvas
from ui_lab.pages.base import PageFrame
from ui_lab.pages.small_text import TextPage
from ui_lab.palette import Palette


class SmallTextFeatureLabTests(unittest.TestCase):
    def test_bitmap_font_fit_is_deterministic(self):
        rendered = FONT_5X7.fit("MERIDIAN REGIONAL", 34)

        self.assertEqual(rendered, "MERI...")
        self.assertLessEqual(FONT_5X7.measure(rendered)[0], 34)

    def test_small_text_page_has_no_unexpected_colors(self):
        page = TextPage()
        palette = Palette()
        canvas = PixelCanvas(128, 64, palette.background)

        page.render(canvas, PageFrame(index=0, total=1, elapsed_s=0.0))
        analysis = page.analyze(canvas)

        self.assertEqual(analysis["unexpected_colors"], [])
        self.assertEqual(len(analysis["glyph_lines"]), 7)
        self.assertIn("A B C D E F G H", analysis["glyph_lines"])
        self.assertIn(". , : ; ! ? - /", analysis["glyph_lines"])
        self.assertEqual(analysis["overlap_pairs"], [])
        self.assertEqual(analysis["out_of_bounds_regions"], [])

    def test_glyph_sheet_stays_inside_demo_panel(self):
        page = TextPage()
        palette = Palette()
        canvas = PixelCanvas(128, 64, palette.background)

        page.render(canvas, PageFrame(index=0, total=1, elapsed_s=0.0))
        pixels = canvas.image.load()

        text_colors = {palette.text, palette.text_dim, palette.accent}
        self.assertTrue(all(pixels[x, 63] not in text_colors for x in range(128)))

if __name__ == "__main__":
    unittest.main()
