"""Tests for the calendar event cache (``ui/flight/events.py``).

The ``icalendar`` / ``recurring_ical_events`` deps are optional and may be
absent in CI, so the ICS stack is stubbed here. The logic under test —
per-feed retention, the lookahead window, and the retry-cadence signal — is
independent of real ICS parsing.
"""
from __future__ import annotations

import types
import urllib.request
from datetime import datetime, timedelta, timezone

import pytest

from ui.flight import events
from ui.flight.events import UpcomingEvent


def _dt(value):
    return types.SimpleNamespace(dt=value)


def _vevent(summary, start, end, status=""):
    return {"SUMMARY": summary, "DTSTART": _dt(start), "DTEND": _dt(end), "STATUS": status}


@pytest.fixture
def feeds(monkeypatch):
    """Drive the stubbed ICS stack from in-memory tables.

    Returns a controller exposing:
      ``served[url] = [vevent, ...]`` — what a feed yields when fetched
      ``failing: set[url]``           — URLs whose fetch raises (e.g. HTTP 429)
    """
    served: dict[str, list[dict]] = {}
    failing: set[str] = set()

    class _Resp:
        def __init__(self, data):
            self._data = data

        def read(self):
            return self._data

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout=None):
        url = request.full_url
        if url in failing:
            raise OSError("simulated rate limit / network error")
        return _Resp(url.encode())

    class _Cal:
        @staticmethod
        def from_ical(payload):
            return payload.decode()

    class _Recur:
        def __init__(self, cal):
            self._cal = cal

        def between(self, start, end):
            return list(served.get(self._cal, []))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(events, "icalendar", types.SimpleNamespace(Calendar=_Cal))
    monkeypatch.setattr(events, "recurring_ical_events", types.SimpleNamespace(of=lambda cal: _Recur(cal)))
    monkeypatch.setattr(events, "_cached", None)
    monkeypatch.setattr(events, "_cached_by_url", {})
    monkeypatch.setattr(events, "_ics_urls", ())
    monkeypatch.setattr(events, "_executor", None)
    monkeypatch.setattr(events, "_next_attempt", 0.0)

    return types.SimpleNamespace(served=served, failing=failing)


def test_flaky_feed_retains_last_events(feeds):
    """A feed that fails one cycle must not vanish from the merged timeline."""
    a, b = "http://a", "http://b"
    events._ics_urls = (a, b)
    soon = datetime.now(timezone.utc) + timedelta(days=2)
    feeds.served[a] = [_vevent("A-shift", soon, soon + timedelta(hours=2))]
    feeds.served[b] = [_vevent("B-shift", soon, soon + timedelta(hours=2))]

    merged, fresh = events._fetch_events()
    assert fresh is True
    assert {e.title for e in merged} == {"A-shift", "B-shift"}

    # B now rate-limits (HTTP 429). Its events must be retained, not dropped.
    feeds.failing.add(b)
    merged, fresh = events._fetch_events()
    assert fresh is True  # A still refreshed this cycle
    assert {e.title for e in merged} == {"A-shift", "B-shift"}

    # B recovers with an updated event; the cache reflects it.
    feeds.failing.discard(b)
    feeds.served[b] = [_vevent("B-shift-2", soon, soon + timedelta(hours=2))]
    merged, fresh = events._fetch_events()
    assert {e.title for e in merged} == {"A-shift", "B-shift-2"}


def test_all_feeds_failing_signals_retry_but_retains(feeds):
    """When every feed fails, signal a fast retry yet keep showing cached events."""
    a = "http://a"
    events._ics_urls = (a,)
    soon = datetime.now(timezone.utc) + timedelta(days=1)
    feeds.served[a] = [_vevent("A-shift", soon, soon + timedelta(hours=1))]
    events._fetch_events()  # prime the cache

    feeds.failing.add(a)
    merged, fresh = events._fetch_events()
    assert fresh is False  # nothing refreshed -> caller should retry sooner
    assert {e.title for e in merged} == {"A-shift"}  # but still displayed


def test_dropped_feed_is_forgotten(feeds):
    """Removing a URL from config drops its slice on the next fetch."""
    a, b = "http://a", "http://b"
    events._ics_urls = (a, b)
    soon = datetime.now(timezone.utc) + timedelta(days=2)
    feeds.served[a] = [_vevent("A", soon, soon + timedelta(hours=1))]
    feeds.served[b] = [_vevent("B", soon, soon + timedelta(hours=1))]
    events._fetch_events()

    events._ics_urls = (a,)  # B unsubscribed
    merged, _ = events._fetch_events()
    assert {e.title for e in merged} == {"A"}


def test_all_day_and_cancelled_events_skipped(feeds):
    """All-day (date, not datetime) and CANCELLED occurrences are filtered out."""
    a = "http://a"
    events._ics_urls = (a,)
    soon = datetime.now(timezone.utc) + timedelta(days=2)
    feeds.served[a] = [
        _vevent("timed", soon, soon + timedelta(hours=1)),
        _vevent("cancelled", soon, soon + timedelta(hours=1), status="CANCELLED"),
        _vevent("all-day", soon.date(), soon.date() + timedelta(days=1)),
    ]
    merged, _ = events._fetch_events()
    assert {e.title for e in merged} == {"timed"}


def test_next_event_uses_seven_day_lookahead(feeds):
    """Events within a week surface; those beyond it do not."""
    now = datetime.now(timezone.utc)
    within = UpcomingEvent("within-week", now + timedelta(days=3), now + timedelta(days=3, hours=1))
    beyond = UpcomingEvent("beyond-week", now + timedelta(days=10), now + timedelta(days=10, hours=1))

    events._cached = [within, beyond]
    assert events.next_event() is within  # nearest within 7 days

    events._cached = [beyond]
    assert events.next_event() is None  # 10 days out is past the window


def test_next_event_returns_in_progress(feeds):
    """An event that started but hasn't ended is returned (rendered as 'now')."""
    now = datetime.now(timezone.utc)
    live = UpcomingEvent("live", now - timedelta(minutes=10), now + timedelta(hours=1))
    events._cached = [live]
    assert events.next_event() is live
