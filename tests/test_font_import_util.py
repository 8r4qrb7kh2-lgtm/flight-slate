import importlib
import unittest

from fonts.import_util import import_bitmap_font


class FontImportUtilTests(unittest.TestCase):
    def test_import_maps_chars_to_frames(self) -> None:
        frames = [
            [
                [0, 1, 0],
                [1, 1, 1],
            ],
            [
                [1, 0, 1],
                [1, 1, 1],
            ],
        ]

        font = import_bitmap_font(frames, "AB", trim_empty_columns=False)

        self.assertEqual(font.height, 2)
        self.assertEqual(font.glyphs["A"].rows, (".#.", "###"))
        self.assertEqual(font.glyphs["B"].rows, ("#.#", "###"))

    def test_trim_empty_columns_removes_outer_padding(self) -> None:
        frames = [
            [
                [0, 1, 0, 0],
                [0, 1, 1, 0],
            ],
        ]

        font = import_bitmap_font(frames, "X", trim_empty_columns=True, min_width=1)

        self.assertEqual(font.glyphs["X"].width, 2)
        self.assertEqual(font.glyphs["X"].rows, ("#.", "##"))

    def test_3x5_font_module_loads_through_importlib(self) -> None:
        module = importlib.import_module("fonts.3x5")

        self.assertIn("A", module.FONT_3X5.glyphs)
        self.assertIn("?", module.FONT_3X5.glyphs)
        self.assertEqual(module.FONT_3X5.height, 5)


if __name__ == "__main__":
    unittest.main()
