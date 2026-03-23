from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from typing import List, Tuple

from PIL import Image


BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "ui/fonts/piskel"
OUTPUT_DIR = BASE_DIR / "ui/fonts/fonts/generated"


def sanitize_name(name: str) -> str:
    out = []
    for ch in name:
        if ch.isalnum() or ch == "_":
            out.append(ch.lower())
        elif ch in (" ", "-", "."):
            out.append("_")
    result = "".join(out).strip("_")
    return result or "font"


def load_piskel_frames(json_path: Path) -> Tuple[str, int, int, List[List[List[int]]]]:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    piskel = data["piskel"]

    name = piskel.get("name") or json_path.stem
    width = piskel["width"]
    height = piskel["height"]

    raw_layers = piskel["layers"]
    layers = [json.loads(layer_str) for layer_str in raw_layers]

    frame_count = max(layer["frameCount"] for layer in layers)

    frames = [
        [[0 for _ in range(width)] for _ in range(height)]
        for _ in range(frame_count)
    ]

    for layer in layers:
        for chunk in layer.get("chunks", []):
            layout = chunk["layout"]

            base64_png = chunk["base64PNG"]
            if "," in base64_png:
                base64_png = base64_png.split(",", 1)[1]

            png_bytes = base64.b64decode(base64_png)
            sheet = Image.open(io.BytesIO(png_bytes)).convert("RGBA")

            tiles_x = sheet.width // width
            tiles_y = sheet.height // height
            total_tiles = tiles_x * tiles_y

            for frame_index, tile_indices in enumerate(layout):
                if frame_index >= frame_count:
                    continue

                for tile_index in tile_indices:
                    if tile_index is None or tile_index < 0 or tile_index >= total_tiles:
                        continue

                    tile_x = (tile_index % tiles_x) * width
                    tile_y = (tile_index // tiles_x) * height

                    tile = sheet.crop((tile_x, tile_y, tile_x + width, tile_y + height))

                    for y in range(height):
                        for x in range(width):
                            _, _, _, a = tile.getpixel((x, y))
                            if a != 0:
                                frames[frame_index][y][x] = 1

    return name, width, height, frames


def pack_frame_rows(frame: List[List[int]]) -> List[int]:
    packed = []
    for row in frame:
        value = 0
        for bit in row:
            value = (value << 1) | (1 if bit else 0)
        packed.append(value)
    return packed


def build_ascii_map(frames: List[List[List[int]]]):
    ascii_94 = (
        " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~"
    )

    if len(frames) != len(ascii_94):
        return None

    return {ch: frame for ch, frame in zip(ascii_94, frames)}


def write_python_module(
    out_path: Path,
    font_name: str,
    width: int,
    height: int,
    frames: List[List[List[int]]],
) -> None:
    ascii_map = build_ascii_map(frames)
    packed_frames = [pack_frame_rows(frame) for frame in frames]

    lines = [
        f'FONT_NAME = {font_name!r}',
        f"WIDTH = {width}",
        f"HEIGHT = {height}",
        f"FRAME_COUNT = {len(frames)}",
        "",
        "frames = [",
    ]

    for frame in frames:
        lines.append("    [")
        for row in frame:
            lines.append(f"        {row!r},")
        lines.append("    ],")
    lines.append("]")
    lines.append("")
    lines.append("packed_frames = [")
    for packed in packed_frames:
        lines.append(f"    {packed!r},")
    lines.append("]")

    if ascii_map is not None:
        lines.append("")
        lines.append("glyphs = {")
        for ch in ascii_map:
            lines.append(f"    {ch!r}: frames[{ord(ch) - 32}],")
        lines.append("}")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def convert_all() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    files = sorted(
        [
            *INPUT_DIR.glob("*.piskel"),
            *INPUT_DIR.glob("*.json"),
        ]
    )

    if not files:
        print(f"No .piskel or .json files found in {INPUT_DIR}")
        return

    for file_path in files:
        try:
            font_name, width, height, frames = load_piskel_frames(file_path)
            module_name = sanitize_name(file_path.stem) + ".py"
            out_path = OUTPUT_DIR / module_name

            write_python_module(out_path, font_name, width, height, frames)

            print(
                f"Converted {file_path} -> {out_path} "
                f"({width}x{height}, {len(frames)} frames)"
            )
        except Exception as e:
            print(f"Failed to convert {file_path}: {e}")


if __name__ == "__main__":
    convert_all()