import unittest

from ui_lab.app import FeatureLabApp


class FeatureLabSuiteTests(unittest.TestCase):
    def test_page_order_matches_required_component_list(self):
        app = FeatureLabApp()

        self.assertEqual([page.key for page in app.pages], ["text"])

    def test_every_page_analyzes_without_unexpected_colors(self):
        app = FeatureLabApp()

        for index, page in enumerate(app.pages):
            app.page_index = index
            frame_times = [0.0] if not page.animated else [0.0, 0.5]
            for elapsed_s in frame_times:
                canvas = app.render(elapsed_s)
                analysis = page.analyze(canvas)
                self.assertEqual(analysis["unexpected_colors"], [], msg=f"{page.key} @ {elapsed_s}")
                self.assertEqual(analysis.get("overlap_pairs", []), [], msg=f"overlap {page.key} @ {elapsed_s}")
                self.assertEqual(
                    analysis.get("out_of_bounds_regions", []),
                    [],
                    msg=f"out-of-bounds {page.key} @ {elapsed_s}",
                )

    def test_next_and_previous_page_wrap_correctly(self):
        app = FeatureLabApp()

        app.page_index = 0
        app.previous_page()
        self.assertEqual(app.current_page.key, "text")

        app.next_page()
        self.assertEqual(app.current_page.key, "text")


if __name__ == "__main__":
    unittest.main()
