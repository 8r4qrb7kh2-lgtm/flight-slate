"""Artifact export and text-mode inspection for feature pages."""

from __future__ import annotations

import json
from pathlib import Path

from ui_lab.canvas import PixelCanvas
from ui_lab.palette import Palette


def export_canvas(canvas: PixelCanvas, output_dir: Path, stem: str, analysis: dict[str, object]) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / f"{stem}.png"
    upscaled_path = output_dir / f"{stem}@8x.png"
    ascii_path = output_dir / f"{stem}.txt"
    report_path = output_dir / f"{stem}.json"

    palette = Palette()
    mapping = {
        palette.background: " ",
        palette.panel: ".",
        palette.panel_edge: "+",
        palette.text: "#",
        palette.text_dim: "=",
        palette.accent: "*",
        palette.accent_alt: "%",
        palette.success: "@",
        palette.error: "!",
    }

    canvas.save(raw_path)
    canvas.save_upscaled(upscaled_path)
    ascii_path.write_text(canvas.ascii_dump(mapping) + "\n", encoding="utf-8")
    report_path.write_text(json.dumps(analysis, indent=2), encoding="utf-8")

    return {
        "raw": raw_path,
        "upscaled": upscaled_path,
        "ascii": ascii_path,
        "report": report_path,
    }
