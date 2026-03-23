"""Geometry helpers for deterministic UI layout validation."""

from __future__ import annotations

from ui_lab.canvas import Rect


def rect_within_bounds(rect: Rect, width: int, height: int) -> bool:
    return rect.x >= 0 and rect.y >= 0 and rect.right <= width and rect.bottom <= height


def rects_overlap(first: Rect, second: Rect) -> bool:
    return not (
        first.right <= second.x
        or second.right <= first.x
        or first.bottom <= second.y
        or second.bottom <= first.y
    )


def find_overlaps(regions: dict[str, Rect]) -> list[tuple[str, str]]:
    overlaps: list[tuple[str, str]] = []
    keys = list(regions.keys())
    for index, left in enumerate(keys):
        for right in keys[index + 1 :]:
            if rects_overlap(regions[left], regions[right]):
                overlaps.append((left, right))
    return overlaps


def center_offset_x(container: Rect, content_x: int, content_width: int) -> float:
    content_center = content_x + (content_width / 2.0)
    container_center = container.x + (container.width / 2.0)
    return abs(content_center - container_center)
