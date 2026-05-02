"""Hero layout for the closest live flight.

Target display: 128x64. Layout:

    ┌─────────────────────────┬──────────────────┐
    │ LOGO │ CALLSIGN          │                 │
    │ 32x32│ ORIG > DEST       │     RADAR       │
    │      │ AIRCRAFT · REG    │    (30 NM)      │
    ├──────┴───────────────────┤                 │
    │ S 280 │ A 35K │ V +12    │                 │
    ├──────────────────────────┴─────────────────┤
    │ ◄──────── POSITION BAR ◄──────────────►    │
    └────────────────────────────────────────────┘
"""

from __future__ import annotations

import functools
import math
import random
import time
from dataclasses import dataclass
from pathlib import Path

from ui.core.canvas import PixelCanvas, Rect
from ui.core.colors import Color, colors
from ui.core.image_asset import ImageFrame, load_png_image_frame
from ui.core.widgets import Column, Image, Panel, Row, Text, Widget
from ui.fonts import FONT_3X5, FONT_4X6, FONT_5X7
from ui.flight import events, weather
from ui.flight.aircraft_types import aircraft_long_name
from ui.flight.airlines import load_airline_logo, resolve_airline_from_callsign
from ui.flight.events import UpcomingEvent
from ui.flight.fun_facts import ANIMAL_FUN_FACTS
from ui.flight.api import AirSnapshot, Flight
from ui.flight.maps import default_fetcher
from ui.flight.route_map import RouteMap


ICON_DIR = Path(__file__).resolve().parents[2] / "assets" / "icons"
ICON_SPEED = "speed.png"
ICON_ALTITUDE = "altitude.png"
ICON_VERTICAL = "vertical-speed.png"

# Drop the city name from the dep/arr footer when it matches HOME_CITY — the
# board lives in Cleveland, so "Cleveland (CLE)" / "Cleveland (BKL)" is just
# noise. Other cities keep the full "City (CODE)" form.
HOME_CITY = "Cleveland"

DISPLAY_WIDTH = 128
DISPLAY_HEIGHT = 64
LOGO_SIZE = 32
DIVIDER_THICKNESS = 1
POSITION_BAR_HEIGHT = 11
TOP_HEIGHT = DISPLAY_HEIGHT - POSITION_BAR_HEIGHT - DIVIDER_THICKNESS  # 52
RADAR_AREA_WIDTH = 40
LEFT_AREA_WIDTH = DISPLAY_WIDTH - RADAR_AREA_WIDTH - DIVIDER_THICKNESS  # 87
HERO_ROW_HEIGHT = LOGO_SIZE  # 32
STATS_ROW_HEIGHT = TOP_HEIGHT - HERO_ROW_HEIGHT - DIVIDER_THICKNESS  # 19
DETAILS_WIDTH = LEFT_AREA_WIDTH - LOGO_SIZE - DIVIDER_THICKNESS  # 54

# Stats row is a 2x2 grid: two rows of two cells each, with FONT_5X7 values.
STAT_CELL_W_LEFT = (LEFT_AREA_WIDTH - DIVIDER_THICKNESS) // 2  # 43
STAT_CELL_W_RIGHT = LEFT_AREA_WIDTH - DIVIDER_THICKNESS - STAT_CELL_W_LEFT  # 43
STAT_SUBROW_H = (STATS_ROW_HEIGHT - DIVIDER_THICKNESS) // 2  # 9

COLOR_LABEL = colors.DIM_WHITE
COLOR_VALUE = colors.WHITE
COLOR_ACCENT: Color = (120, 200, 255)
COLOR_STATUS_WARN: Color = (240, 180, 80)
COLOR_DIVIDER: Color = (35, 70, 95)
COLOR_RADAR_RING: Color = (45, 95, 125)
COLOR_RADAR_CENTER: Color = (80, 150, 190)
COLOR_RADAR_CONE: Color = (30, 75, 100)
COLOR_RADAR_HEAD_NORMAL: Color = (80, 220, 90)
COLOR_RADAR_HEAD_SELECTED: Color = (255, 60, 60)
COLOR_RADAR_TAIL_NEAR: Color = (140, 150, 165)
COLOR_RADAR_TAIL_FAR: Color = (65, 75, 90)
COLOR_BAR_BG: Color = (18, 32, 44)
COLOR_BAR_TICK: Color = (90, 130, 160)
COLOR_RADAR_SWEEP: Color = (60, 200, 90)

SWEEP_PERIOD_S = 7.0
SWEEP_TRAIL_STEPS: tuple[tuple[int, float], ...] = ()

SPEED_COLOR_LOW: Color = (50, 210, 70)    # 100 kt — green
SPEED_COLOR_MID: Color = (225, 200, 35)   # midpoint — yellow
SPEED_COLOR_HIGH: Color = (230, 55, 45)   # 600 kt — red
SPEED_COLOR_UNKNOWN: Color = (140, 140, 140)
SPEED_GREEN_KT = 100.0
SPEED_RED_KT = 600.0


@functools.lru_cache(maxsize=8)
def _load_icon(name: str) -> ImageFrame | None:
    path = ICON_DIR / name
    if not path.exists():
        return None
    try:
        return load_png_image_frame(path)
    except Exception:
        return None


