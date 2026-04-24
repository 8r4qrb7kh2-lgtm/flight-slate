"""Live flight data fetchers.

* ADSB.lol — positions, speed, altitude, aircraft type for everything within
  a radius of a point. Results are sorted closest first. Free, no auth.
* Flightradar24 API — origin/destination airport lookup by callsign. Requires
  ``FR24_API_KEY``. Returns IATA codes only; we join against the local
  OpenFlights airport database for coordinates and city names.

Even with FR24's authoritative data, we still apply the plausibility and
track-direction checks before trusting the route — defense in depth against
stale data, callsign reuse, and ambiguous matches.
"""

from __future__ import annotations

import functools
import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, replace
from typing import Any

from ui.flight import airports as airport_db


ADSB_LOL_URL = "https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{dist}"
FR24_FLIGHT_POSITIONS_URL = "https://fr24api.flightradar24.com/api/live/flight-positions/full"

DEFAULT_TIMEOUT_S = 8.0

ROUTE_PLAUSIBILITY_FIXED_NM = 40.0
ROUTE_PLAUSIBILITY_FRACTION = 0.10
# When the plane is broadcasting a track, reject routes whose bearing-to-destination
# differs by more than this. Catches stale-cache cases where the geometry happens to
# fit (e.g. plane in CLE accepted for an MCI→PHL route) but the plane isn't headed
# anywhere near the destination.
ROUTE_TRACK_TOLERANCE_DEG = 60.0


# Wholly-owned regional carriers that always operate for a single major.
# Maps operating airline ICAO → ticketed (true) airline ICAO.
# Multi-carrier regionals (RPA/SKW/GJS) are intentionally omitted — we can't
# reliably tell which major they're flying for from callsign alone.
TRUE_AIRLINE_OVERRIDES: dict[str, str] = {
    "EDV": "DAL",  # Endeavor Air → Delta Connection (wholly owned by Delta)
    "ENY": "AAL",  # Envoy Air → American Eagle (wholly owned by AA)
    "PDT": "AAL",  # Piedmont Airlines → American Eagle (wholly owned by AA)
    "JIA": "AAL",  # PSA Airlines → American Eagle (wholly owned by AA)
    "JZA": "ACA",  # Jazz Aviation → Air Canada Express
}

# Human-readable names paired with the overrides (for the airline_name field).
TRUE_AIRLINE_NAMES: dict[str, str] = {
    "DAL": "Delta Air Lines",
    "AAL": "American Airlines",
    "UAL": "United Airlines",
    "ACA": "Air Canada",
}


@dataclass(frozen=True)
class Region:
    """A viewing region defined by a center point, radius, and a view cone.

    The cone restricts visible aircraft to those within the window's field of
    view. Specified by center bearing (degrees clockwise from true north) and
    total horizontal field of view in degrees.
    """

    center_lat: float
    center_lon: float
    radius_nm: float
    view_bearing_deg: float = 180.0
    view_cone_deg: float = 360.0
    overhead_exempt_nm: float = 1.0
    # Only include aircraft at or below this altitude. None disables the filter.
    max_altitude_ft: float | None = None
    # Radius the radar widget scales to (separate from overall fetch radius).
    # Aircraft beyond this are dropped from the scope but stay in the snapshot.
    radar_radius_nm: float = 8.69  # 10 statute miles


@dataclass
class Flight:
    """A single flight's live state composed for hero display."""

    icao24: str
    callsign: str
    airline_icao: str | None
    airline_name: str | None
    flight_number: str | None
    aircraft_type: str | None
    registration: str | None
    origin_iata: str | None
    origin_name: str | None
    destination_iata: str | None
    destination_name: str | None
    ground_speed_kt: float | None
    altitude_ft: float | None
    vertical_rate_fpm: float | None
    track_deg: float | None
    latitude: float
    longitude: float
    distance_nm: float
    bearing_deg: float
    on_ground: bool
    route_verified: bool


@dataclass(frozen=True)
class AircraftPing:
    """Minimal state needed to place a plane on the radar."""

    icao24: str
    callsign: str | None
    latitude: float
    longitude: float
    distance_nm: float
    bearing_deg: float
    in_cone: bool
    track_deg: float | None = None
    ground_speed_kt: float | None = None
    # Previous radar positions (polar: bearing_deg, distance_nm), newest first.
    # Populated by `PingHistory` between fetches, empty on the first sighting.
    trail: tuple[tuple[float, float], ...] = ()


