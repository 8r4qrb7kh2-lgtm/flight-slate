"""Per-flight position history for drawing the actual flown path.

We don't have access to a flight's full historical track from ADSB — only
the live position. Each poll (every ``FLIGHT_REFRESH_SECONDS``) we drop a
breadcrumb here keyed by ICAO24, and the route-map widget reads them back
to draw the path the aircraft has actually flown since we picked it up.

The data is "best effort": for the part of the flight before we first
saw it (origin → first observation), the renderer falls back to a
great-circle line, which the user understands is interpolated.

Stored as a module-level singleton because the lifecycle is the same as
the running display process; introducing it as a class on FlightState
would mean threading it through six call sites for no real benefit.
"""

from __future__ import annotations

import threading
import time

from ui.flight.api import AirSnapshot


# Drop history older than this. A scheduled flight rarely exceeds 6 hours
# wheels-up to wheels-down, and we don't want to draw tracks from a
# previous day's same-callsign reuse. ICAO24 hex changes per airframe so
# a fresh-flown re-registered tail isn't an issue, but a long-stationary
# aircraft (e.g. parked GA) would otherwise accumulate noise.
_MAX_AGE_S = 6 * 3600.0
# Hard cap on points per aircraft so memory stays bounded even if a
# transponder broadcasts at high rate from a stuck plane.
_MAX_POINTS = 1024
# Drop the entire history bucket if we haven't seen the icao24 in this
# long — it's no longer in our airspace.
_STALE_AFTER_S = 30 * 60.0
# Skip recording new points that are within this great-circle distance
# of the last point. Avoids accumulating thousands of duplicate samples
# for a stationary or slow-taxiing aircraft. ~50 m at the equator.
_MIN_MOVE_DEG = 0.0005


class _PathHistory:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tracks: dict[str, list[tuple[float, float, float]]] = {}
        self._last_seen: dict[str, float] = {}

    def record(self, snapshot: AirSnapshot) -> None:
        """Append the selected flight's position to its track buffer.

        Only the snapshot's ``selected`` flight is recorded — radar pings
        come and go too quickly and we only ever draw the path of the
        hero flight. Cleanup also happens here on every call so we don't
        need a separate pruning loop.
        """
        if snapshot is None:
            return
        now = time.time()
        with self._lock:
            self._prune(now)
            sel = snapshot.selected
            if sel is None or not sel.icao24:
                return
            track = self._tracks.setdefault(sel.icao24, [])
            if track:
                _, last_lat, last_lon = track[-1]
                if (
                    abs(sel.latitude - last_lat) < _MIN_MOVE_DEG
                    and abs(sel.longitude - last_lon) < _MIN_MOVE_DEG
                ):
                    self._last_seen[sel.icao24] = now
                    return
            track.append((now, sel.latitude, sel.longitude))
            if len(track) > _MAX_POINTS:
                # Drop the oldest sample, not random ones — we want the
                # earliest part of the recorded track preserved if at all
                # possible (it's the part the renderer can't reconstruct).
                track.pop(0)
            self._last_seen[sel.icao24] = now

    def get_path(self, icao24: str | None) -> list[tuple[float, float]]:
        """Return ``(lat, lon)`` points for an aircraft, oldest first."""
        if not icao24:
            return []
        now = time.time()
        with self._lock:
            self._prune(now)
            track = self._tracks.get(icao24)
            if not track:
                return []
            cutoff = now - _MAX_AGE_S
            return [(lat, lon) for ts, lat, lon in track if ts >= cutoff]

    def _prune(self, now: float) -> None:
        # Caller holds the lock.
        for icao, last in list(self._last_seen.items()):
            if now - last > _STALE_AFTER_S:
                self._tracks.pop(icao, None)
                self._last_seen.pop(icao, None)


_path_history = _PathHistory()


def record(snapshot: AirSnapshot) -> None:
    """Public entry point for the poll loop to drop a breadcrumb."""
    _path_history.record(snapshot)


def get_path(icao24: str | None) -> list[tuple[float, float]]:
    """Public entry point for the renderer to read back the track."""
    return _path_history.get_path(icao24)