def _divider() -> Widget:
    return Panel(padding=0, bg=COLOR_DIVIDER, border=None, child=None)  # type: ignore[arg-type]


def _spacer(color: Color = colors.BLACK) -> Widget:
    return Panel(padding=0, bg=color, border=None, child=None)  # type: ignore[arg-type]


def _lerp_color(a: Color, b: Color, t: float) -> Color:
    t = max(0.0, min(1.0, t))
    return (
        int(round(a[0] + (b[0] - a[0]) * t)),
        int(round(a[1] + (b[1] - a[1]) * t)),
        int(round(a[2] + (b[2] - a[2]) * t)),
    )


def _speed_color(speed_kt: float | None) -> Color:
    """Linear 100 → 600 kt green → yellow → red gradient."""
    if speed_kt is None:
        return SPEED_COLOR_UNKNOWN
    t = (speed_kt - SPEED_GREEN_KT) / (SPEED_RED_KT - SPEED_GREEN_KT)
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        return _lerp_color(SPEED_COLOR_LOW, SPEED_COLOR_MID, t * 2)
    return _lerp_color(SPEED_COLOR_MID, SPEED_COLOR_HIGH, (t - 0.5) * 2)


def _icon_or_letter(icon_name: str, fallback_letter: str, color: Color) -> Widget:
    frame = _load_icon(icon_name)
    if frame is not None:
        return Image(frame=frame, fit="original")
    return Text(
        text=fallback_letter,
        font=FONT_4X6,
        align="center",
        overflow="clip",
        color=color,
    )


def _format_altitude(altitude_ft: float | None) -> str:
    if altitude_ft is None:
        return "--"
    value = int(round(altitude_ft))
    if value >= 10_000:
        return f"{value // 1000}K"
    if value >= 1000:
        return f"{value / 1000:.1f}K"
    return f"{max(0, value)}"


def _format_ground_speed(speed_kt: float | None) -> str:
    if speed_kt is None:
        return "--"
    return f"{int(round(speed_kt))}"


def _format_vertical_rate(vs_fpm: float | None) -> str:
    if vs_fpm is None:
        return "--"
    hundreds = int(round(vs_fpm / 100.0))
    if hundreds == 0:
        return "0"
    sign = "+" if hundreds > 0 else "-"
    return f"{sign}{abs(hundreds)}"


