"""Weather + indoor-temperature cache for the idle (no-flight) display.

Module-level singleton. One background executor periodically pulls the
outside temperature from Open-Meteo (no API key, free for personal use).
The inside temperature is write-only from our side — some other process
(iOS Shortcut → webhook, Home Assistant poller, etc.) calls
``set_inside_temp_f`` with a fresh reading; values older than
``_INSIDE_STALE_AFTER_S`` are returned as ``None``.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

_OPEN_METEO_URL = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude={lat:.4f}&longitude={lon:.4f}"
    "&current=temperature_2m&temperature_unit=fahrenheit"
)
_OUTSIDE_REFRESH_S = 600.0      # 10 min — Open-Meteo updates hourly
_OUTSIDE_RETRY_AFTER_FAIL_S = 60.0
_INSIDE_STALE_AFTER_S = 30 * 60.0  # 30 min without an update → treat as unknown


_lat: float = 0.0
_lon: float = 0.0
_configured: bool = False
_executor: ThreadPoolExecutor | None = None

_outside_f: float | None = None
_outside_next_attempt: float = 0.0
_outside_pending: Future[float | None] | None = None

_inside_f: float | None = None
_inside_updated_at: float = 0.0


def configure(lat: float, lon: float) -> None:
    """Set the viewer location and spin up the background fetch executor."""
    global _lat, _lon, _configured, _executor
    _lat = lat
    _lon = lon
    _configured = True
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="weather")


def _fetch_outside() -> float | None:
    url = _OPEN_METEO_URL.format(lat=_lat, lon=_lon)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "flight-slate/0.1"})
        with urllib.request.urlopen(request, timeout=8.0) as response:
            payload = response.read()
        data: dict[str, Any] = json.loads(payload.decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
        return None
    current = data.get("current") if isinstance(data, dict) else None
    temp = current.get("temperature_2m") if isinstance(current, dict) else None
    if isinstance(temp, (int, float)):
        return float(temp)
    return None


def outside_temp_f() -> float | None:
    """Cached outside temp in °F. Kicks off a background refresh when stale."""
    global _outside_f, _outside_next_attempt, _outside_pending
    if not _configured or _executor is None:
        return None

    if _outside_pending is not None and _outside_pending.done():
        pending = _outside_pending
        _outside_pending = None
        try:
            result = pending.result()
        except Exception:  # pragma: no cover - defensive
            result = None
        if result is not None:
            _outside_f = result
            _outside_next_attempt = time.monotonic() + _OUTSIDE_REFRESH_S
        else:
            _outside_next_attempt = time.monotonic() + _OUTSIDE_RETRY_AFTER_FAIL_S

    now = time.monotonic()
    if _outside_pending is None and now >= _outside_next_attempt:
        _outside_next_attempt = now + _OUTSIDE_RETRY_AFTER_FAIL_S  # tentative — success bumps it to full refresh
        _outside_pending = _executor.submit(_fetch_outside)

    return _outside_f


def set_inside_temp_f(temp_f: float | None) -> None:
    """Update the inside-temperature cache.

    External integrations (iOS Shortcut webhook, Home Assistant poller,
    etc.) call this with a fresh reading. Pass ``None`` to clear.
    """
    global _inside_f, _inside_updated_at
    _inside_f = temp_f
    _inside_updated_at = time.monotonic()


def inside_temp_f() -> float | None:
    """Cached inside temp in °F, or None if never set or stale (>30 min)."""
    if _inside_f is None:
        return None
    if (time.monotonic() - _inside_updated_at) > _INSIDE_STALE_AFTER_S:
        return None
    return _inside_f
