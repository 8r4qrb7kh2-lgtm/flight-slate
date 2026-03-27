import unittest
from pathlib import Path
import tempfile

from PIL import Image as PILImage
from ui.core.canvas import PixelCanvas, Rect
from ui.core.image_asset import ImageFrame, load_c_image_frames, load_png_image_frame
from ui.core.widgets import Image

BLACK = (0, 0, 0)
RED = (255, 0, 0)
BLUE = (0, 0, 255)


class CoreImageTests(unittest.TestCase):
    def test_image_widget_stretch_renders_argb_pixels(self) -> None:
        # Frame is 2x1: left red, right blue.
        frame = ImageFrame(
            width=2,
            height=1,
            argb_pixels=(0xFFFF0000, 0xFF0000FF),
        )

        canvas = PixelCanvas(4, 2, BLACK)
        Image(frame=frame, fit="stretch").draw(canvas, Rect(0, 0, 4, 2))

        pixels = canvas.image.load()
        for y in range(2):
            self.assertEqual(pixels[0, y], RED)
            self.assertEqual(pixels[1, y], RED)
            self.assertEqual(pixels[2, y], BLUE)
            self.assertEqual(pixels[3, y], BLUE)

    def test_c_image_loader_reads_airline_asset(self) -> None:
        asset_path = Path(__file__).resolve().parents[1] / "airline-southwest.c"
        frames = load_c_image_frames(asset_path)

        self.assertGreaterEqual(len(frames), 1)
        first = frames[0]
        self.assertEqual(first.width, 32)
        self.assertEqual(first.height, 31)
        self.assertEqual(len(first.argb_pixels), 32 * 31)

    def test_image_widget_original_fit_keeps_native_size(self) -> None:
        # Frame is 2x1 and should remain exactly 2x1 when fit="original".
        frame = ImageFrame(
            width=2,
            height=1,
            argb_pixels=(0xFFFF0000, 0xFF0000FF),
        )

        canvas = PixelCanvas(6, 3, BLACK)
        Image(frame=frame, fit="original").draw(canvas, Rect(0, 0, 6, 3))

        pixels = canvas.image.load()
        # Draw is centered, with no scaling.
        self.assertEqual(pixels[2, 1], RED)
        self.assertEqual(pixels[3, 1], BLUE)
        # Adjacent pixels remain untouched if no scaling occurred.
        self.assertEqual(pixels[1, 1], BLACK)
        self.assertEqual(pixels[4, 1], BLACK)

    def test_png_loader_reads_rgba_pixels(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            png_path = Path(temp_dir) / "sample.png"
            image = PILImage.new("RGBA", (2, 1))
            image.putdata([(255, 0, 0, 255), (0, 0, 255, 128)])
            image.save(png_path)

            frame = load_png_image_frame(png_path)
            self.assertEqual(frame.width, 2)
            self.assertEqual(frame.height, 1)
            self.assertEqual(frame.argb_pixels[0], 0xFFFF0000)
            self.assertEqual(frame.argb_pixels[1], 0x800000FF)


if __name__ == "__main__":
    unittest.main()