_COMPASS_POINTS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def _compass_letter(bearing_deg: float | None) -> str:
    if bearing_deg is None:
        return ""
    index = int((bearing_deg + 22.5) // 45.0) % 8
    return _COMPASS_POINTS[index]


def _format_distance(distance_nm: float | None) -> str:
    if distance_nm is None:
        return ""
    if distance_nm < 10:
        return f"{distance_nm:.1f}NM"
    return f"{int(round(distance_nm))}NM"


def _route_text(flight: Flight) -> str:
    compass = _compass_letter(flight.bearing_deg)
    distance = _format_distance(flight.distance_nm)
    parts = [p for p in (compass, distance) if p]
    return " ".join(parts) if parts else "AIRBORNE"


def _aircraft_type_display(flight: Flight) -> str:
    """Friendly aircraft type name, falling back to the raw code/reg if needed.

    Replaces the call-sign line in the details column — the aircraft type
    is what most viewers actually want to know ("oh, it's a 737-800")
    once the airline logo has already told them who's flying it.
    """
    long_name = aircraft_long_name(flight.aircraft_type)
    if long_name:
        return long_name
    reg = (flight.registration or "").strip()
    if reg:
        return reg
    return flight.icao24.upper() or "AIRCRAFT"


def _flight_id_line(flight: Flight) -> str:
    """Airline call sign in 'XXX 1234' form, falling back to the raw callsign.

    Returns the ICAO airline prefix joined to the flight number when both
    are known (the boarding-pass-style identifier), the bare callsign as
    received from ADS-B otherwise, and the hex ICAO24 if even that is
    absent. This is the bottom-line identifier — registration is dropped.
    """
    airline = (flight.airline_icao or "").strip()
    number = (flight.flight_number or "").strip()
    if airline and number:
        return f"{airline} {number}"
    callsign = (flight.callsign or "").strip()
    if callsign:
        return callsign
    return (flight.icao24 or "").upper()


def _build_stat_cell(
    label: str,
    value: str,
    cell_w: int,
    *,
    label_color: Color = COLOR_ACCENT,
    value_color: Color = COLOR_VALUE,
) -> Widget:
    """One stat in the 2x2 grid: FONT_5X7 letter prefix + value, centered.

    9-tall cell vertically holds a 7-tall FONT_5X7 line with 1 px padding
    top and bottom.
    """
    label_w, _ = FONT_5X7.measure(label)
    value_w, _ = FONT_5X7.measure(value)
    gap = 2
    content_w = min(cell_w, label_w + gap + value_w)
    left_pad = max(0, (cell_w - content_w) // 2)
    right_pad = max(0, cell_w - content_w - left_pad)

    content = Row(
        gap=gap,
        sizes=[label_w, value_w],
        children=[
            Text(text=label, font=FONT_5X7, align="left", overflow="clip", color=label_color),
            Text(text=value, font=FONT_5X7, align="left", overflow="clip", color=value_color),
        ],
    )
    # sizes must sum to cell_w (Row treats them as proportions otherwise).
    centered = Row(
        gap=0,
        sizes=[left_pad, content_w, right_pad],
        children=[_spacer(), content, _spacer()],
    )
    return Column(
        gap=0,
        sizes=[1, 7, 1],
        children=[_spacer(), centered, _spacer()],
    )


_DELAY_RED: Color = (230, 70, 60)
_DELAY_GREEN: Color = (70, 220, 90)


def _format_schedule_delta(flight: Flight) -> tuple[str, str, Color]:
    """Return (label, value, color) for the schedule-delta cell.

    Label is "L" when late, "E" when early, "" when on-time or unknown.
    Magnitude in minutes only — color encodes late/early direction.
    """
    eta_dt = _parse_iso_utc(flight.eta_utc)
    sched_dt = _parse_iso_utc(flight.scheduled_arrival_utc)
    if eta_dt is None or sched_dt is None:
        return "", "--", COLOR_LABEL
    delta_min = round((eta_dt - sched_dt).total_seconds() / 60.0)
    if delta_min > 0:
        return "L", f"{delta_min}", _DELAY_RED
    if delta_min < 0:
        return "E", f"{abs(delta_min)}", _DELAY_GREEN
    return "", "0", COLOR_VALUE  # on time


def _parse_iso_utc(value: str | None) -> "datetime | None":
    """Parse 'YYYY-MM-DDTHH:MM:SSZ' to a UTC-aware datetime; None on failure."""
    if not value:
        return None
    from datetime import datetime, timezone
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _build_value_cell(value: str, color: Color, cell_w: int) -> Widget:
    """Single value, no label, centered horizontally and vertically in a 9-tall cell."""
    value_w = min(cell_w, FONT_5X7.measure(value)[0])
    left_pad = max(0, (cell_w - value_w) // 2)
    right_pad = max(0, cell_w - value_w - left_pad)
    centered = Row(
        gap=0,
        sizes=[left_pad, value_w, right_pad],
        children=[
            _spacer(),
            Text(text=value, font=FONT_5X7, align="left", overflow="clip", color=color),
            _spacer(),
        ],
    )
    return Column(
        gap=0,
        sizes=[1, 7, 1],
        children=[_spacer(), centered, _spacer()],
    )


def _build_stats_row(flight: Flight) -> Widget:
    delta_label, delta_value, delta_color = _format_schedule_delta(flight)
    if delta_label:
        delta_cell = _build_stat_cell(
            delta_label, delta_value, STAT_CELL_W_RIGHT, value_color=delta_color
        )
    else:
        delta_cell = _build_value_cell(delta_value, delta_color, STAT_CELL_W_RIGHT)

    def _subrow(left: Widget, right: Widget) -> Widget:
        return Row(
            gap=0,
            sizes=[STAT_CELL_W_LEFT, DIVIDER_THICKNESS, STAT_CELL_W_RIGHT],
            children=[left, _divider(), right],
        )

    top = _subrow(
        _build_stat_cell("S", _format_ground_speed(flight.ground_speed_kt), STAT_CELL_W_LEFT),
        _build_stat_cell("A", _format_altitude(flight.altitude_ft), STAT_CELL_W_RIGHT),
    )
    bottom = _subrow(
        _build_stat_cell("V", _format_vertical_rate(flight.vertical_rate_fpm), STAT_CELL_W_LEFT),
        delta_cell,
    )
    return Column(
        gap=0,
        sizes=[STAT_SUBROW_H, DIVIDER_THICKNESS, STAT_SUBROW_H],
        children=[top, _divider(), bottom],
    )


class _TypeNameScroll:
    """Persistent anchor for the aircraft-type marquee.

    Reset whenever the displayed text changes so the scroll restarts from
    the left edge for a new aircraft instead of jumping mid-word.
    """

    def __init__(self) -> None:
        self.last_text: str | None = None
        self.anchor_mono: float = 0.0


_type_name_scroll = _TypeNameScroll()
_TYPE_NAME_SCROLL_PX_PER_S = 14.0


def _build_type_name_text(text: str, max_width_px: int) -> Widget:
    """Aircraft-type line: clip when it fits, marquee when it doesn't.

    Sits on the dim-coloured bottom line of the details column, so the
    text takes the LABEL colour to recede behind the brighter flight ID
    on line 1 and the route bearing on line 2.
    """
    width, _ = FONT_4X6.measure(text)
    if width <= max_width_px:
        return Text(
            text=text,
            font=FONT_4X6,
            align="left",
            overflow="clip",
            color=COLOR_LABEL,
        )
    if _type_name_scroll.last_text != text:
        _type_name_scroll.last_text = text
        _type_name_scroll.anchor_mono = time.monotonic()
    elapsed = max(0.0, time.monotonic() - _type_name_scroll.anchor_mono)
    return Text(
        text=text,
        font=FONT_4X6,
        align="left",
        overflow="overflow",
        overflow_offset=elapsed * _TYPE_NAME_SCROLL_PX_PER_S,
        overflow_gap=12,
        color=COLOR_LABEL,
    )


def _build_details_column(flight: Flight) -> Widget:
    """Layout (top to bottom):
        line 1 — flight ID / call sign (bright, FONT_5X7)
        line 2 — compass + distance from viewer (accent blue, FONT_5X7)
        line 3 — long aircraft type, marquees if it doesn't fit (dim, FONT_4X6)
    """
    type_text = _aircraft_type_display(flight)
    lines = Column(
        gap=3,
        sizes=[7, 7, 6],
        children=[
            Text(
                text=_flight_id_line(flight),
                font=FONT_5X7,
                align="left",
                overflow="clip",
                color=COLOR_VALUE,
            ),
            Text(
                text=_route_text(flight),
                font=FONT_5X7,
                align="left",
                overflow="clip",
                color=COLOR_ACCENT,
            ),
            _build_type_name_text(type_text, DETAILS_WIDTH - 2),
        ],
    )
    return Panel(padding=1, bg=colors.BLACK, border=None, child=lines)


def _build_logo_widget(flight: Flight) -> Widget:
    logo = load_airline_logo(
        flight.airline_icao or resolve_airline_from_callsign(flight.callsign)
    )
    if logo is not None:
        # Source PNGs are 48x48; use "contain" so the widget scales to the 32x32 slot.
        return Image(frame=logo, fit="contain", bg=colors.BLACK)
    return Panel(
        padding=0,
        bg=colors.BLACK,
        border=COLOR_DIVIDER,
        child=Text(
            text=(flight.airline_icao or flight.callsign[:3] or "???").upper(),
            font=FONT_5X7,
            align="center",
            overflow="clip",
            color=COLOR_ACCENT,
        ),
    )


def _build_hero_row(flight: Flight) -> Widget:
    return Row(
        gap=0,
        sizes=[LOGO_SIZE, DIVIDER_THICKNESS, DETAILS_WIDTH],
        children=[_build_logo_widget(flight), _divider(), _build_details_column(flight)],
    )


def _build_left_column(flight: Flight) -> Widget:
    return Column(
        gap=0,
        sizes=[HERO_ROW_HEIGHT, DIVIDER_THICKNESS, STATS_ROW_HEIGHT],
        children=[_build_hero_row(flight), _divider(), _build_stats_row(flight)],
    )


class _SweepState:
    """Persistent radar state across frames (the Radar widget is rebuilt each frame)."""

    def __init__(self) -> None:
        self.displayed: dict[str, "AircraftPing"] = {}
        self.last_sweep_deg: float | None = None


_sweep_state = _SweepState()


def _sweep_angle_deg(now_mono: float) -> float:
    """Current bearing of the sweep arm, increasing clockwise."""
    return (now_mono * 360.0 / SWEEP_PERIOD_S) % 360.0


def _sweep_arc_covers(prev: float | None, curr: float, target: float) -> bool:
    """True if the clockwise sweep moved from `prev` past `target` to reach `curr`."""
    if prev is None:
        return True
    if curr >= prev:
        return prev <= target <= curr
    # Wrapped through 0/360.
    return target >= prev or target <= curr


@dataclass
class Radar(Widget):
    """Polar top-down radar with the viewer at center.

    Rotated so ``view_bearing_deg`` points up — i.e. a south-facing window
    puts south at the top of the radar, which matches what the viewer sees
    out the window. The horizontal axis is still viewer-left/right.

    A rotating sweep arm refreshes each plane's displayed position only as
    it passes overhead, mimicking a mechanical PPI radar.
    """

    snapshot: AirSnapshot

    def draw(self, canvas: PixelCanvas, rect: Rect) -> None:
        if rect.width < 6 or rect.height < 6:
            return

        side = min(rect.width, rect.height)
        # Use the midpoint between the rect's edges so an even-diameter circle
        # (e.g. 40 in a 40-wide rect) lands symmetrically on the pixel grid.
        cx = rect.x + (rect.width - 1) / 2.0
        cy = rect.y + (rect.height - 1) / 2.0
        radius = (side - 1) / 2.0

        region = self.snapshot.region
        rotation_deg = region.view_bearing_deg

        def project(bearing_deg: float, distance_frac: float) -> tuple[float, float]:
            rel = math.radians(bearing_deg - rotation_deg)
            return (
                cx + math.sin(rel) * distance_frac * radius,
                cy - math.cos(rel) * distance_frac * radius,
            )

        # Advance the sweep and refresh frozen plane positions for any whose
        # current bearing the sweep just passed.
        sweep_deg = _sweep_angle_deg(time.monotonic())
        prev_sweep_deg = _sweep_state.last_sweep_deg
        current_by_id: dict[str, "AircraftPing"] = {}
        for ping in self.snapshot.pings:
            if not ping.icao24:
                continue
            current_by_id[ping.icao24] = ping
            if _sweep_arc_covers(prev_sweep_deg, sweep_deg, ping.bearing_deg):
                _sweep_state.displayed[ping.icao24] = ping
        for icao in list(_sweep_state.displayed.keys()):
            if icao not in current_by_id:
                del _sweep_state.displayed[icao]
        _sweep_state.last_sweep_deg = sweep_deg

        with canvas.clip(rect):
            # View cone: two radial lines from center to arc. They span the
            # upper half after rotation, since view_bearing points up.
            if region.view_cone_deg < 360.0:
                half = region.view_cone_deg / 2.0
                for edge_bearing in (
                    region.view_bearing_deg - half,
                    region.view_bearing_deg + half,
                ):
                    ex, ey = project(edge_bearing, 1.0)
                    _draw_line(
                        canvas,
                        int(round(cx)),
                        int(round(cy)),
                        int(round(ex)),
                        int(round(ey)),
                        COLOR_RADAR_CONE,
                    )

            # Sweep trail behind the arm — drawn before planes so they sit on top.
            for offset_deg, brightness in SWEEP_TRAIL_STEPS:
                trail_bearing = (sweep_deg - offset_deg) % 360.0
                tex, tey = project(trail_bearing, 1.0)
                trail_color = _lerp_color(colors.BLACK, COLOR_RADAR_SWEEP, brightness)
                _draw_line(
                    canvas,
                    int(round(cx)),
                    int(round(cy)),
                    int(round(tex)),
                    int(round(tey)),
                    trail_color,
                )

            _draw_circle_outline(canvas, cx, cy, radius, COLOR_RADAR_RING)

            # Small center "+" marks the viewer position and anchors the scope.
            icx = int(round(cx))
            icy = int(round(cy))
            canvas.pixel(icx, icy, COLOR_RADAR_CENTER)
            canvas.pixel(icx - 1, icy, COLOR_RADAR_CENTER)
            canvas.pixel(icx + 1, icy, COLOR_RADAR_CENTER)
            canvas.pixel(icx, icy - 1, COLOR_RADAR_CENTER)
            canvas.pixel(icx, icy + 1, COLOR_RADAR_CENTER)

            selected_icao = self.snapshot.selected.icao24 if self.snapshot.selected else None
            radius_nm = max(0.1, region.radar_radius_nm)

            # Each aircraft renders as three adjacent dots: head at the current
            # position (green, or red for the selected flight) plus two trailing
            # dots. Positions come from the sweep-frozen cache, so a plane only
            # moves when the arm passes over its current bearing.

            def _project_polar(bearing_deg: float, distance_nm: float) -> tuple[int, int]:
                frac = min(1.0, distance_nm / radius_nm)
                x, y = project(bearing_deg, frac)
                return int(round(x)), int(round(y))

            for ping in _sweep_state.displayed.values():
                if ping.distance_nm > radius_nm:
                    continue
                is_selected = bool(ping.icao24) and ping.icao24 == selected_icao
                head_color = COLOR_RADAR_HEAD_SELECTED if is_selected else COLOR_RADAR_HEAD_NORMAL

                head = _project_polar(ping.bearing_deg, ping.distance_nm)

                if ping.track_deg is not None:
                    track_rel = math.radians(ping.track_deg - rotation_deg)
                    synth_dx = -math.sin(track_rel)
                    synth_dy = math.cos(track_rel)
                else:
                    synth_dx = synth_dy = 0.0

                def _pick_trail(slot_index: int, used: tuple[tuple[int, int], ...]) -> tuple[int, int] | None:
                    if slot_index < len(ping.trail):
                        bearing, distance = ping.trail[slot_index]
                        candidate = _project_polar(bearing, distance)
                        if candidate not in used:
                            return candidate
                    if ping.track_deg is None:
                        return None
                    offset = slot_index + 1
                    synth = (
                        int(round(head[0] + synth_dx * offset)),
                        int(round(head[1] + synth_dy * offset)),
                    )
                    if synth in used:
                        return None
                    return synth

                near = _pick_trail(0, (head,))
                far = _pick_trail(1, (head,) + ((near,) if near is not None else ()))

                if far is not None:
                    canvas.pixel(far[0], far[1], COLOR_RADAR_TAIL_FAR)
                if near is not None:
                    canvas.pixel(near[0], near[1], COLOR_RADAR_TAIL_NEAR)
                canvas.pixel(head[0], head[1], head_color)

            # Main sweep arm — brightest, drawn last so it sits on top.
            ax, ay = project(sweep_deg, 1.0)
            _draw_line(canvas, icx, icy, int(round(ax)), int(round(ay)), COLOR_RADAR_SWEEP)


@dataclass
class PositionBar(Widget):
    """Horizontal bar mapping the view cone; slider shows the selected flight's bearing."""

    snapshot: AirSnapshot

    def draw(self, canvas: PixelCanvas, rect: Rect) -> None:
        if rect.width <= 6 or rect.height <= 2:
            return

        # Bar background.
        canvas.rect(rect, fill=COLOR_BAR_BG)

        inner_left = rect.x + 1
        inner_right = rect.right - 2
        mid_y = rect.y + rect.height // 2

        # End ticks (full-height) and a dimmer center tick marking due-south.
        canvas.vline(inner_left, rect.y + 1, rect.height - 2, COLOR_BAR_TICK)
        canvas.vline(inner_right, rect.y + 1, rect.height - 2, COLOR_BAR_TICK)
        center_x = (inner_left + inner_right) // 2
        canvas.vline(center_x, rect.y + 2, rect.height - 4, COLOR_DIVIDER)

        # Subtle horizontal line across the middle so the slot reads as a bar.
        canvas.hline(inner_left + 1, mid_y, (inner_right - inner_left) - 1, COLOR_DIVIDER)

        selected = self.snapshot.selected
        if selected is None:
            return

        region = self.snapshot.region
        cone = max(1.0, region.view_cone_deg)
        half = cone / 2.0
        # bearing relative to cone center, in [-half, +half].
        rel = ((selected.bearing_deg - region.view_bearing_deg + 540.0) % 360.0) - 180.0
        rel = max(-half, min(half, rel))
        frac = (rel + half) / cone  # 0.0 = left edge, 1.0 = right edge

        slider_w = 5
        slider_h = rect.height - 2
        usable = (inner_right - inner_left + 1) - slider_w
        if usable < 0:
            return
        slider_x = inner_left + int(round(frac * usable))
        slider_y = rect.y + 1
        slider_color = _speed_color(selected.ground_speed_kt)

        for dx in range(slider_w):
            canvas.vline(slider_x + dx, slider_y, slider_h, slider_color)
        # Tiny brighter highlight on top row to make the slider pop.
        highlight = _lerp_color(slider_color, colors.WHITE, 0.35)
        canvas.hline(slider_x, slider_y, slider_w, highlight)


_ROUTE_MAP_BG: Color = (8, 14, 18)
_ROUTE_MAP_LAND: Color = (14, 38, 14)
_ROUTE_MAP_PARK: Color = (24, 78, 24)
_ROUTE_MAP_BUILDING: Color = (60, 64, 70)
_ROUTE_MAP_WATER: Color = (16, 64, 150)
_ROUTE_MAP_ROAD: Color = (70, 76, 82)
_ROUTE_MAP_BORDER: Color = (110, 130, 150)


def _route_endpoints(
    flight: Flight | None,
) -> tuple[float, float, float, float] | None:
    """``(o_lat, o_lon, d_lat, d_lon)`` when both ends are known, else None."""
    if flight is None:
        return None
    if (
        flight.origin_lat is None
        or flight.origin_lon is None
        or flight.destination_lat is None
        or flight.destination_lon is None
    ):
        return None
    return (
        flight.origin_lat,
        flight.origin_lon,
        flight.destination_lat,
        flight.destination_lon,
    )


def _build_route_map_widget(
    flight: Flight,
    endpoints: tuple[float, float, float, float],
) -> Widget:
    o_lat, o_lon, d_lat, d_lon = endpoints
    tile_data = default_fetcher().get(o_lat, o_lon, d_lat, d_lon)
    zoom = int(tile_data.get("zoom", 4))
    return RouteMap(
        center_lat=flight.latitude,
        center_lon=flight.longitude,
        zoom=zoom,
        tile_data=tile_data,
        loading=False,
        bg=_ROUTE_MAP_BG,
        land_color=_ROUTE_MAP_LAND,
        park_color=_ROUTE_MAP_PARK,
        building_color=_ROUTE_MAP_BUILDING,
        water_color=_ROUTE_MAP_WATER,
        road_color=_ROUTE_MAP_ROAD,
        border_color=_ROUTE_MAP_BORDER,
        origin_lat=o_lat,
        origin_lon=o_lon,
        dest_lat=d_lat,
        dest_lon=d_lon,
        plane_lat=flight.latitude,
        plane_lon=flight.longitude,
    )


def _build_right_column(snapshot: AirSnapshot) -> Widget:
    """Right column: full-size radar by itself when no route, stacked
    radar+map when a hero flight has both endpoints.

    Layout for the stacked case in the 52-tall column:
        2 px spacer
        24 px radar (40 wide; widget centers a 24-px circle inside)
        2 px spacer
        22 px map preview
        2 px spacer
    """
    selected = snapshot.selected
    endpoints = _route_endpoints(selected)
    if selected is None or endpoints is None:
        return Column(
            gap=0,
            sizes=[6, 40, 6],
            children=[_spacer(), Radar(snapshot=snapshot), _spacer()],
        )

    radar = Radar(snapshot=snapshot)
    map_widget = _build_route_map_widget(selected, endpoints)
    return Column(
        gap=0,
        sizes=[2, 24, 2, 22, 2],
        children=[_spacer(), radar, _spacer(), map_widget, _spacer()],
    )


def _build_top_row(snapshot: AirSnapshot) -> Widget:
    if snapshot.selected is None:
        left: Widget = _build_waiting_left(snapshot)
    else:
        left = _build_left_column(snapshot.selected)
    return Row(
        gap=0,
        sizes=[LEFT_AREA_WIDTH, DIVIDER_THICKNESS, RADAR_AREA_WIDTH],
        children=[left, _divider(), _build_right_column(snapshot)],
    )


def _format_dep_arr_text(flight: Flight | None, max_width_px: int) -> str:
    """Compose 'Origin City (XXX) to Destination City (YYY)', abbreviating
    cities by right-truncation only as much as needed to fit ``max_width_px``.

    Falls back to ``CODE`` (no parens) when a city name is missing. Returns
    an empty string when both codes are missing.
    """
    if flight is None:
        return ""
    o_code = (flight.origin_iata or "").strip()
    o_city = (flight.origin_name or "").strip()
    d_code = (flight.destination_iata or "").strip()
    d_city = (flight.destination_name or "").strip()

    if o_city.casefold() == HOME_CITY.casefold():
        o_city = ""
    if d_city.casefold() == HOME_CITY.casefold():
        d_city = ""

    if not o_code and not d_code:
        return ""

    def _compose(oc: str, dc: str) -> str:
        left = f"{oc} ({o_code})" if oc and o_code else (oc or o_code)
        right = f"{dc} ({d_code})" if dc and d_code else (dc or d_code)
        if not left:
            return right
        if not right:
            return left
        return f"{left} to {right}"

    oc, dc = o_city, d_city
    while FONT_4X6.measure(_compose(oc, dc))[0] > max_width_px:
        # Shrink whichever city is longer; tie → shrink the right (destination)
        # so the origin retains slightly more characters when both must be cut.
        if len(dc) >= len(oc) and dc:
            dc = dc[:-1].rstrip()
        elif oc:
            oc = oc[:-1].rstrip()
        else:
            break
    return _compose(oc, dc)


def _build_dep_arr_row(flight: Flight | None) -> Widget:
    """Footer line: 'Origin City (XXX) to Destination City (YYY)'."""
    text = _format_dep_arr_text(flight, DISPLAY_WIDTH)
    line = Text(
        text=text,
        font=FONT_4X6,
        align="center",
        overflow="clip",
        color=COLOR_VALUE,
    )
    # Center the 6-tall text within the 11-tall footer strip.
    return Column(gap=0, sizes=[2, 7, 2], children=[_spacer(), line, _spacer()])


def _format_temp_f(temp_f: float | None) -> str:
    if temp_f is None:
        return "--F"
    return f"{int(round(temp_f))}F"


@dataclass
class _ScaledText(Widget):
    """Single-line bitmap text rendered at integer ``scale``, center-aligned."""

    text: str
    font: object  # BitmapFont — kept loose to avoid import cycle in dataclass
    color: Color
    scale: int = 1

    def draw(self, canvas: PixelCanvas, rect: Rect) -> None:
        if rect.width <= 0 or rect.height <= 0 or not self.text:
            return
        line_width, line_height = self.font.measure(self.text, scale=self.scale)
        draw_x = rect.x + max(0, (rect.width - line_width) // 2)
        draw_y = rect.y + max(0, (rect.height - line_height) // 2)
        with canvas.clip(rect):
            self.font.render(canvas, draw_x, draw_y, self.text, self.color, scale=self.scale)


def _build_waiting_left(snapshot: AirSnapshot) -> Widget:
    del snapshot  # No longer used; kept for signature parity.
    now = time.localtime()
    time_text = time.strftime("%H:%M:%S", now)
    out_text = f"OUT {_format_temp_f(weather.outside_temp_f())}"
    in_text = f"IN  {_format_temp_f(weather.inside_temp_f())}"

    # 87×52 layout: 14-tall time at scale 2, two 7-tall temp lines, with
    # spacers padding the column to fill vertically.
    return Panel(
        padding=1,
        bg=colors.BLACK,
        border=None,
        child=Column(
            gap=0,
            sizes=[5, 14, 6, 7, 4, 7, 7],
            children=[
                _spacer(),
                _ScaledText(text=time_text, font=FONT_5X7, color=COLOR_VALUE, scale=2),
                _spacer(),
                _ScaledText(text=out_text, font=FONT_5X7, color=COLOR_ACCENT, scale=1),
                _spacer(),
                _ScaledText(text=in_text, font=FONT_5X7, color=COLOR_ACCENT, scale=1),
                _spacer(),
            ],
        ),
    )


_FACT_SCROLL_PX_PER_S = 18.0  # comfortable reading speed for FONT_4X6


class _IdleFootState:
    """Persistent state for the idle (no-flight) footer.

    Tracks the previously-selected aircraft so we can pick a fresh fun
    fact each time the display transitions from "have a hero flight" to
    "no aircraft in cone". The first frame ever counts as a transition.
    """

    def __init__(self) -> None:
        self.last_selected_icao: str | None = None
        self.has_seen_first_frame: bool = False
        self.current_fact: str = ""
        self.fact_started_mono: float = 0.0


_idle_foot = _IdleFootState()


def _maybe_refresh_idle_fact(snapshot: AirSnapshot) -> None:
    selected = snapshot.selected
    selected_icao = selected.icao24 if selected is not None else None

    became_idle = (
        selected_icao is None
        and (_idle_foot.last_selected_icao is not None or not _idle_foot.has_seen_first_frame)
    )
    if became_idle:
        _idle_foot.current_fact = random.choice(ANIMAL_FUN_FACTS)
        _idle_foot.fact_started_mono = time.monotonic()

    _idle_foot.has_seen_first_frame = True
    _idle_foot.last_selected_icao = selected_icao


def _build_fun_fact_footer() -> Widget:
    text = _idle_foot.current_fact
    if not text:
        return _spacer()
    fact_width, _ = FONT_4X6.measure(text)
    if fact_width <= DISPLAY_WIDTH:
        line: Widget = Text(
            text=text,
            font=FONT_4X6,
            align="center",
            overflow="clip",
            color=COLOR_LABEL,
        )
    else:
        elapsed = max(0.0, time.monotonic() - _idle_foot.fact_started_mono)
        # Positive offset shifts the content leftward over time, producing
        # right-to-left scroll motion (the standard reading-marquee direction).
        scroll_offset = elapsed * _FACT_SCROLL_PX_PER_S
        line = Text(
            text=text,
            font=FONT_4X6,
            align="left",
            overflow="overflow",
            overflow_offset=scroll_offset,
            overflow_gap=20,
            color=COLOR_LABEL,
        )
    # Center the 6-tall text within the 11-tall footer strip.
    return Column(gap=0, sizes=[2, 7, 2], children=[_spacer(), line, _spacer()])


class _EventFootState:
    """Persistent state for the upcoming-event footer.

    The scroll anchor only resets when the event identity changes (different
    title or start time), so the title scrolls smoothly across the
    once-per-minute updates of the time-until phrase.
    """

    def __init__(self) -> None:
        self.last_event_key: tuple[str, "datetime"] | None = None
        self.anchor_mono: float = 0.0


_event_foot = _EventFootState()


def _format_event_clock(local: "datetime") -> str:
    """'9 AM' / '3:30 PM' — drop leading zero on hour, drop ':00' minutes."""
    h12 = local.hour % 12 or 12
    suffix = "AM" if local.hour < 12 else "PM"
    if local.minute == 0:
        return f"{h12} {suffix}"
    return f"{h12}:{local.minute:02d} {suffix}"


def _format_event_when(ev: UpcomingEvent) -> str:
    """Phrase trailing the title: 'now', 'in 12m', 'at 3:30 PM', 'Sun 9 AM'."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    if ev.start <= now < ev.end:
        return "now"
    delta_s = (ev.start - now).total_seconds()
    if delta_s < 60.0:
        return "now"
    minutes = int(delta_s // 60)
    if minutes < 60:
        return f"in {minutes}m"
    local_start = ev.start.astimezone()
    today_local = now.astimezone().date()
    if local_start.date() == today_local:
        return f"at {_format_event_clock(local_start)}"
    return f"{local_start.strftime('%a')} {_format_event_clock(local_start)}"


def _build_event_footer(ev: UpcomingEvent) -> Widget:
    key = (ev.title, ev.start)
    if _event_foot.last_event_key != key:
        _event_foot.last_event_key = key
        _event_foot.anchor_mono = time.monotonic()

    text = f"{ev.title} {_format_event_when(ev)}"
    text_w, _ = FONT_4X6.measure(text)
    if text_w <= DISPLAY_WIDTH:
        line: Widget = Text(
            text=text,
            font=FONT_4X6,
            align="center",
            overflow="clip",
            color=COLOR_VALUE,
        )
    else:
        elapsed = max(0.0, time.monotonic() - _event_foot.anchor_mono)
        scroll_offset = elapsed * _FACT_SCROLL_PX_PER_S
        line = Text(
            text=text,
            font=FONT_4X6,
            align="left",
            overflow="overflow",
            overflow_offset=scroll_offset,
            overflow_gap=20,
            color=COLOR_VALUE,
        )
    return Column(gap=0, sizes=[2, 7, 2], children=[_spacer(), line, _spacer()])


def build_flight_hero_page(
    snapshot: AirSnapshot | None,
    *,
    status_line: str | None = None,
) -> Panel:
    """Compose the hero page. `snapshot` may be None before the first fetch completes."""
    del status_line  # keeping the signature for compatibility; status is inferred from snapshot

    from ui.flight.api import Region as _Region

    if snapshot is None:
        snapshot = AirSnapshot(region=_Region(0.0, 0.0, 1.0))

    _maybe_refresh_idle_fact(snapshot)

    if snapshot.selected is None:
        upcoming = events.next_event()
        if upcoming is not None:
            footer: Widget = _build_event_footer(upcoming)
        else:
            footer = _build_fun_fact_footer()
    else:
        footer = _build_dep_arr_row(snapshot.selected)

    body = Column(
        gap=0,
        sizes=[TOP_HEIGHT, DIVIDER_THICKNESS, POSITION_BAR_HEIGHT],
        children=[
            _build_top_row(snapshot),
            _divider(),
            footer,
        ],
    )
    return Panel(padding=0, bg=colors.BLACK, border=None, child=body)


def _draw_line(
    canvas: PixelCanvas,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    color: Color,
) -> None:
    dx = abs(x1 - x0)
    sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0)
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        canvas.pixel(x0, y0, color)
        if x0 == x1 and y0 == y1:
            return
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def _draw_circle_outline(
    canvas: PixelCanvas,
    cx: float,
    cy: float,
    radius: float,
    color: Color,
) -> None:
    """Draw a 1-px circle outline. Center and radius may be fractional.

    A pixel ``(x, y)`` is part of the outline iff its Euclidean distance to
    ``(cx, cy)`` falls in ``[radius - 0.5, radius + 0.5)``. Using a fractional
    center lets even-diameter circles fit exactly inside an even-width rect
    (otherwise a 40-pixel-wide box can only hold a 39-pixel circle).
    """
    if radius < 1:
        return
    inner = max(0.0, radius - 0.5)
    outer = radius + 0.5
    inner2 = inner * inner
    outer2 = outer * outer
    bounds = int(math.ceil(outer))
    icx = int(round(cx))
    icy = int(round(cy))
    for dy in range(-bounds, bounds + 1):
        y_off = (icy + dy) - cy
        y_off2 = y_off * y_off
        if y_off2 >= outer2:
            continue
        for dx in range(-bounds, bounds + 1):
            x_off = (icx + dx) - cx
            d2 = x_off * x_off + y_off2
            if inner2 <= d2 < outer2:
                canvas.pixel(icx + dx, icy + dy, color)
