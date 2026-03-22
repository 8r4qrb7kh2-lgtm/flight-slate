"""Feature page contract."""

from __future__ import annotations

from dataclasses import dataclass

from ui_lab.canvas import PixelCanvas


@dataclass(frozen=True)
class PageFrame:
    index: int
    total: int
    elapsed_s: float


class FeaturePage:
    key: str = "feature"
    title: str = "Feature"
    animated: bool = False

    def render(self, canvas: PixelCanvas, frame: PageFrame) -> None:
        raise NotImplementedError

    def analyze(self, canvas: PixelCanvas) -> dict[str, object]:
        raise NotImplementedError
