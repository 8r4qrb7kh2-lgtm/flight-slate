"""Calendar event cache for the idle (no-flight) display.

Module-level singleton. A background executor periodically pulls an
iCalendar (.ics) feed, expands recurring events, and caches upcoming
occurrences. The display calls ``next_event()`` each frame; the cache
refreshes itself in the background when stale.

Configure the feed via ``configure(ics_url)``. Passing ``None`` (or not
calling configure) leaves the cache disabled — ``next_event()`` returns
``None`` and callers should fall back to whatever they showed before.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

try:
    import icalendar  # type: ignore[import-not-found]
    import recurring_ical_events  # type: ignore[import-not-found]
except ImportError:
    icalendar = None  # type: ignore[assignment]
    recurring_ical_events = None  # type: ignore[assignment]


_REFRESH_S = 600.0          # 10 min — calendars don't change minute-to-minute
_RETRY_AFTER_FAIL_S = 90.0
_FETCH_HORIZON = timedelta(hours=48)  # cache 2x the lookahead so stale-but-valid data still works
_LOOKAHEAD = timedelta(hours=24)


@dataclass(frozen=True)
class UpcomingEvent:
    title: str
    start: datetime  # timezone-aware
    end: datetime    # timezone-aware


_ics_urls: tuple[str, ...] = ()
_executor: ThreadPoolExecutor | None = None
_cached: list[UpcomingEvent] | None = None
_next_attempt: float = 0.0
_pending: Future[list[UpcomingEvent] | None] | None = None
_warned_missing_deps: bool = False


def configure(ics_urls: "str | list[str] | tuple[str, ...] | None") -> None:
    """Set one or more ICS feed URLs and spin up the background fetch executor.

    Pass ``None``, an empty string, or an empty list to leave the cache
    disabled. Multiple URLs are fetched sequentially each refresh and their
    events are merged into a single sorted timeline.
    """
    global _ics_urls, _executor, _warned_missing_deps
    if not ics_urls:
        _ics_urls = ()
        return
    if isinstance(ics_urls, str):
        normalized = (ics_urls,)
    else:
        normalized = tuple(u for u in ics_urls if u)
    if not normalized:
        _ics_urls = ()
        return
    if icalendar is None or recurring_ical_events is None:
        if not _warned_missing_deps:
            print(
                "[flight-slate] events: icalendar/recurring-ical-events not installed; "
                "calendar footer disabled (run: pip install -r requirements.txt)"
            )
            _warned_missing_deps = True
        _ics_urls = ()
        return
    _ics_urls = normalized
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="events")


def _ensure_aware(value: datetime) -> datetime:
    """Treat naive datetimes as UTC. Most ICS feeds carry tzinfo via VTIMEZONE
    blocks, but a few (notably some basic.ics exports) drop it on floating times."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _fetch_events() -> list[UpcomingEvent] | None:
    urls = _ics_urls
    if not urls or icalendar is None or recurring_ical_events is None:
        return None

    now = datetime.now(timezone.utc)
    horizon_end = now + _FETCH_HORIZON
    out: list[UpcomingEvent] = []
    any_succeeded = False

    for url in urls:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "flight-slate/0.1"})
            with urllib.request.urlopen(request, timeout=15.0) as response:
                payload = response.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
            continue

        try:
            cal = icalendar.Calendar.from_ical(payload)
            occurrences = recurring_ical_events.of(cal).between(now, horizon_end)
        except Exception:
            continue

        any_succeeded = True
        for ev in occurrences:
            if str(ev.get("STATUS", "")).upper() == "CANCELLED":
                continue
            dt_start = ev.get("DTSTART")
            if dt_start is None:
                continue
            start_raw = dt_start.dt
            # Skip all-day events: a 12am "Vacation" doesn't read well as a countdown.
            if not isinstance(start_raw, datetime) and isinstance(start_raw, date):
                continue
            title = str(ev.get("SUMMARY", "")).strip() or "(untitled)"
            start = _ensure_aware(start_raw)
            dt_end = ev.get("DTEND")
            end_raw = dt_end.dt if dt_end is not None else None
            if isinstance(end_raw, datetime):
                end = _ensure_aware(end_raw)
            else:
                end = start + timedelta(hours=1)
            out.append(UpcomingEvent(title=title, start=start, end=end))

    if not any_succeeded:
        return None  # All feeds failed — retry sooner. A partial succeed returns whatever we got.

    out.sort(key=lambda e: e.start)
    return out


def _refresh_if_stale() -> None:
    global _cached, _next_attempt, _pending
    if not _ics_urls or _executor is None:
        return

    if _pending is not None and _pending.done():
        pending = _pending
        _pending = None
        try:
            result = pending.result()
        except Exception:
            result = None
        if result is not None:
            _cached = result
            _next_attempt = time.monotonic() + _REFRESH_S
        else:
            _next_attempt = time.monotonic() + _RETRY_AFTER_FAIL_S

    now_mono = time.monotonic()
    if _pending is None and now_mono >= _next_attempt:
        _next_attempt = now_mono + _RETRY_AFTER_FAIL_S  # tentative; success bumps to full refresh
        _pending = _executor.submit(_fetch_events)


def next_event() -> UpcomingEvent | None:
    """Return the next event ending after now within the lookahead window.

    An event currently in progress (start ≤ now < end) is returned — callers
    can check that range to render it as "happening now". Returns ``None``
    when the cache is empty, the feed isn't configured, or nothing is scheduled
    in the next 24 hours.
    """
    _refresh_if_stale()
    if _cached is None:
        return None
    now = datetime.now(timezone.utc)
    horizon = now + _LOOKAHEAD
    for ev in _cached:
        if ev.end <= now:
            continue
        if ev.start > horizon:
            return None
        return ev
    return None
