"""Shared LED matrix interface definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class RGBMatrixOptions:
    rows: int = 64
    cols: int = 128
    chain_length: int = 1
    parallel: int = 1
    brightness: int = 100
    hardware_mapping: str = "mock"
    panel_type: str | None = None
    row_addr_type: int | None = None
    multiplexing: int | None = None
    rgb_sequence: str | None = None
    pwm_bits: int = 11
    limit_refresh_rate_hz: int = 30

    @property
    def width(self) -> int:
        return self.cols * self.chain_length

    @property
    def height(self) -> int:
        return self.rows * self.parallel


@runtime_checkable
class LEDMatrix(Protocol):
    width: int
    height: int

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:
        """Set a single pixel."""

    def Clear(self) -> None:
        """Clear all pixels."""


@runtime_checkable
class InteractiveLEDMatrix(LEDMatrix, Protocol):
    @property
    def closed(self) -> bool:
        """Whether the matrix window or loop has been closed."""

    def process(self) -> bool:
        """Process one UI/event iteration."""

    def close(self) -> None:
        """Close the matrix."""
