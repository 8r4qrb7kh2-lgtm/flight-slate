"""AirLabs flight-schedule lookup for delay/early calculations.

Used to obtain *scheduled* arrival times that FR24's API doesn't return.
We compare AirLabs' ``arr_time_utc`` (scheduled) against FR24's ``eta``
(current estimate) to compute "X min late / early" for the displayed
flight.

The free AirLabs tier is 1,000 calls/month, so caching is aggressive:

* Positive cache: per callsign, valid for 20 hours. A given callsign's
  schedule for the day doesn't change once filed; reusing the same
  callsign on a future day with a different schedule will refresh after
  the TTL expires.
* Negative cache: per callsign, 1 hour. Skip non-commercial / unscheduled
  callsigns (private aircraft, military) without burning monthly budget.
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
from typing import Any


_FLIGHT_URL = "https://airlabs.co/api/v9/flight"
_TIMEOUT_S = 8.0
_POSITIVE_TTL_S = 20 * 3600.0
_NEGATIVE_TTL_S = 3600.0
# Same-day callsign reuse (e.g. Republic running DL5674 BOS-CLE twice in one
# day) sometimes makes AirLabs return the wrong instance — a record whose
# departure is hours in the future, or whose arrival was hours ago. The slate
# only looks up airborne flights, so anything outside this window around "now"
# is a different instance and should be skipped.
_INSTANCE_WINDOW_S = 30 * 60.0
# Short negative TTL for instance mismatches so we recover quickly when AirLabs
# catches up, without burning the monthly quota re-querying every snapshot.
_MISMATCH_TTL_S = 5 * 60.0

# Callsign shaped like a tail registration (N + digits + optional letters).
# AirLabs doesn't carry schedules for these — skip entirely so we don't waste
# the monthly quota negative-caching every passing GA/medical flight.
_TAIL_NUMBER_RE = re.compile(r"^N\d+[A-Z]*$")


# callsign → (cached_at, scheduled_arrival_utc_iso)
_known: dict[str, tuple[float, str]] = {}
_negative: dict[str, float] = {}


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


def _is_current_instance(payload: dict[str, Any]) -> bool:
    """True iff the AirLabs record describes a flight active around now.

    AirLabs sometimes returns the next or prior instance of a reused callsign
    (e.g. a regional running the same flight number twice on the same day).
    Those records put departure hours in the future or arrival hours in the
    past, which yields a wildly wrong schedule-delta. The slate only ever
    looks up airborne flights, so any record whose dep/arr timestamps don't
    bracket "now" is the wrong instance.
    """
    now = time.time()
    dep_ts = payload.get("dep_time_ts")
    if isinstance(dep_ts, (int, float)) and dep_ts > now + _INSTANCE_WINDOW_S:
        return False
    arr_ts = payload.get("arr_time_ts")
    if isinstance(arr_ts, (int, float)) and arr_ts < now - _INSTANCE_WINDOW_S:
        return False
    return True


def get_scheduled_arrival(callsign: str) -> str | None:
    """Return the scheduled arrival as an ISO-8601 UTC string, or None.

    Hits AirLabs only on cache miss. Safe to call from the request-path of
    a snapshot fetch: a single call adds ~100-300 ms latency on miss.
    """
    if not callsign:
        return None
    cs = _normalize_callsign(callsign)
    if not cs or _TAIL_NUMBER_RE.match(cs):
        return None
    now = time.monotonic()

    cached = _known.get(cs)
    if cached is not None:
        cached_at, value = cached
        if (now - cached_at) < _POSITIVE_TTL_S:
            return value
        _known.pop(cs, None)
    neg_ts = _negative.get(cs)
    if neg_ts is not None and (now - neg_ts) < _NEGATIVE_TTL_S:
        return None

    api_key = os.environ.get("AIRLABS_API_KEY", "").strip()
    if not api_key:
        return None

    # ADSB callsigns are usually ICAO-format (3-letter airline prefix).
    # AirLabs returns null on flight_iata for those; flight_icao matches.
    param = "flight_icao" if _looks_icao(cs) else "flight_iata"
    url = (
        f"{_FLIGHT_URL}?api_key={urllib.parse.quote(api_key)}"
        f"&{param}={urllib.parse.quote(cs)}"
    )
    request = urllib.request.Request(url, headers={"User-Agent": "flight-slate/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
        return None  # transient — don't poison the cache, retry next snapshot

    payload = data.get("response") if isinstance(data, dict) else None
    if isinstance(payload, dict):
        if not _is_current_instance(payload):
            # Short negative-cache so we re-check soon when AirLabs updates.
            _negative[cs] = now - (_NEGATIVE_TTL_S - _MISMATCH_TTL_S)
            return None
        iso = _arrival_to_iso_utc(payload.get("arr_time_utc"))
        if iso is not None:
            _known[cs] = (now, iso)
            return iso

    _negative[cs] = now
    return None
