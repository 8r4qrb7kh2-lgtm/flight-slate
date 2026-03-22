"""Compatibility wrapper matching the usual rpi-rgb-led-matrix import shape."""

from demo_bouncing_ball import main, run_bouncing_ball_demo
from mock_led_matrix import MockRGBMatrix, RGBMatrix, glow_channel, glow_rgb_to_hex, scale_rgb_to_hex
from standard_led_matrix_interface import InteractiveLEDMatrix, LEDMatrix, RGBMatrixOptions

__all__ = [
    "InteractiveLEDMatrix",
    "LEDMatrix",
    "MockRGBMatrix",
    "RGBMatrix",
    "RGBMatrixOptions",
    "glow_channel",
    "glow_rgb_to_hex",
    "main",
    "run_bouncing_ball_demo",
    "scale_rgb_to_hex",
]
