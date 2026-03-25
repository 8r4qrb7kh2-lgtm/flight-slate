"""Standalone core UI package."""

from ui.core.app import App
from ui.core.colors import colors
from ui.core.widgets import Column, Marquee, Panel, Row, Text

__all__ = [
    "App",
    "Column",
    "Row",
    "Panel",
    "Marquee",
    "Text",
    "colors",
]
