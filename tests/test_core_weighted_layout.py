import unittest

from ui.core.canvas import PixelCanvas, Rect
from ui.core.widgets import Column, Panel, Row, Widget

RED = (255, 0, 0)
BLUE = (0, 0, 255)
GREEN = (0, 255, 0)
BLACK = (0, 0, 0)


class Solid(Widget):
    def __init__(self, color: tuple[int, int, int]) -> None:
        self.color = color

    def draw(self, canvas: PixelCanvas, rect: Rect) -> None:
        canvas.rect(rect, fill=self.color)


def count_color(canvas: PixelCanvas, color: tuple[int, int, int]) -> int:
    pixels = canvas.image.load()
    count = 0
    for y in range(canvas.height):
        for x in range(canvas.width):
            if pixels[x, y] == color:
                count += 1
    return count


class CoreWeightedLayoutTests(unittest.TestCase):
    def test_panel_border_and_padding_both_inset_child(self) -> None:
        canvas = PixelCanvas(8, 8, BLACK)
        panel = Panel(
            child=Solid(RED),
            padding=1,
            border=BLUE,
            bg=BLACK,
        )

        panel.draw(canvas, Rect(0, 0, 8, 8))

        pixels = canvas.image.load()
        # Border occupies edge pixels; child starts after border(1) + padding(1).
        self.assertEqual(pixels[0, 0], BLUE)
        self.assertEqual(pixels[1, 1], BLACK)
        self.assertEqual(pixels[2, 2], RED)
        self.assertEqual(pixels[5, 5], RED)
        self.assertEqual(pixels[6, 6], BLACK)

    def test_row_even_split_for_equal_sizes(self) -> None:
        canvas = PixelCanvas(10, 1, BLACK)
        row = Row(children=[Solid(RED), Solid(BLUE)], sizes=[1, 1])

        row.draw(canvas, Rect(0, 0, 10, 1))

        self.assertEqual(count_color(canvas, RED), 5)
        self.assertEqual(count_color(canvas, BLUE), 5)

    def test_row_weighted_split_10_90(self) -> None:
        canvas = PixelCanvas(20, 1, BLACK)
        row = Row(children=[Solid(RED), Solid(BLUE)], sizes=[10, 90])

        row.draw(canvas, Rect(0, 0, 20, 1))

        self.assertEqual(count_color(canvas, RED), 2)
        self.assertEqual(count_color(canvas, BLUE), 18)

    def test_row_remainder_distribution_is_deterministic(self) -> None:
        canvas = PixelCanvas(11, 1, BLACK)
        row = Row(children=[Solid(RED), Solid(BLUE)], sizes=[1, 1])

        row.draw(canvas, Rect(0, 0, 11, 1))

        self.assertEqual(count_color(canvas, RED), 5)
        self.assertEqual(count_color(canvas, BLUE), 6)

    def test_weighted_layout_rejects_too_many_children(self) -> None:
        canvas = PixelCanvas(10, 1, BLACK)
        row = Row(children=[Solid(RED), Solid(BLUE)], sizes=[1])

        with self.assertRaises(ValueError):
            row.draw(canvas, Rect(0, 0, 10, 1))

    def test_column_renders_missing_slots_as_blank(self) -> None:
        canvas = PixelCanvas(2, 10, BLACK)
        column = Column(children=[Solid(RED)], sizes=[1, 1])

        column.draw(canvas, Rect(0, 0, 2, 10))

        pixels = canvas.image.load()
        top_half_red = sum(1 for y in range(5) for x in range(2) if pixels[x, y] == RED)
        bottom_half_black = sum(1 for y in range(5, 10) for x in range(2) if pixels[x, y] == BLACK)

        self.assertEqual(top_half_red, 10)
        self.assertEqual(bottom_half_black, 10)

    def test_nested_weighted_row_inside_weighted_column(self) -> None:
        canvas = PixelCanvas(8, 8, BLACK)
        nested = Column(
            sizes=[1, 1],
            children=[
                Row(children=[Solid(RED), Solid(BLUE)], sizes=[1, 3]),
                Solid(GREEN),
            ],
        )

        nested.draw(canvas, Rect(0, 0, 8, 8))

        self.assertEqual(count_color(canvas, RED), 8)
        self.assertEqual(count_color(canvas, BLUE), 24)
        self.assertEqual(count_color(canvas, GREEN), 32)


if __name__ == "__main__":
    unittest.main()