class PingHistory:
    """Per-aircraft ring buffer of recent radar positions.

    Maintains ``max_length`` prior observations per icao24 so the Radar widget
    can plot the actual path a plane has traveled, rather than synthesising a
    tick mark from its instantaneous heading. Entries for aircraft that leave
    the region quietly age out once they haven't been seen for
    ``stale_after`` consecutive updates.
    """

    def __init__(self, *, max_length: int = 2, stale_after: int = 12) -> None:
        self._max_length = max_length
        self._stale_after = stale_after
        self._trails: dict[str, list[tuple[float, float]]] = {}
        self._idle_count: dict[str, int] = {}

    def decorate(self, snapshot: "AirSnapshot") -> "AirSnapshot":
        """Attach per-ping trails drawn from history, then record new positions."""
        decorated = tuple(
            replace(ping, trail=tuple(self._trails.get(ping.icao24, ())))
            for ping in snapshot.pings
        )

        seen: set[str] = set()
        for ping in snapshot.pings:
            if not ping.icao24:
                continue
            seen.add(ping.icao24)
            trail = self._trails.setdefault(ping.icao24, [])
            trail.insert(0, (ping.bearing_deg, ping.distance_nm))
            del trail[self._max_length:]
            self._idle_count[ping.icao24] = 0

        for icao in list(self._idle_count.keys()):
            if icao in seen:
                continue
            self._idle_count[icao] += 1
            if self._idle_count[icao] > self._stale_after:
                self._idle_count.pop(icao, None)
                self._trails.pop(icao, None)

        return AirSnapshot(region=snapshot.region, selected=snapshot.selected, pings=decorated)


@dataclass
class AirSnapshot:
    """Everything the display needs in one frame: selected flight + radar pings."""

    region: Region
    selected: Flight | None = None
    pings: tuple[AircraftPing, ...] = field(default_factory=tuple)


