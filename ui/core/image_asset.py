"""Image asset parsing helpers for C and PNG sources."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from PIL import Image as PILImage


@dataclass(frozen=True)
class ImageFrame:
    width: int
    height: int
    argb_pixels: tuple[int, ...]


def load_c_image_frames(path: Path) -> list[ImageFrame]:
    """Load image frames from a Piskel-style C export file.

    Piskel C exports encode pixels as AABBGGRR. We normalize each pixel into
    canonical AARRGGBB so widget rendering stays consistent.
    """
    content = path.read_text(encoding="utf-8")

    frame_count = _extract_define(content, r"#define\s+\S+_FRAME_COUNT\s+(\d+)")
    width = _extract_define(content, r"#define\s+\S+_FRAME_WIDTH\s+(\d+)")
    height = _extract_define(content, r"#define\s+\S+_FRAME_HEIGHT\s+(\d+)")

    values = [int(match, 16) for match in re.findall(r"0x[0-9a-fA-F]+", content)]
    expected = frame_count * width * height
    if len(values) < expected:
        raise ValueError(
            f"Expected at least {expected} pixel entries in {path.name}, found {len(values)}"
        )

    values = [_normalize_piskel_pixel(value) for value in values[:expected]]
    frames: list[ImageFrame] = []
    index = 0
    frame_size = width * height
    for _ in range(frame_count):
        pixels = tuple(values[index : index + frame_size])
        frames.append(ImageFrame(width=width, height=height, argb_pixels=pixels))
        index += frame_size

    return frames


def load_png_image_frame(path: Path) -> ImageFrame:
    """Load a single PNG into an `ImageFrame` using AARRGGBB pixels."""
    with PILImage.open(path) as image:
        rgba = image.convert("RGBA")
        width, height = rgba.size
        raw = rgba.tobytes()
        pixels: list[int] = []
        for index in range(0, len(raw), 4):
            red = raw[index]
            green = raw[index + 1]
            blue = raw[index + 2]
            alpha = raw[index + 3]
            pixels.append((alpha << 24) | (red << 16) | (green << 8) | blue)
    return ImageFrame(width=width, height=height, argb_pixels=tuple(pixels))


def _extract_define(content: str, pattern: str) -> int:
    match = re.search(pattern, content)
    if match is None:
        raise ValueError(f"Could not parse define with pattern: {pattern}")
    return int(match.group(1))


def _normalize_piskel_pixel(raw: int) -> int:
    """Convert AABBGGRR (Piskel export) to AARRGGBB."""
    alpha = (raw >> 24) & 0xFF
    blue = (raw >> 16) & 0xFF
    green = (raw >> 8) & 0xFF
    red = raw & 0xFF
    return (alpha << 24) | (red << 16) | (green << 8) | blue
