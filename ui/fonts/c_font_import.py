"""Import bitmap fonts from C source files exported by Piskel."""

from __future__ import annotations

from pathlib import Path
import re


def load_c_font_frames(path: Path) -> tuple[int, int, list[list[list[int]]]]:
	content = path.read_text(encoding="utf-8")

	frame_count = _extract_define(content, r"#define\s+\d+X\d+_FONT_FRAME_COUNT\s+(\d+)")
	width = _extract_define(content, r"#define\s+\d+X\d+_FONT_FRAME_WIDTH\s+(\d+)")
	height = _extract_define(content, r"#define\s+\d+X\d+_FONT_FRAME_HEIGHT\s+(\d+)")

	values = [int(match, 16) for match in re.findall(r"0x[0-9a-fA-F]+", content)]
	expected = frame_count * width * height
	if len(values) < expected:
		raise ValueError(
			f"Expected at least {expected} pixel entries in {path.name}, found {len(values)}"
		)

	values = values[:expected]
	frames: list[list[list[int]]] = []
	idx = 0
	for _ in range(frame_count):
		frame: list[list[int]] = []
		for _ in range(height):
			row: list[int] = []
			for _ in range(width):
				# Piskel C export stores ARGB; only alpha indicates pixel presence.
				alpha = (values[idx] >> 24) & 0xFF
				row.append(1 if alpha != 0 else 0)
				idx += 1
			frame.append(row)
		frames.append(frame)

	return width, height, frames


def load_project_c_font(filename: str) -> tuple[int, int, list[list[list[int]]]]:
	root = Path(__file__).resolve().parents[2]
	return load_c_font_frames(root / filename)


def _extract_define(content: str, pattern: str) -> int:
	match = re.search(pattern, content)
	if match is None:
		raise ValueError(f"Could not parse define with pattern: {pattern}")
	return int(match.group(1))
