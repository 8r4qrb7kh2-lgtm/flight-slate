import json
import tempfile
import unittest
from pathlib import Path

from ui_lab.app import FeatureLabApp
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

        page.render(canvas, PageFrame(index=0, total=13, elapsed_s=0.0))
        analysis = page.analyze(canvas)

        self.assertEqual(analysis["unexpected_colors"], [])
        self.assertGreater(analysis["small_width"], 0)
        self.assertGreater(analysis["medium_width"], analysis["small_width"])
        self.assertGreaterEqual(analysis["large_width"], analysis["small_width"])

    def test_glyph_sheet_stays_inside_lower_panel(self):
        page = TextPage()
        palette = Palette()
        canvas = PixelCanvas(128, 64, palette.background)

        page.render(canvas, PageFrame(index=0, total=13, elapsed_s=0.0))
        pixels = canvas.image.load()

        row_between_sections = 39
        self.assertTrue(all(pixels[x, row_between_sections] != palette.accent_alt for x in range(128)))

    def test_export_current_page_writes_artifacts(self):
        app = FeatureLabApp()

        with tempfile.TemporaryDirectory() as tmp_dir:
            paths, analysis = app.export_current_page(Path(tmp_dir), stem="proof")

            self.assertTrue(paths["raw"].exists())
            self.assertTrue(paths["upscaled"].exists())
            self.assertTrue(paths["ascii"].exists())
            self.assertTrue(paths["report"].exists())
            self.assertEqual(json.loads(paths["report"].read_text())["small_width"], analysis["small_width"])


if __name__ == "__main__":
    unittest.main()
