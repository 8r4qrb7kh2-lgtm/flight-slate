import unittest

from ui_lab.assets import icon_registry, logo_registry
from ui_lab.canvas import PixelCanvas, Rect
from ui_lab.palette import Palette
from ui_lab.widgets import draw_list_item, draw_stat_block, draw_state_card


class WidgetBoundsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.palette = Palette()

    def assert_pixels_only_inside(self, canvas: PixelCanvas, rect: Rect) -> None:
        pixels = canvas.image.load()
        for y in range(canvas.height):
            for x in range(canvas.width):
                if pixels[x, y] == self.palette.background:
                    continue
                self.assertTrue(
                    rect.x <= x < rect.right and rect.y <= y < rect.bottom,
                    msg=f"Pixel at {(x, y)} escaped {rect}",
                )

    def test_list_item_stays_within_bounds(self) -> None:
        canvas = PixelCanvas(128, 64, self.palette.background)
        rect = Rect(6, 20, 116, 18)

        draw_list_item(
            canvas,
            rect,
            "JFK -> ORD",
            "SA128",
            "452",
            self.palette,
            self.palette.accent,
            logo_registry()["slate"],
            selected=True,
        )

        self.assert_pixels_only_inside(canvas, rect)

    def test_state_card_stays_within_bounds(self) -> None:
        canvas = PixelCanvas(128, 64, self.palette.background)
        rect = Rect(6, 20, 116, 14)

        draw_state_card(
            canvas,
            rect,
            "LOADING",
            "SCANNING FEED",
            self.palette,
            self.palette.accent,
            icon_registry()["live"],
        )

        self.assert_pixels_only_inside(canvas, rect)

    def test_stat_block_value_fits_block_width(self) -> None:
        canvas = PixelCanvas(128, 64, self.palette.background)
        rect = Rect(8, 20, 36, 36)

        analysis = draw_stat_block(
            canvas,
            rect,
            "SPD",
            "452",
            self.palette,
            self.palette.accent,
            icon_registry()["plane"],
        )

        self.assert_pixels_only_inside(canvas, rect)
        self.assertLessEqual(analysis["value_width"], rect.width - 2)


if __name__ == "__main__":
    unittest.main()
