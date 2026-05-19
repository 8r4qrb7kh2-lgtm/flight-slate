"""AirLabs flight-schedule lookup for delay/early calculations.

Used to obtain *scheduled* arrival times that FR24's API doesn't return.
We compare AirLabs' ``arr_time_utc`` (scheduled) against the slate's locally
computed ``eta_utc`` (current estimate) to compute "X min late / early" for
the displayed flight.

Uses the ``/schedules`` endpoint rather than ``/flight``: ``/flight`` returns
*one* instance per callsign and frequently picks the wrong one when a flight
number is reused on the same day (e.g. Republic running DL5674 BOS-CLE in
both the morning and afternoon). ``/schedules`` returns every instance for
the day so we can disambiguate by destination and live status.

The free AirLabs tier is 1,000 calls/month, so caching is aggressive:

* Positive cache: per (callsign, dest_iata), valid for 20 hours. A given
  flight's schedule for the day doesn't change once filed; reusing the same
  callsign on a future day will refresh after the TTL expires.
* Negative cache: per (callsign, dest_iata), 1 hour. Skip non-commercial /
  unscheduled callsigns (private aircraft, military) without burning budget.
* Network errors aren't cached — retried next snapshot.

Configured by env var:
    AIRLABS_API_KEY  — your AirLabs API key (free at airlabs.co)
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any


_SCHEDULES_URL = "https://airlabs.co/api/v9/schedules"
_TIMEOUT_S = 8.0
_POSITIVE_TTL_S = 20 * 3600.0
_NEGATIVE_TTL_S = 3600.0

# Callsign shaped like a tail registration (N + digits + optional letters).
# AirLabs doesn't carry schedules for these — skip entirely so we don't waste
# the monthly quota negative-caching every passing GA/medical flight.
_TAIL_NUMBER_RE = re.compile(r"^N\d+[A-Z]*$")


# (callsign, dest_iata) → (cached_at, scheduled_arrival_utc_iso)
_known: dict[tuple[str, str], tuple[float, str]] = {}
_negative: dict[tuple[str, str], float] = {}

# Wall-clock timestamp (epoch seconds) before which AirLabs has told us the
# quota is exhausted. Skipping the network call entirely while blocked saves
# the one extra call per (callsign, dest_iata) miss we'd otherwise spend
# rediscovering the same error every negative-cache TTL.
_blocked_until_wall: float | None = None


def _normalize_callsign(callsign: str) -> str:
    """Strip whitespace + non-alphanumerics, uppercase. ADSB callsigns are
    typically ICAO format (SWA2936, UAL1234) — we send those via flight_icao.
    """
    return "".join(ch for ch in callsign.upper() if ch.isalnum())


def _looks_icao(callsign: str) -> bool:
    """ICAO callsigns lead with a 3-letter airline prefix; IATA leads with 2."""
    return len(callsign) >= 4 and callsign[:3].isalpha()


def _arrival_to_iso_utc(value: Any) -> str | None:
    """Convert an AirLabs ``YYYY-MM-DD HH:MM`` UTC string to ISO-8601 with Z."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) < 16:
        return None
    # AirLabs format: "2026-04-25 00:25" — naive UTC, no seconds.
    return text[:10] + "T" + text[11:16] + ":00Z"


