#!/usr/bin/env python3
"""Flight Slate live-flight display entry point.

Shows the closest live flight inside a configured geographical region as a hero
panel on the LED matrix. Flight positions come from ADSB.lol and route info
from adsbdb.com. Both endpoints are free and require no auth.

Configuration (environment variables):

* ``FLIGHT_CENTER_LAT`` / ``FLIGHT_CENTER_LON`` — viewer position (default
  10600 Chester Ave, Cleveland OH: 41.5055390, -81.6142095).
* ``FLIGHT_RADIUS_NM`` — max distance an aircraft can be and still qualify
  (default 100).
* ``FLIGHT_VIEW_BEARING_DEG`` — compass bearing the window faces (default 180,
  due south).
* ``FLIGHT_VIEW_CONE_DEG`` — horizontal field of view of the window in degrees
  (default 120). Aircraft outside ``bearing ± cone/2`` are excluded.
* ``FLIGHT_REFRESH_SECONDS`` — how often to poll ADSB.lol (default 5).
* ``FLIGHT_ROUTE_LOOKUPS`` — set to ``0`` to disable the adsbdb.com route
  enrichment (useful when offline).

Hardware geometry and other knobs share the same env vars as ``core_ui_demo``
(``FLIGHT_SLATE_MATRIX_*``, ``FLIGHT_SLATE_HARDWARE_MAPPING``, etc.).
"""

from __future__ import annotations

import ctypes
import os
import sys
import time
import urllib.error
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from standard_led_matrix_interface import RGBMatrixOptions
from ui import App
from ui.flight import AirSnapshot, PingHistory, Region, build_flight_hero_page, fetch_air_snapshot
from ui.flight import events, inside_temp_server, nest, path_history, weather


TARGET_REFRESH_HZ = 30
# Default center: 10600 Chester Avenue, Cleveland OH 44106 (geocoded via OSM).
DEFAULT_CENTER_LAT = 41.5055390
DEFAULT_CENTER_LON = -81.6142095
DEFAULT_RADIUS_NM = 26.07  # 30 statute miles
DEFAULT_POLL_SECONDS = 5.0
# View cone: south-facing 14th-floor window. 120° total field of view gives the
# visible bearings 120°–240° (east-of-south through west-of-south).
DEFAULT_VIEW_BEARING_DEG = 180.0
DEFAULT_VIEW_CONE_DEG = 120.0
# Only include aircraft low enough to be plausibly visible from a window.
DEFAULT_MAX_ALTITUDE_FT = 10_000.0
# Radar scope radius — tighter than the overall fetch so the scope shows only
# planes in the immediate neighbourhood. 10 statute miles ≈ 8.69 nm.
DEFAULT_RADAR_RADIUS_NM = 8.69


def _read_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


def _read_float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw.strip())
    except ValueError:
        return default


def _read_bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _read_str_env(name: str) -> str | None:
    raw = os.environ.get(name)
    if raw is None:
        return None
    value = raw.strip()
    return value or None


def _default_hardware_mapping() -> str:
    env_value = os.environ.get("FLIGHT_SLATE_HARDWARE_MAPPING")
    if env_value and env_value.strip():
        return env_value.strip()
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        return "adafruit-hat"
    return "mock"


def _build_matrix_options() -> RGBMatrixOptions:
    return RGBMatrixOptions(
        rows=_read_int_env("FLIGHT_SLATE_MATRIX_ROWS", 64),
        cols=_read_int_env("FLIGHT_SLATE_MATRIX_COLS", 128),
        chain_length=_read_int_env("FLIGHT_SLATE_MATRIX_CHAIN", 1),
        parallel=_read_int_env("FLIGHT_SLATE_MATRIX_PARALLEL", 1),
        brightness=max(1, min(100, _read_int_env("FLIGHT_SLATE_MATRIX_BRIGHTNESS", 100))),
        hardware_mapping=_default_hardware_mapping(),
        panel_type=_read_str_env("FLIGHT_SLATE_LED_PANEL_TYPE"),
        row_addr_type=(
            None
            if (row_addr := _read_int_env("FLIGHT_SLATE_LED_ROW_ADDR_TYPE", -1)) < 0
            else row_addr
        ),
        multiplexing=(
            None
            if (mux := _read_int_env("FLIGHT_SLATE_LED_MULTIPLEXING", -1)) < 0
            else mux
        ),
        rgb_sequence=_read_str_env("FLIGHT_SLATE_LED_RGB_SEQUENCE"),
        pwm_bits=max(1, min(11, _read_int_env("FLIGHT_SLATE_MATRIX_PWM_BITS", 11))),
        limit_refresh_rate_hz=max(1, _read_int_env("FLIGHT_SLATE_REFRESH_HZ", TARGET_REFRESH_HZ)),
    )


def _read_region() -> Region:
    cone = max(1.0, min(360.0, _read_float_env("FLIGHT_VIEW_CONE_DEG", DEFAULT_VIEW_CONE_DEG)))
    bearing = _read_float_env("FLIGHT_VIEW_BEARING_DEG", DEFAULT_VIEW_BEARING_DEG) % 360.0
    max_alt = _read_float_env("FLIGHT_MAX_ALTITUDE_FT", DEFAULT_MAX_ALTITUDE_FT)
    radar_radius = max(0.1, _read_float_env("FLIGHT_RADAR_RADIUS_NM", DEFAULT_RADAR_RADIUS_NM))
    return Region(
        center_lat=_read_float_env("FLIGHT_CENTER_LAT", DEFAULT_CENTER_LAT),
        center_lon=_read_float_env("FLIGHT_CENTER_LON", DEFAULT_CENTER_LON),
        radius_nm=max(1.0, _read_float_env("FLIGHT_RADIUS_NM", DEFAULT_RADIUS_NM)),
        view_bearing_deg=bearing,
        view_cone_deg=cone,
        max_altitude_ft=max_alt if max_alt > 0 else None,
        radar_radius_nm=radar_radius,
    )


