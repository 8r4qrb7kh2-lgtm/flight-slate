#!/usr/bin/env python3
"""Minimal launcher for the 128x64 feature lab."""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass

from ui import App, Column, FONT_5x7, Panel, Text, colors
from ui.fonts.import_util import ALNUM_PUNCT_94


@dataclass
class AppState:
    page_index: int = 0


FONT_PAGES = ["3x5", "4x6", "5x7"]


def _load_font(font_key: str):
    if font_key == "5x7":
        return FONT_5x7
    if font_key == "4x6":
        return importlib.import_module("ui.fonts.4x6").FONT_4X6
    if font_key == "3x5":
        return importlib.import_module("ui.fonts.3x5").FONT_3X5
    raise ValueError(f"Unsupported font key: {font_key}")


def clamp_page(index: int) -> int:
    return max(0, min(index, len(FONT_PAGES) - 1))


def build_ui(state: AppState) -> Panel:
    font_key = FONT_PAGES[state.page_index]
    return Panel(
        padding=2,
        bg=colors.BLACK,
        border=colors.BLUE,
        child=Column(
            gap=2,
            children=[
                Text(
                    align="center",
                    font=_load_font(font_key),
                    overflow="wrap",
                    text=f"{font_key}",
                ),
                Text(
                    align="left",
                    font=_load_font(font_key),
                    overflow="wrap",
                    text=f"{ALNUM_PUNCT_94}",
                ),
            ]
        )

    )


def main() -> int:
    try:
        app = App()
        state = AppState()

        while True:
            app.Render(build_ui(state))

            event = app.poll_input()
            if event == "left":
                state.page_index = clamp_page(state.page_index - 1)
            elif event == "right":
                state.page_index = clamp_page(state.page_index + 1)
            elif event == "quit":
                break

        if not app.matrix.closed:
            app.matrix.close()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
