import unittest

from flight_ui_core import (
    CoreUIDemo,
    FontRegistry,
    MapViewport,
    MockFlightProvider,
    PixelCanvas,
    Rect,
    Theme,
    build_logo_registry,
    fit_text,
    measure_text,
    run_core_ui_demo,
)
from standard_led_matrix_interface import RGBMatrixOptions


class FakeMatrix:
    def __init__(self, width=128, height=64):
        self.width = width
        self.height = height
        self.closed = False
        self.process_calls = 0
        self.pixels = {}

    def SetPixel(self, x, y, r, g, b):
        self.pixels[(x, y)] = (r, g, b)

    def Clear(self):
        self.pixels.clear()

    def process(self):
        self.process_calls += 1
        return self.process_calls < 2

    def close(self):
        self.closed = True


class CoreUIDemoTests(unittest.TestCase):
    @staticmethod
    def count_non_black_pixels(canvas):
        pixels = canvas.image.load()
        count = 0
        for y in range(canvas.height):
            for x in range(canvas.width):
                if pixels[x, y] != (0, 0, 0):
                    count += 1
        return count

    @staticmethod
    def has_non_black_pixels(canvas):
        pixels = canvas.image.load()
        for y in range(canvas.height):
            for x in range(canvas.width):
                if pixels[x, y] != (0, 0, 0):
                    return True
        return False

    def test_fit_text_ellipsis_respects_width(self):
        font = FontRegistry().get("mono", 7)
        fitted = fit_text("MERIDIAN REGIONAL EXPRESS", font, 28)

        self.assertLessEqual(measure_text(font, fitted)[0], 28)
        self.assertTrue(fitted.endswith("...") or fitted == "")

    def test_map_viewport_projects_center_to_middle(self):
        viewport = MapViewport(center_lat=40.0, center_lon=-75.0, zoom=1.5, width=120, height=46)

        self.assertEqual(viewport.project(40.0, -75.0), (60, 23))

    def test_mock_flight_provider_returns_animated_flights(self):
        provider = MockFlightProvider()
        early = provider.snapshot(0.0)
        later = provider.snapshot(5.0)

        self.assertGreaterEqual(len(early), 4)
        self.assertNotEqual(early[0].aircraft_lat, later[0].aircraft_lat)
        self.assertNotEqual(early[0].speed_kt, later[0].speed_kt)

    def test_core_ui_demo_renders_non_empty_frame(self):
        demo = CoreUIDemo()
        canvas = demo.render_to_canvas(0.0)

        lit_pixels = self.count_non_black_pixels(canvas)

        self.assertGreater(lit_pixels, 500)

    def test_logo_fallback_renders_when_asset_missing(self):
        canvas = PixelCanvas(32, 16)
        theme = Theme()
        demo = CoreUIDemo(width=32, height=16)
        demo.canvas = canvas
        demo.logos = build_logo_registry()

        from flight_ui_core import draw_logo_or_fallback

        draw_logo_or_fallback(
            canvas,
            Rect(0, 0, 12, 12),
            demo.logos,
            demo.fonts,
            theme,
            "missing",
            "Ghost Air",
            theme.rose,
        )

        self.assertTrue(self.has_non_black_pixels(canvas))

    def test_run_core_ui_demo_works_with_fake_matrix(self):
        matrix = FakeMatrix()

        run_core_ui_demo(
            matrix=matrix,
            options=RGBMatrixOptions(limit_refresh_rate_hz=1000),
            auto_close_ms=None,
        )

        self.assertEqual(matrix.process_calls, 2)
        self.assertIn((0, 0), matrix.pixels)


if __name__ == "__main__":
    unittest.main()