@dataclass
class FlightState:
    region: Region
    snapshot: AirSnapshot | None = None
    last_fetch_time: float = 0.0
    last_error: str | None = None
    pending: Future[AirSnapshot] | None = None
    ever_succeeded: bool = False
    history: PingHistory = field(default_factory=PingHistory)


def _poll_fetch_result(state: FlightState) -> bool:
    if state.pending is None or not state.pending.done():
        return False

    future = state.pending
    state.pending = None
    state.last_fetch_time = time.time()
    try:
        result = future.result()
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError, ValueError) as exc:
        state.last_error = str(exc) or exc.__class__.__name__
        return True
    except Exception as exc:  # pragma: no cover - unexpected exceptions still shouldn't crash display
        state.last_error = f"{exc.__class__.__name__}: {exc}"
        return True

    state.last_error = None
    state.ever_succeeded = True
    state.snapshot = state.history.decorate(result)
    # Drop a breadcrumb for the route-map's flown-path overlay.
    path_history.record(state.snapshot)
    return True


def _start_fetch(
    state: FlightState,
    executor: ThreadPoolExecutor,
    *,
    enrich_route: bool,
) -> None:
    if state.pending is not None:
        return
    state.pending = executor.submit(
        fetch_air_snapshot,
        state.region,
        enrich_route=enrich_route,
    )


def _status_line(state: FlightState) -> str | None:
    if state.last_error:
        return f"NET: {state.last_error[:22]}"
    if state.snapshot is None or state.snapshot.selected is None:
        if not state.ever_succeeded:
            return "CONTACTING ADS-B..."
        return "NO AIRCRAFT IN VIEW"
    return None


class _HighResWindowsTimer:
    def __init__(self) -> None:
        self._enabled = False

    def __enter__(self) -> "_HighResWindowsTimer":
        if sys.platform == "win32":
            try:
                winmm = ctypes.WinDLL("winmm")
                if winmm.timeBeginPeriod(1) == 0:
                    self._enabled = True
            except Exception:
                self._enabled = False
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._enabled and sys.platform == "win32":
            try:
                ctypes.WinDLL("winmm").timeEndPeriod(1)
            except Exception:
                pass


def _sleep_until(deadline: float) -> None:
    while True:
        now = time.perf_counter()
        remaining = deadline - now
        if remaining <= 0:
            return
        if remaining > 0.002:
            time.sleep(remaining - 0.001)
        else:
            while time.perf_counter() < deadline:
                pass
            return


def main() -> int:
    poll_interval_s = max(1.0, _read_float_env("FLIGHT_REFRESH_SECONDS", DEFAULT_POLL_SECONDS))
    enrich_route = _read_bool_env("FLIGHT_ROUTE_LOOKUPS", True)

    try:
        with _HighResWindowsTimer(), ThreadPoolExecutor(max_workers=1) as fetch_executor:
            app = App(options=_build_matrix_options())
            state = FlightState(region=_read_region())
            half = state.region.view_cone_deg / 2.0
            bearing_lo = (state.region.view_bearing_deg - half) % 360.0
            bearing_hi = (state.region.view_bearing_deg + half) % 360.0
            print(
                f"[flight-slate] region: lat={state.region.center_lat:.6f} "
                f"lon={state.region.center_lon:.6f} "
                f"radius={state.region.radius_nm:.0f} nm "
                f"cone={state.region.view_cone_deg:.0f}° centered {state.region.view_bearing_deg:.0f}° "
                f"(visible bearings {bearing_lo:.0f}°..{bearing_hi:.0f}°) "
                f"poll={poll_interval_s:.1f}s"
            )

            weather.configure(state.region.center_lat, state.region.center_lon)
            ics_raw = _read_str_env("FLIGHT_SLATE_CALENDAR_ICS_URL") or ""
            events.configure([u.strip() for u in ics_raw.split(",") if u.strip()] or None)
            inside_temp_server.start(_read_int_env("FLIGHT_INSIDE_TEMP_PORT", 8080))
            nest.start(interval_s=_read_float_env("NEST_POLL_SECONDS", 900.0))
            _start_fetch(state, fetch_executor, enrich_route=enrich_route)

            frame_delay = 1.0 / max(1, app.options.limit_refresh_rate_hz)
            next_deadline = time.perf_counter() + frame_delay
            last_poll_start = 0.0

            while True:
                event = app.poll_input()
                if event == "quit":
                    break

                now_mono = time.perf_counter()
                _poll_fetch_result(state)

                if state.pending is None and (now_mono - last_poll_start) >= poll_interval_s:
                    last_poll_start = now_mono
                    _start_fetch(state, fetch_executor, enrich_route=enrich_route)

                page = build_flight_hero_page(state.snapshot, status_line=_status_line(state))
                app.Render(page)

                _sleep_until(next_deadline)
                next_deadline += frame_delay
                # Drop catch-up frames after a long pause (e.g. ctrl-Z) so we don't burst-render.
                if next_deadline < time.perf_counter():
                    next_deadline = time.perf_counter() + frame_delay

            if not app.matrix.closed:
                app.matrix.close()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
