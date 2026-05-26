"""Weather + indoor-temperature cache for the idle (no-flight) display.

Module-level singleton. One background executor periodically pulls the
outside temperature from Open-Meteo (no API key, free for personal use),
falling back to the U.S. National Weather Service (api.weather.gov) when
Open-Meteo is unreachable. The inside temperature is write-only from our
side — some other process (iOS Shortcut → webhook, Home Assistant poller,
etc.) calls ``set_inside_temp_f`` with a fresh reading; values older than
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
_NWS_POINT_URL = "https://api.weather.gov/points/{lat:.4f},{lon:.4f}"
_NWS_OBSERVATION_URL = "https://api.weather.gov/stations/{station}/observations/latest"
_USER_AGENT = "flight-slate/0.1 (https://github.com/8r4qrb7kh2-lgtm/flight-slate)"
_HTTP_TIMEOUT_S = 8.0

_OUTSIDE_REFRESH_S = 600.0      # 10 min — Open-Meteo updates hourly
_OUTSIDE_RETRY_AFTER_FAIL_S = 60.0
_NWS_MAX_STATIONS = 3           # try up to N nearest stations per fallback fetch
_INSIDE_STALE_AFTER_S = 30 * 60.0  # 30 min without an update → treat as unknown


_lat: float = 0.0
_lon: float = 0.0
_configured: bool = False
_executor: ThreadPoolExecutor | None = None

_outside_f: float | None = None
_outside_next_attempt: float = 0.0
_outside_pending: Future[float | None] | None = None

# NWS observation stations near (_lat, _lon), ordered by proximity. Discovered
# lazily on first Open-Meteo failure; re-discovered later if the list is empty.
_nws_station_ids: list[str] = []

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


def _http_get_json(url: str) -> Any:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT_S) as response:
            payload = response.read()
        return json.loads(payload.decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
        return None


def _fetch_open_meteo() -> float | None:
    data = _http_get_json(_OPEN_METEO_URL.format(lat=_lat, lon=_lon))
    current = data.get("current") if isinstance(data, dict) else None
    temp = current.get("temperature_2m") if isinstance(current, dict) else None
    if isinstance(temp, (int, float)):
        return float(temp)
    return None


def _discover_nws_stations() -> list[str]:
    """Return NWS observation station IDs near (_lat, _lon), ordered by proximity."""
    point = _http_get_json(_NWS_POINT_URL.format(lat=_lat, lon=_lon))
    props = point.get("properties") if isinstance(point, dict) else None
    stations_url = props.get("observationStations") if isinstance(props, dict) else None
    if not isinstance(stations_url, str):
        return []
    stations = _http_get_json(stations_url)
    features = stations.get("features") if isinstance(stations, dict) else None
    if not isinstance(features, list):
        return []
    out: list[str] = []
    for feature in features:
        sp = feature.get("properties") if isinstance(feature, dict) else None
        sid = sp.get("stationIdentifier") if isinstance(sp, dict) else None
        if isinstance(sid, str) and sid:
            out.append(sid)
    return out


def _nws_temp_f_from_observation(data: Any) -> float | None:
    props = data.get("properties") if isinstance(data, dict) else None
    temp = props.get("temperature") if isinstance(props, dict) else None
    if not isinstance(temp, dict):
        return None
    value = temp.get("value")
    if not isinstance(value, (int, float)):
        return None
    unit = temp.get("unitCode", "")
    if unit in ("wmoUnit:degC", "unit:degC"):
        return float(value) * 9.0 / 5.0 + 32.0
    if unit in ("wmoUnit:degF", "unit:degF"):
        return float(value)
    return None


def _fetch_nws() -> float | None:
    """Try the nearest N NWS observation stations; return the first valid reading."""
    global _nws_station_ids
    if not _nws_station_ids:
        _nws_station_ids = _discover_nws_stations()
    for station in _nws_station_ids[:_NWS_MAX_STATIONS]:
        data = _http_get_json(_NWS_OBSERVATION_URL.format(station=station))
        temp_f = _nws_temp_f_from_observation(data)
        if temp_f is not None:
            return temp_f
    return None


def _fetch_outside() -> float | None:
    temp = _fetch_open_meteo()
    if temp is not None:
        return temp
    return _fetch_nws()


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