def _http_get_json(
    url: str,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    headers = {"User-Agent": "flight-slate/0.1", "Accept": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        payload = response.read()
    return json.loads(payload.decode("utf-8"))


def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_nm = 3440.065
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius_nm * math.asin(min(1.0, math.sqrt(a)))


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    y = math.sin(dlambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    theta = math.degrees(math.atan2(y, x))
    return (theta + 360.0) % 360.0


def _angular_distance_deg(a: float, b: float) -> float:
    diff = abs((a - b) % 360.0)
    return diff if diff <= 180.0 else 360.0 - diff


def _in_view_cone(
    bearing_from_viewer: float,
    distance_nm: float,
    view_bearing_deg: float,
    view_cone_deg: float,
    overhead_exempt_nm: float,
) -> bool:
    if view_cone_deg >= 360.0:
        return True
    if distance_nm <= overhead_exempt_nm:
        return True
    return _angular_distance_deg(bearing_from_viewer, view_bearing_deg) <= view_cone_deg / 2.0


def _altitude_ft(entry: dict[str, Any]) -> float | None:
    """Return the aircraft's altitude in feet, preferring geometric over baro.

    ``alt_baro`` is ``"ground"`` when the aircraft is on the surface — treated
    as 0 ft. Returns ``None`` when no altitude is reported.
    """
    if entry.get("alt_baro") == "ground":
        return 0.0
    for key in ("alt_geom", "alt_baro"):
        value = entry.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _clean_callsign(raw: Any) -> str | None:
    if raw is None:
        return None
    callsign = str(raw).strip()
    return callsign or None


def _split_callsign(callsign: str) -> tuple[str | None, str | None]:
    head = callsign[:3].upper()
    tail = callsign[3:].strip()
    if head.isalpha():
        return head, tail or None
    return None, callsign


@functools.lru_cache(maxsize=512)
def _cached_fr24_route(callsign: str) -> tuple[str, ...] | None:
    """Flightradar24 callsign → route lookup.

    Hits the live flight-positions endpoint and pulls origin/destination
    IATA codes for the callsign currently airborne. FR24 returns codes only,
    so we join against the local OpenFlights airport database to supply
    coordinates (needed for the plausibility check) and city names (for the
    footer). Returns a 10-tuple matching the shape consumed by
    ``_apply_cached_route`` or ``None`` if no key is set / the lookup fails.
    """
    api_key = os.environ.get("FR24_API_KEY")
    if not api_key:
        return None
    url = f"{FR24_FLIGHT_POSITIONS_URL}?callsigns={urllib.parse.quote(callsign)}"
    try:
        data = _http_get_json(
            url,
            extra_headers={
                "Accept-Version": "v1",
                "Authorization": f"Bearer {api_key}",
            },
        )
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
        return None
    entries = data.get("data") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not entries:
        return None
    entry = entries[0]
    if not isinstance(entry, dict):
        return None
    dep_iata = str(entry.get("orig_iata") or "").strip().upper()
    arr_iata = str(entry.get("dest_iata") or "").strip().upper()
    if not dep_iata or not arr_iata:
        return None
    dep = airport_db.lookup(dep_iata)
    arr = airport_db.lookup(arr_iata)
    if dep is None or arr is None:
        # Can't plausibility-check or label without airport data — skip.
        return None
    airline_icao = str(entry.get("painted_as") or entry.get("operating_as") or "")
    return (
        airline_icao,
        "",  # FR24 live endpoint doesn't return airline display name
        dep_iata,
        dep.city,
        arr_iata,
        arr.city,
        f"{dep.latitude:.6f}",
        f"{dep.longitude:.6f}",
        f"{arr.latitude:.6f}",
        f"{arr.longitude:.6f}",
    )


def _route_is_plausible(
    flight_lat: float,
    flight_lon: float,
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    track_deg: float | None = None,
) -> bool:
    direct = _haversine_nm(origin_lat, origin_lon, dest_lat, dest_lon)
    if direct <= 0.0:
        return False
    via_flight = _haversine_nm(origin_lat, origin_lon, flight_lat, flight_lon) + _haversine_nm(
        flight_lat, flight_lon, dest_lat, dest_lon
    )
    allowed = direct * (1.0 + ROUTE_PLAUSIBILITY_FRACTION) + ROUTE_PLAUSIBILITY_FIXED_NM
    if via_flight > allowed:
        return False
    if track_deg is not None:
        bearing_to_dest = _bearing_deg(flight_lat, flight_lon, dest_lat, dest_lon)
        if _angular_distance_deg(track_deg, bearing_to_dest) > ROUTE_TRACK_TOLERANCE_DEG:
            return False
    return True


def _apply_cached_route(
    cached: tuple[str, ...],
    flight_lat: float,
    flight_lon: float,
    track_deg: float | None = None,
) -> tuple[str, str | None, str, str | None] | None:
    """Validate a cached route tuple against the current aircraft position.

    Returns ``(origin_iata, origin_name, destination_iata, destination_name)``
    when the route is present and plausible; ``None`` when fields are missing,
    coordinates don't parse, or the aircraft is clearly off-route (either by
    distance from the great circle or by track-direction mismatch).
    """
    (
        _airline_icao,
        _airline_name,
        o_iata,
        o_name,
        d_iata,
        d_name,
        o_lat_s,
        o_lon_s,
        d_lat_s,
        d_lon_s,
    ) = cached
    if not (o_iata and d_iata and o_lat_s and o_lon_s and d_lat_s and d_lon_s):
        return None
    try:
        o_lat = float(o_lat_s)
        o_lon = float(o_lon_s)
        d_lat = float(d_lat_s)
        d_lon = float(d_lon_s)
    except ValueError:
        return None
    if not _route_is_plausible(flight_lat, flight_lon, o_lat, o_lon, d_lat, d_lon, track_deg):
        return None
    return (o_iata, o_name or None, d_iata, d_name or None)


def _apply_true_airline(airline_icao: str | None, airline_name: str | None) -> tuple[str | None, str | None]:
    if not airline_icao:
        return airline_icao, airline_name
    override = TRUE_AIRLINE_OVERRIDES.get(airline_icao.upper())
    if override is None:
        return airline_icao, airline_name
    return override, TRUE_AIRLINE_NAMES.get(override) or airline_name


def _build_flight(
    ac: dict[str, Any],
    lat: float,
    lon: float,
    distance_nm: float,
    bearing_from_viewer_deg: float,
    enrich_route: bool,
) -> Flight | None:
    callsign = _clean_callsign(ac.get("flight"))
    if not callsign:
        return None

    airline_icao, flight_number = _split_callsign(callsign)
    airline_name: str | None = None
    origin_iata = origin_name = destination_iata = destination_name = None
    route_verified = False

    # Parsed early so the plausibility check can compare it to bearing-to-destination.
    track_raw = ac.get("track")
    track_deg = float(track_raw) if isinstance(track_raw, (int, float)) else None

    if enrich_route:
        cached = _cached_fr24_route(callsign)
        if cached is not None:
            if cached[0] and not airline_icao:
                airline_icao = cached[0]
            resolved = _apply_cached_route(cached, lat, lon, track_deg)
            if resolved is not None:
                origin_iata, origin_name, destination_iata, destination_name = resolved
                route_verified = True

    airline_icao, airline_name = _apply_true_airline(airline_icao, airline_name)

    altitude_raw = ac.get("alt_geom")
    if altitude_raw in (None, "ground"):
        altitude_raw = ac.get("alt_baro")
    altitude_ft = float(altitude_raw) if isinstance(altitude_raw, (int, float)) else None

    gs_raw = ac.get("gs")
    ground_speed_kt = float(gs_raw) if isinstance(gs_raw, (int, float)) else None

    vs_raw = ac.get("baro_rate")
    if vs_raw is None:
        vs_raw = ac.get("geom_rate")
    vertical_rate_fpm = float(vs_raw) if isinstance(vs_raw, (int, float)) else None

    on_ground = ac.get("alt_baro") == "ground"

    return Flight(
        icao24=str(ac.get("hex", "")).lower(),
        callsign=callsign,
        airline_icao=airline_icao,
        airline_name=airline_name,
        flight_number=flight_number,
        aircraft_type=(ac.get("t") or None),
        registration=(ac.get("r") or None),
        origin_iata=origin_iata or None,
        origin_name=origin_name,
        destination_iata=destination_iata or None,
        destination_name=destination_name,
        ground_speed_kt=ground_speed_kt,
        altitude_ft=altitude_ft,
        vertical_rate_fpm=vertical_rate_fpm,
        track_deg=track_deg,
        latitude=lat,
        longitude=lon,
        distance_nm=distance_nm,
        bearing_deg=bearing_from_viewer_deg,
        on_ground=on_ground,
        route_verified=route_verified,
    )


def fetch_air_snapshot(
    region: Region,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    enrich_route: bool = True,
) -> AirSnapshot:
    """Return a snapshot of airspace: all pings in radius, plus the closest in-cone flight."""

    url = ADSB_LOL_URL.format(
        lat=f"{region.center_lat:.6f}",
        lon=f"{region.center_lon:.6f}",
        dist=max(1, int(round(region.radius_nm))),
    )
    data = _http_get_json(url, timeout_s=timeout_s)

    aircraft = data.get("ac") if isinstance(data, dict) else None
    if not isinstance(aircraft, list):
        return AirSnapshot(region=region)

    pings: list[AircraftPing] = []
    # Track cone candidates separately so we can pick the closest in-cone plane.
    cone_candidates: list[tuple[float, dict[str, Any], float, float, float]] = []

    for entry in aircraft:
        if not isinstance(entry, dict):
            continue
        lat_raw = entry.get("lat")
        lon_raw = entry.get("lon")
        if not isinstance(lat_raw, (int, float)) or not isinstance(lon_raw, (int, float)):
            continue
        lat = float(lat_raw)
        lon = float(lon_raw)

        dst_raw = entry.get("dst")
        distance_nm = (
            float(dst_raw)
            if isinstance(dst_raw, (int, float))
            else _haversine_nm(region.center_lat, region.center_lon, lat, lon)
        )
        if distance_nm > region.radius_nm:
            # Hard cap on radius, even if the feed returned a looser result.
            continue

        if region.max_altitude_ft is not None:
            altitude_ft = _altitude_ft(entry)
            # If we know the altitude and it exceeds the cap, drop the aircraft.
            # A None altitude (e.g. no mode-C) is kept so we don't lose pings.
            if altitude_ft is not None and altitude_ft > region.max_altitude_ft:
                continue

        bearing = _bearing_deg(region.center_lat, region.center_lon, lat, lon)
        in_cone = _in_view_cone(
            bearing_from_viewer=bearing,
            distance_nm=distance_nm,
            view_bearing_deg=region.view_bearing_deg,
            view_cone_deg=region.view_cone_deg,
            overhead_exempt_nm=region.overhead_exempt_nm,
        )

        track_raw = entry.get("track")
        gs_raw = entry.get("gs")
        pings.append(
            AircraftPing(
                icao24=str(entry.get("hex", "")).lower(),
                callsign=_clean_callsign(entry.get("flight")),
                latitude=lat,
                longitude=lon,
                distance_nm=distance_nm,
                bearing_deg=bearing,
                in_cone=in_cone,
                track_deg=float(track_raw) if isinstance(track_raw, (int, float)) else None,
                ground_speed_kt=float(gs_raw) if isinstance(gs_raw, (int, float)) else None,
            )
        )

        if in_cone:
            cone_candidates.append((distance_nm, entry, lat, lon, bearing))

    cone_candidates.sort(key=lambda row: row[0])
    selected: Flight | None = None
    for distance_nm, entry, lat, lon, bearing in cone_candidates:
        # Plane info is only shown when the aircraft is inside the radar's
        # scope — i.e. close enough to be realistically visible from the
        # window. Anything further is tracked in the snapshot (so it can still
        # influence peripheral UI later) but doesn't get a hero card.
        if distance_nm > region.radar_radius_nm:
            break
        flight = _build_flight(
            entry,
            lat=lat,
            lon=lon,
            distance_nm=distance_nm,
            bearing_from_viewer_deg=bearing,
            enrich_route=enrich_route,
        )
        if flight is not None:
            selected = flight
            break

    return AirSnapshot(region=region, selected=selected, pings=tuple(pings))


def fetch_closest_flight(
    region: Region,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    enrich_route: bool = True,
) -> Flight | None:
    """Backwards-compatible helper — returns just the selected flight."""
    return fetch_air_snapshot(region, timeout_s=timeout_s, enrich_route=enrich_route).selected
