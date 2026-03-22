import json
import tempfile
import unittest
from pathlib import Path

from ui_lab.app import FeatureLabApp
from ui_lab.bitmap_font import FONT_5X7
from ui_lab.palette import Palette


class FeatureLabSuiteTests(unittest.TestCase):
    def test_page_order_matches_required_component_list(self):
        app = FeatureLabApp()

        self.assertEqual(
            [page.key for page in app.pages],
            [
                "text",
                "overflow",
                "icons",
                "images_logos",
                "container",
                "shapes",
                "badges",
                "progress",
                "stats",
                "lists",
                "states",
                "map",
                "animation",
            ],
        )

    def test_every_page_analyzes_without_unexpected_colors(self):
        app = FeatureLabApp()

        for index, page in enumerate(app.pages):
            app.page_index = index
            frame_times = [0.0] if not page.animated else [0.0, 0.5]
            for elapsed_s in frame_times:
                canvas = app.render(elapsed_s)
                analysis = page.analyze(canvas)
                self.assertEqual(analysis["unexpected_colors"], [], msg=f"{page.key} @ {elapsed_s}")

    def test_export_all_pages_writes_final_report_and_animation_frames(self):
        app = FeatureLabApp()

        with tempfile.TemporaryDirectory() as tmp_dir:
            report = app.export_all_pages(Path(tmp_dir))

            self.assertEqual(len(report), 13)
            self.assertEqual(len(report["animation"]), 4)
            self.assertEqual(len(report["overflow"]), 4)
            self.assertTrue(Path(report["text"][0]["paths"]["raw"]).exists())

    def test_animation_frames_change_over_time(self):
        app = FeatureLabApp()
        animation_index = [page.key for page in app.pages].index("animation")
        app.page_index = animation_index

        canvas_a = app.render(0.0)
        bytes_a = canvas_a.image.tobytes()
        canvas_b = app.render(0.75)
        bytes_b = canvas_b.image.tobytes()

        self.assertNotEqual(bytes_a, bytes_b)

    def test_overflow_marquee_is_clipped_to_its_box(self):
        app = FeatureLabApp()
        overflow_index = [page.key for page in app.pages].index("overflow")
        app.page_index = overflow_index
        canvas = app.render(0.5)
        pixels = canvas.image.load()
        palette = Palette()

        for y in range(48, 55):
            for x in list(range(0, 8)) + list(range(120, 128)):
                self.assertNotEqual(pixels[x, y], palette.success)

    def test_page_counter_fits_header_box(self):
        self.assertEqual(FONT_5X7.fit("13/13", 32), "13/13")

    def test_bottom_safe_rows_do_not_carry_component_content(self):
        app = FeatureLabApp()
        palette = Palette()
        allowed_bottom_colors = {palette.background, palette.panel, palette.panel_edge}

        for index, page in enumerate(app.pages):
            app.page_index = index
            frame_times = [0.0] if not page.animated else [0.0, 0.5]
            for elapsed_s in frame_times:
                canvas = app.render(elapsed_s)
                pixels = canvas.image.load()
                for y in (61,):
                    for x in range(1, 127):
                        self.assertIn(
                            pixels[x, y],
                            allowed_bottom_colors,
                            msg=f"{page.key} @ {elapsed_s} leaked content into bottom safe rows",
                        )


if __name__ == "__main__":
    unittest.main()
