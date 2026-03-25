"""Native acceleration bridge for core rendering."""

from __future__ import annotations

try:
    from . import _render_native as native_backend
except Exception:
    native_backend = None

__all__ = ["native_backend"]
