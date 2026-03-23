import unittest

from ui_lab.app import FeatureLabApp
from ui_lab.canvas import PixelCanvas
from ui_lab.pages.base import PageFrame
from ui_lab.pages.small_text import TextPage
from ui_lab.palette import Palette


class TextDemoTests(unittest.TestCase):
    def test_text_page_layout_is_valid(self) -> None:
        palette = Palette()
        canvas = PixelCanvas(128, 64, palette.background)
        page = TextPage()

        page.render(canvas, PageFrame(index=0, total=1, elapsed_s=0.0))
        analysis = page.analyze(canvas)

        self.assertEqual(analysis["unexpected_colors"], [])
        self.assertEqual(analysis["overlap_pairs"], [])
        self.assertEqual(analysis["out_of_bounds_regions"], [])
        self.assertEqual(
            analysis["glyph_lines"],
            [
                "A B C D E F G H",
                "I J K L M N O P",
                "Q R S T U V W X",
                "Y Z",
                "0 1 2 3 4 5 6 7",
                "8 9",
                ". , : ; ! ? - /",
            ],
        )

    def test_core_app_has_single_page(self) -> None:
        app = FeatureLabApp()
        self.assertEqual([page.key for page in app.pages], ["text"])


if __name__ == "__main__":
    unittest.main()
