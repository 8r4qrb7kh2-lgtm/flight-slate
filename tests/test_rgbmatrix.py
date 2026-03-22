import io
import unittest
from unittest import mock

import demo_bouncing_ball
import mock_led_matrix
import rgbmatrix
import standard_led_matrix_interface


class FakeRoot:
    def __init__(self):
        self.after_calls = []
        self.protocol_calls = {}
        self.bind_calls = {}
        self.config = {}
        self.title_value = None
        self.resizable_args = None
        self.destroyed = False
        self.update_called = False
        self.update_idle_called = False

    def title(self, value):
        self.title_value = value

    def configure(self, **kwargs):
        self.config.update(kwargs)

    def resizable(self, width, height):
        self.resizable_args = (width, height)

    def protocol(self, name, callback):
        self.protocol_calls[name] = callback

    def bind(self, event, callback):
        self.bind_calls[event] = callback

    def after(self, delay, callback):
        self.after_calls.append((delay, callback))

    def update_idletasks(self):
        self.update_idle_called = True

    def update(self):
        self.update_called = True

    def destroy(self):
        self.destroyed = True


class FakeCanvas:
    def __init__(self, root, width, height, bg, highlightthickness):
        self.root = root
        self.width = width
        self.height = height
        self.bg = bg
        self.highlightthickness = highlightthickness
        self.packed = False
        self.items = []
        self.itemconfig_calls = []

    def pack(self):
        self.packed = True

    def create_oval(self, x0, y0, x1, y1, fill, outline, width=1):
        item_id = len(self.items)
        self.items.append(
            {
                "coords": (x0, y0, x1, y1),
                "fill": fill,
                "outline": outline,
                "width": width,
            }
        )
        return item_id

    def itemconfig(self, item_id, **kwargs):
        self.itemconfig_calls.append((item_id, kwargs))
        self.items[item_id].update(kwargs)


class FakeDemoMatrix:
    def __init__(self, options):
        self.options = options
        self.width = 128
        self.height = 64
        self.closed = False
        self.clear_called = False
        self.pixel_calls = []
        self.process_calls = 0

    def SetPixel(self, x, y, r, g, b):
        self.pixel_calls.append((x, y, r, g, b))

    def Clear(self):
        self.clear_called = True

    def process(self):
        self.process_calls += 1
        return self.process_calls < 2

    def close(self):
        self.closed = True


