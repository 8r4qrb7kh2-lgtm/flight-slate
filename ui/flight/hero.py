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
from dataclasses import dataclass
from pathlib import Path

from ui.core.canvas import PixelCanvas, Rect
from ui.core.colors import Color, colors
from ui.core.image_asset import ImageFrame, load_png_image_frame
from ui.core.widgets import Column, Image, Panel, Row, Text, Widget
from ui.fonts import FONT_3X5, FONT_4X6, FONT_5X7
from ui.flight.airlines import load_airline_logo, resolve_airline_from_callsign
from ui.flight.api import AirSnapshot, Flight


ICON_DIR = Path(__file__).resolve().parents[2] / "assets" / "icons"
ICON_SPEED = "speed.png"
ICON_ALTITUDE = "altitude.png"
ICON_VERTICAL = "vertical-speed.png"

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

# Stat cell widths in the stats row (sum must equal LEFT_AREA_WIDTH).
_STAT_BASE = (LEFT_AREA_WIDTH - 2 * DIVIDER_THICKNESS) // 3
STAT_CELL_WIDTHS: tuple[int, int, int] = (
    _STAT_BASE,
    _STAT_BASE,
    LEFT_AREA_WIDTH - 2 * DIVIDER_THICKNESS - 2 * _STAT_BASE,
)

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


def _callsign_display(flight: Flight) -> str:
    airline = flight.airline_icao or ""
    number = flight.flight_number or ""
    if airline and number:
        return f"{airline} {number}"
    return flight.callsign.strip() or flight.icao24.upper()


def _aircraft_line(flight: Flight) -> str:
    plane = (flight.aircraft_type or "").strip()
    reg = (flight.registration or "").strip()
    if plane and reg:
        return f"{plane} {reg}"
    if plane:
        return plane
    if reg:
        return reg
    return flight.icao24.upper() or ""


def _build_stat_cell(icon: Widget, value: str) -> Widget:
    # Cell height is 19. Keep internal padding so icons don't crowd dividers.
    content_row = Row(
        gap=1,
        sizes=[9, 19],
        children=[
            icon,
            Text(
                text=value,
                font=FONT_5X7,
                align="left",
                overflow="clip",
                color=COLOR_VALUE,
            ),
        ],
    )
    return Column(
        gap=0,
        sizes=[4, 11, 4],
        children=[_spacer(), content_row, _spacer()],
    )


def _build_stats_row(flight: Flight) -> Widget:
    return Row(
        gap=0,
        sizes=[
            STAT_CELL_WIDTHS[0],
            DIVIDER_THICKNESS,
            STAT_CELL_WIDTHS[1],
            DIVIDER_THICKNESS,
            STAT_CELL_WIDTHS[2],
        ],
        children=[
            _build_stat_cell(
                _icon_or_letter(ICON_SPEED, "S", COLOR_ACCENT),
                _format_ground_speed(flight.ground_speed_kt),
            ),
            _divider(),
            _build_stat_cell(
                _icon_or_letter(ICON_ALTITUDE, "A", COLOR_ACCENT),
                _format_altitude(flight.altitude_ft),
            ),
            _divider(),
            _build_stat_cell(
                _icon_or_letter(ICON_VERTICAL, "V", COLOR_ACCENT),
                _format_vertical_rate(flight.vertical_rate_fpm),
            ),
        ],
    )