def _select_instance(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the AirLabs schedule entry that matches the live aircraft.

    ``/schedules`` returns every instance of a flight number for the day —
    morning and afternoon legs, return legs, future days. The live aircraft
    we're looking up is exactly one of these. Selection rules, in order:

    1. ``status=active`` — the flight currently in the air. There is almost
       never more than one active instance of the same callsign at a time.
    2. Falling back: an instance whose scheduled departure has passed and
       whose scheduled arrival hasn't (i.e. timestamps bracket "now"). Covers
       cases where AirLabs hasn't updated ``status`` yet.
    """
    if not items:
        return None
    active = [r for r in items if r.get("status") == "active"]
    if active:
        if len(active) == 1:
            return active[0]
        # Tiebreak on the most recent actual departure — the one that took
        # off most recently is the one currently airborne.
        active.sort(key=lambda r: r.get("dep_time_ts") or 0, reverse=True)
        return active[0]
    now = time.time()
    for r in items:
        dep_ts = r.get("dep_time_ts")
        arr_ts = r.get("arr_time_ts")
        if (
            isinstance(dep_ts, (int, float)) and dep_ts <= now
            and isinstance(arr_ts, (int, float)) and arr_ts >= now
        ):
            return r
    return None


def _next_quota_reset_utc(error_code: str) -> datetime:
    """Best-effort UTC time at which the named AirLabs limit refills.

    Monthly limits reset at the start of the next UTC month; daily limits at
    the next UTC midnight. Anything else falls back to a 24-hour back-off,
    which is conservative but bounded.
    """
    now = datetime.now(timezone.utc)
    if "month" in error_code:
        if now.month == 12:
            return now.replace(
                year=now.year + 1, month=1, day=1,
                hour=0, minute=0, second=0, microsecond=0,
            )
        return now.replace(
            month=now.month + 1, day=1,
            hour=0, minute=0, second=0, microsecond=0,
        )
    if "day" in error_code:  # matches "daily_limit_exceeded" and similar
        return (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
    return now + timedelta(hours=24)


def _mark_quota_blocked(error_code: str) -> None:
    global _blocked_until_wall
    reset = _next_quota_reset_utc(error_code)
    _blocked_until_wall = reset.timestamp()
    print(
        f"[flight-slate] airlabs quota: {error_code}; backing off until {reset.isoformat()}",
        flush=True,
    )


def get_scheduled_arrival(
    callsign: str, *, dest_iata: str | None = None
) -> str | None:
    """Return the scheduled arrival as an ISO-8601 UTC string, or None.

    ``dest_iata`` (when known) filters AirLabs' schedule list to the matching
    route, which makes instance selection unambiguous in the common case.
    Hits AirLabs only on cache miss; safe to call from the request-path of
    a snapshot fetch (one call adds ~100-300 ms on miss).
    """
    if not callsign:
        return None
    cs = _normalize_callsign(callsign)
    if not cs or _TAIL_NUMBER_RE.match(cs):
        return None
    arr = (dest_iata or "").upper()
    key = (cs, arr)
    now = time.monotonic()

    cached = _known.get(key)
    if cached is not None:
        cached_at, value = cached
        if (now - cached_at) < _POSITIVE_TTL_S:
            return value
        _known.pop(key, None)
    neg_ts = _negative.get(key)
    if neg_ts is not None and (now - neg_ts) < _NEGATIVE_TTL_S:
        return None

    if _blocked_until_wall is not None and time.time() < _blocked_until_wall:
        return None

    api_key = os.environ.get("AIRLABS_API_KEY", "").strip()
    if not api_key:
        return None

    # ADSB callsigns are usually ICAO-format (3-letter airline prefix).
    # AirLabs returns null on flight_iata for those; flight_icao matches.
    param = "flight_icao" if _looks_icao(cs) else "flight_iata"
    url = (
        f"{_SCHEDULES_URL}?api_key={urllib.parse.quote(api_key)}"
        f"&{param}={urllib.parse.quote(cs)}"
    )
    if arr:
        url += f"&arr_iata={urllib.parse.quote(arr)}"
    request = urllib.request.Request(url, headers={"User-Agent": "flight-slate/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
        return None  # transient — don't poison the cache, retry next snapshot

    # Quota exhaustion arrives as a top-level ``error`` rather than a
    # transport-level failure, so we have to inspect the JSON body.
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            code = str(error.get("code") or "")
            if "limit_exceeded" in code:
                _mark_quota_blocked(code)
                return None

    payload = data.get("response") if isinstance(data, dict) else None
    items = payload if isinstance(payload, list) else []
    chosen = _select_instance([r for r in items if isinstance(r, dict)])
    if chosen is not None:
        iso = _arrival_to_iso_utc(chosen.get("arr_time_utc"))
        if iso is not None:
            _known[key] = (now, iso)
            return iso

    _negative[key] = now
    return None