class MockLEDMatrixTests(unittest.TestCase):
    def build_matrix(self, options=None, platform="linux"):
        root = FakeRoot()
        with mock.patch.object(mock_led_matrix.tk, "Tk", return_value=root), mock.patch.object(
            mock_led_matrix.tk, "Canvas", FakeCanvas
        ), mock.patch.object(mock_led_matrix.sys, "platform", platform):
            matrix = mock_led_matrix.MockRGBMatrix(options)
        return matrix, root

    def test_default_options_match_single_panel(self):
        options = standard_led_matrix_interface.RGBMatrixOptions()
        self.assertEqual(options.width, 128)
        self.assertEqual(options.height, 64)

    def test_constructor_builds_full_panel_and_schedules_render(self):
        matrix, root = self.build_matrix()

        self.assertEqual(matrix.width, 128)
        self.assertEqual(matrix.height, 64)
        self.assertEqual(len(matrix._glow_ids), 128 * 64)
        self.assertEqual(len(matrix._pixel_ids), 128 * 64)
        self.assertTrue(matrix.canvas.packed)
        self.assertEqual(matrix.canvas.width, 1554)
        self.assertEqual(matrix.canvas.height, 786)
        first_glow = matrix.canvas.items[matrix._glow_ids[0]]
        first_led = matrix.canvas.items[matrix._pixel_ids[0]]
        last_led = matrix.canvas.items[matrix._pixel_ids[-1]]
        self.assertEqual(first_glow["coords"], (9.5, 9.5, 20.5, 20.5))
        self.assertEqual(first_led["coords"], (11.5, 11.5, 18.5, 18.5))
        self.assertEqual(first_led["outline"], mock_led_matrix.MockRGBMatrix.OUTLINE_COLOR)
        self.assertEqual(first_led["width"], 1)
        self.assertEqual(last_led["coords"], (1535.5, 767.5, 1542.5, 774.5))
        self.assertEqual(root.after_calls[0][0], 0)

    def test_setpixel_clamps_tracks_dirty_and_ignores_out_of_bounds(self):
        matrix, _root = self.build_matrix()

        matrix.SetPixel(10, 20, -5, 300, 12.8)
        matrix.SetPixel(-1, 0, 1, 2, 3)
        matrix.SetPixel(128, 63, 1, 2, 3)

        index = 20 * matrix.width + 10
        base = index * 3
        self.assertEqual(list(matrix._framebuffer[base : base + 3]), [0, 255, 12])
        self.assertEqual(matrix._dirty_pixels, {index})
        self.assertEqual(matrix._lit_pixels, {index})

    def test_clear_zeros_only_lit_pixels(self):
        matrix, _root = self.build_matrix()

        matrix.SetPixel(1, 2, 10, 20, 30)
        matrix.SetPixel(3, 4, 40, 50, 60)
        indexes = {2 * matrix.width + 1, 4 * matrix.width + 3}

        matrix.Clear()

        self.assertEqual(matrix._lit_pixels, set())
        self.assertTrue(indexes.issubset(matrix._dirty_pixels))
        for index in indexes:
            base = index * 3
            self.assertEqual(list(matrix._framebuffer[base : base + 3]), [0, 0, 0])

    def test_render_updates_dirty_pixels_with_brightness_scaling(self):
        options = standard_led_matrix_interface.RGBMatrixOptions(brightness=50, limit_refresh_rate_hz=30)
        matrix, root = self.build_matrix(options)
        matrix.SetPixel(0, 0, 255, 128, 64)

        matrix._render()

        self.assertEqual(matrix._dirty_pixels, set())
        self.assertEqual(
            matrix.canvas.itemconfig_calls[-2],
            (matrix._glow_ids[0], {"fill": mock_led_matrix.MockRGBMatrix.BACKGROUND}),
        )
        self.assertEqual(
            matrix.canvas.itemconfig_calls[-1],
            (matrix._pixel_ids[0], {"fill": "#7f4020", "outline": "", "width": 0}),
        )
        self.assertEqual(root.after_calls[-1][0], 33)

    def test_process_and_close_are_safe(self):
        matrix, root = self.build_matrix()

        self.assertTrue(matrix.process())
        self.assertTrue(root.update_called)
        self.assertTrue(root.update_idle_called)

        matrix.close()
        matrix.close()

        self.assertTrue(matrix.closed)
        self.assertTrue(root.destroyed)
        self.assertFalse(matrix.process())

    def test_invalid_panel_size_raises(self):
        options = standard_led_matrix_interface.RGBMatrixOptions(cols=64)
        with self.assertRaises(ValueError):
            self.build_matrix(options)

    def test_old_macos_tk_raises_clean_error(self):
        with mock.patch.object(mock_led_matrix.sys, "platform", "darwin"), mock.patch.object(
            mock_led_matrix.tk, "TkVersion", 8.5
        ), mock.patch.object(mock_led_matrix.tk, "Tk", return_value=FakeRoot()), mock.patch.object(
            mock_led_matrix.tk, "Canvas", FakeCanvas
        ):
            with self.assertRaises(RuntimeError) as ctx:
                mock_led_matrix.MockRGBMatrix()

        self.assertIn("Tkinter 8.6 or newer is required on macOS", str(ctx.exception))

    def test_compatibility_wrapper_exports_expected_symbols(self):
        self.assertIs(rgbmatrix.RGBMatrixOptions, standard_led_matrix_interface.RGBMatrixOptions)
        self.assertIs(rgbmatrix.MockRGBMatrix, mock_led_matrix.MockRGBMatrix)
        self.assertIs(rgbmatrix.RGBMatrix, mock_led_matrix.RGBMatrix)


class DemoTests(unittest.TestCase):
    def test_bouncing_ball_updates_pixels_using_standard_interface(self):
        matrix = FakeDemoMatrix(standard_led_matrix_interface.RGBMatrixOptions())
        demo = demo_bouncing_ball.BouncingBallDemo(matrix.width, matrix.height)

        demo.draw_next_frame(matrix)

        self.assertGreater(len(matrix.pixel_calls), 0)
        self.assertTrue(any((r, g, b) != (0, 0, 0) for _x, _y, r, g, b in matrix.pixel_calls))

    def test_run_demo_clears_draws_and_processes(self):
        matrix = FakeDemoMatrix(standard_led_matrix_interface.RGBMatrixOptions(limit_refresh_rate_hz=1000))
        with mock.patch.object(demo_bouncing_ball.time, "sleep", return_value=None):
            demo_bouncing_ball.run_bouncing_ball_demo(matrix=matrix)

        self.assertTrue(matrix.clear_called)
        self.assertGreater(len(matrix.pixel_calls), 0)
        self.assertEqual(matrix.process_calls, 2)

    def test_main_returns_error_code_on_runtime_error(self):
        stderr = io.StringIO()
        with mock.patch.object(demo_bouncing_ball, "run_bouncing_ball_demo", side_effect=RuntimeError("boom")), mock.patch(
            "sys.stderr", stderr
        ):
            result = demo_bouncing_ball.main()

        self.assertEqual(result, 1)
        self.assertIn("boom", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