def _build_details_column(flight: Flight) -> Widget:
    lines = Column(
        gap=3,
        sizes=[7, 7, 6],
        children=[
            Text(
                text=_callsign_display(flight),
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
            Text(
                text=_aircraft_line(flight),
                font=FONT_4X6,
                align="left",
                overflow="clip",
                color=COLOR_LABEL,
            ),
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


@dataclass
class Radar(Widget):
    """Polar top-down radar with the viewer at center.

    Rotated so ``view_bearing_deg`` points up — i.e. a south-facing window
    puts south at the top of the radar, which matches what the viewer sees
    out the window. The horizontal axis is still viewer-left/right.
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
            # dots. We prefer real recorded positions from PingHistory, but
            # between 5-second polls most planes move <1 px on a 40-px radar,
            # so the history dots collapse onto the head. In that case we fall
            # back to a synthetic 1-px step along the aircraft's track so the
            # trail is always visible as 3 distinct pixels.

            def _project_polar(bearing_deg: float, distance_nm: float) -> tuple[int, int]:
                frac = min(1.0, distance_nm / radius_nm)
                x, y = project(bearing_deg, frac)
                return int(round(x)), int(round(y))

            for ping in self.snapshot.pings:
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
                    # Prefer the recorded history point for this slot when it
                    # lands on a pixel distinct from everything already drawn.
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


def _build_radar_area(snapshot: AirSnapshot) -> Widget:
    radar = Radar(snapshot=snapshot)
    # Centre the radar vertically within the right column so the optical weight
    # balances the left-side content.
    return Column(
        gap=0,
        sizes=[6, 40, 6],
        children=[_spacer(), radar, _spacer()],
    )


def _build_top_row(snapshot: AirSnapshot) -> Widget:
    if snapshot.selected is None:
        left: Widget = _build_waiting_left(snapshot)
    else:
        left = _build_left_column(snapshot.selected)
    return Row(
        gap=0,
        sizes=[LEFT_AREA_WIDTH, DIVIDER_THICKNESS, RADAR_AREA_WIDTH],
        children=[left, _divider(), _build_radar_area(snapshot)],
    )


def _build_dep_arr_row(flight: Flight | None) -> Widget:
    """Footer row showing origin/destination codes + cities (replaces the slider)."""
    origin_code = (flight.origin_iata if flight else None) or ""
    origin_city = (flight.origin_name if flight else None) or ""
    dest_code = (flight.destination_iata if flight else None) or ""
    dest_city = (flight.destination_name if flight else None) or ""

    # 3-char IATA at FONT_4X6 = 12px; 13px cell leaves 1px breathing room.
    code_w = 13
    city_w = 49
    gap = 2

    left_half = Row(
        gap=gap,
        sizes=[code_w, city_w],
        children=[
            Text(text=origin_code, font=FONT_4X6, align="left", overflow="clip", color=COLOR_ACCENT),
            Text(text=origin_city, font=FONT_4X6, align="left", overflow="clip", color=COLOR_VALUE),
        ],
    )
    right_half = Row(
        gap=gap,
        sizes=[city_w, code_w],
        children=[
            Text(text=dest_city, font=FONT_4X6, align="right", overflow="clip", color=COLOR_VALUE),
            Text(text=dest_code, font=FONT_4X6, align="right", overflow="clip", color=COLOR_ACCENT),
        ],
    )
    content = Row(gap=0, sizes=[64, 64], children=[left_half, right_half])

    # Center the 6-tall text within the 11-tall footer strip.
    return Column(gap=0, sizes=[2, 7, 2], children=[_spacer(), content, _spacer()])


def _build_waiting_left(snapshot: AirSnapshot) -> Widget:
    del snapshot  # No longer used; kept for signature parity.
    return Panel(
        padding=2,
        bg=colors.BLACK,
        border=None,
        child=Column(
            gap=4,
            sizes=[7, 7, 7],
            children=[
                Text(
                    text="FLIGHT SLATE",
                    font=FONT_5X7,
                    align="center",
                    overflow="clip",
                    color=COLOR_ACCENT,
                ),
                Text(
                    text="LIVE RADAR",
                    font=FONT_5X7,
                    align="center",
                    overflow="clip",
                    color=COLOR_LABEL,
                ),
                Text(
                    text="NO AIRCRAFT",
                    font=FONT_5X7,
                    align="center",
                    overflow="clip",
                    color=COLOR_STATUS_WARN,
                ),
            ],
        ),
    )


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

    body = Column(
        gap=0,
        sizes=[TOP_HEIGHT, DIVIDER_THICKNESS, POSITION_BAR_HEIGHT],
        children=[
            _build_top_row(snapshot),
            _divider(),
            _build_dep_arr_row(snapshot.selected),
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
