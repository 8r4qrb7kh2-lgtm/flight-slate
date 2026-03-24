#!/usr/bin/env python3
"""Core UI demo launcher with Font Demo and Column/Row Demo pages."""

from __future__ import annotations

import sys
from dataclasses import dataclass

from ui import App, Column, FONT_5X7, FONT_3X5, FONT_4X6, Panel, Row, Text, colors
from ui.fonts.import_util import ALNUM_PUNCT_94


@dataclass
class AppState:
    page_index: int = 0


DEMO_PAGES = ["font-demo", "layout-demo"]


def clamp_page(index: int) -> int:
    return max(0, min(index, len(DEMO_PAGES) - 1))


def _build_font_demo_page() -> Panel:
    return Panel(
        padding=2,
        bg=colors.BLACK,
        border=colors.BLUE,
        child=Column(
            gap=1,
            sizes=[8, 10, 10, 34],
            children=[
                Text(
                    align="center",
                    font=FONT_5X7,
                    overflow="clip",
                    text="FONT DEMO",
                ),
                Text(
                    align="left",
                    font=FONT_3X5,
                    overflow="wrap",
                    text="3x5: ABC123!?",
                ),
                Text(
                    align="left",
                    font=FONT_4X6,
                    overflow="wrap",
                    text="4x6: MERIDIAN",
                ),
                Text(
                    align="left",
                    font=FONT_5X7,
                    overflow="wrap",
                    text=f"{ALNUM_PUNCT_94}",
                ),
            ]
        )

    )


def _build_layout_demo_page() -> Panel:
    return Panel(
        padding=1,
        bg=colors.BLACK,
        border=colors.CYAN,
        child=Column(
            gap=1,
            sizes=[8, 54],
            children=[
                Text(
                    align="center",
                    font=FONT_5X7,
                    overflow="clip",
                    text="ROW/COLUMN",
                ),
                Row(
                    gap=1,
                    sizes=[10, 90],
                    children=[
                        Panel(bg=colors.BLUE, border=colors.WHITE, child=None),
                        Column(
                            gap=1,
                            sizes=[1, 1, 1],
                            children=[
                                Row(
                                    gap=1,
                                    sizes=[1, 1],
                                    children=[
                                        Panel(bg=colors.CYAN, border=colors.WHITE, child=None),
                                        Panel(bg=colors.DIM_WHITE, border=colors.WHITE, child=None),
                                    ],
                                ),
                                Row(
                                    gap=1,
                                    sizes=[10, 90],
                                    children=[
                                        Panel(bg=colors.BLUE, border=colors.WHITE, child=None),
                                        Panel(bg=colors.DIM_WHITE, border=colors.WHITE, child=None),
                                    ],
                                ),
                                Row(
                                    gap=1,
                                    sizes=[1, 1, 1],
                                    children=[
                                        Panel(bg=colors.CYAN, border=colors.WHITE, child=None),
                                        Panel(bg=colors.BLUE, border=colors.WHITE, child=None),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        ),
    )


def build_pages() -> list[Panel]:
    return [_build_font_demo_page(), _build_layout_demo_page()]


def main() -> int:
    try:
        app = App()
        state = AppState()
        pages = build_pages()
        needs_render = True

        while True:
            event = app.poll_input()
            if event == "left":
                state.page_index = clamp_page(state.page_index - 1)
                needs_render = True
            elif event == "right":
                state.page_index = clamp_page(state.page_index + 1)
                needs_render = True
            elif event == "quit":
                break

            if needs_render:
                app.Render(pages[state.page_index])
                needs_render = False

        if not app.matrix.closed:
            app.matrix.close()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
