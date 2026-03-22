"""Core UI demo primitives for a 128x64 LED flight display.

This module intentionally focuses on rendering and interaction scaffolding,
not on live flight integration. It provides a stress-test demo for the core
UI system: typography, icons, logo bitmaps, widgets, list layouts, and a
simple low-detail map viewport.
"""

from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass, field
from functools import lru_cache

try:
    from PIL import Image, ImageDraw, ImageFont
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(
        "Pillow is required for the core UI demo. "
        "Install it into the interpreter you are using, for example: "
        "`python3 -m pip install Pillow`."
    ) from exc

from mock_led_matrix import MockRGBMatrix
from standard_led_matrix_interface import InteractiveLEDMatrix, LEDMatrix, RGBMatrixOptions

Color = tuple[int, int, int]


def rgb(value: str) -> Color:
    value = value.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def mix(a: Color, b: Color, amount: float) -> Color:
    amount = clamp(amount, 0.0, 1.0)
    return tuple(int(a[index] + (b[index] - a[index]) * amount) for index in range(3))


def pulse(color: Color, low: float, high: float, phase: float) -> Color:
    return tuple(int(channel * (low + (high - low) * phase)) for channel in color)


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @property
    def center_x(self) -> int:
        return self.x + self.width // 2

    @property
    def center_y(self) -> int:
        return self.y + self.height // 2

    def inset(self, value: int) -> "Rect":
        return Rect(
            self.x + value,
            self.y + value,
            max(0, self.width - value * 2),
            max(0, self.height - value * 2),
        )


@dataclass(frozen=True)
class Theme:
    background: Color = rgb("#040b12")
    panel: Color = rgb("#0a1622")
    panel_alt: Color = rgb("#102031")
    panel_hot: Color = rgb("#132a3f")
    text: Color = rgb("#edf7ff")
    text_dim: Color = rgb("#93a7b8")
    text_muted: Color = rgb("#5d7184")
    cyan: Color = rgb("#59e5ff")
    lime: Color = rgb("#8bff9a")
    amber: Color = rgb("#ffc95a")
    coral: Color = rgb("#ff7a63")
    rose: Color = rgb("#ff5c7b")
    ocean: Color = rgb("#071728")
    ocean_glow: Color = rgb("#0f2840")
    land: Color = rgb("#163328")
    land_highlight: Color = rgb("#24493c")
    grid: Color = rgb("#15344d")
    route: Color = rgb("#66e3ff")
    selection: Color = rgb("#fff2a8")


@dataclass(frozen=True)
class FlightSample:
    airline: str
    flight_number: str
    logo_key: str
    accent: Color
    dep_code: str
    arr_code: str
    dep_lat: float
    dep_lon: float
    arr_lat: float
    arr_lon: float
    progress: float
    speed_kt: int
    altitude_ft: int
    heading_deg: int
    vertical_rate_fpm: int
    status: str
    updated_s: int
    aircraft_lat: float
    aircraft_lon: float

    @property
    def callsign(self) -> str:
        return self.flight_number

    @property
    def route_label(self) -> str:
        return f"{self.dep_code} -> {self.arr_code}"


@dataclass(frozen=True)
class MapPin:
    lat: float
    lon: float
    label: str
    color: Color
    icon: str = "pin"
    focused: bool = False


class FontRegistry:
    """Loads a small set of system fonts sized for the LED panel."""

    FONT_PATHS = {
        "headline": "/System/Library/Fonts/SFNSRounded.ttf",
        "body": "/System/Library/Fonts/SFNS.ttf",
        "mono": "/System/Library/Fonts/SFNSMono.ttf",
    }

    def get(self, role: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        path = self.FONT_PATHS.get(role, self.FONT_PATHS["body"])
        return self._load(path, size)

    @staticmethod
    @lru_cache(maxsize=128)
    def _load(path: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            return ImageFont.load_default()


def measure_text(font: ImageFont.FreeTypeFont | ImageFont.ImageFont, text: str) -> tuple[int, int]:
    left, top, right, bottom = font.getbbox(text or " ")
    return max(0, right - left), max(0, bottom - top)


def fit_text(
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
    mode: str = "ellipsis",
) -> str:
    if max_width <= 0:
        return ""
    if measure_text(font, text)[0] <= max_width:
        return text
    if mode == "clip":
        suffix = ""
    else:
        suffix = "..."
    if measure_text(font, suffix)[0] > max_width:
        suffix = ""
    candidate = text
    while candidate and measure_text(font, candidate + suffix)[0] > max_width:
        candidate = candidate[:-1]
    return candidate + suffix


@dataclass(frozen=True)
class PixelBitmap:
    rows: tuple[str, ...]
    palette: dict[str, Color]

    @property
    def width(self) -> int:
        return max((len(row) for row in self.rows), default=0)

    @property
    def height(self) -> int:
        return len(self.rows)

    def draw(self, canvas: "PixelCanvas", x: int, y: int, scale: int = 1) -> None:
        for row_index, row in enumerate(self.rows):
            for column_index, key in enumerate(row):
                if key == ".":
                    continue
                color = self.palette[key]
                for offset_y in range(scale):
                    for offset_x in range(scale):
                        canvas.pixel(
                            x + column_index * scale + offset_x,
                            y + row_index * scale + offset_y,
                            color,
                        )


def _bitmap(rows: tuple[str, ...], palette: dict[str, str]) -> PixelBitmap:
    return PixelBitmap(rows=rows, palette={key: rgb(value) for key, value in palette.items()})


def build_icon_registry(theme: Theme) -> dict[str, PixelBitmap]:
    return {
        "plane": _bitmap(
            (
                "...c.....",
                "...cc....",
                "ccccccccc",
                ".ccccccc.",
                "...cc....",
                "...c.....",
                "..c......",
                ".c.......",
                "c........",
            ),
            {"c": "#e7f7ff"},
        ),
        "speed": _bitmap(
            (
                "...c.....",
                ".ccccc...",
                "cc...cc..",
                "c.....c..",
                "c..c..c..",
                "cc...cc..",
                ".ccccc...",
                "....c....",
                "....c....",
            ),
            {"c": "#59e5ff"},
        ),
        "altitude": _bitmap(
            (
                "....c....",
                "...ccc...",
                "..ccccc..",
                ".ccccccc.",
                "...ccc...",
                "...ccc...",
                "...ccc...",
                "...ccc...",
                "...ccc...",
            ),
            {"c": "#8bff9a"},
        ),
        "heading": _bitmap(
            (
                "....c....",
                "...ccc...",
                "..ccccc..",
                ".cc.c.cc.",
                "cc..c..cc",
                "....c....",
                "....c....",
                "....c....",
                "....c....",
            ),
            {"c": "#ffc95a"},
        ),
        "clock": _bitmap(
            (
                "..ccccc..",
                ".cc...cc.",
                "cc.....cc",
                "cc..c..cc",
                "cc..cc.cc",
                "cc.....cc",
                ".cc...cc.",
                "..ccccc..",
                "....c....",
            ),
            {"c": "#edf7ff"},
        ),
        "pin": _bitmap(
            (
                "...ccc...",
                "..ccccc..",
                "..ccccc..",
                "..ccccc..",
                "...ccc...",
                "...ccc...",
                "...c.c...",
                "..c...c..",
                ".c.....c.",
            ),
            {"c": "#ff7a63"},
        ),
        "map": _bitmap(
            (
                "ccc...ccc",
                "ccc...ccc",
                ".ccc.ccc.",
                ".ccc.ccc.",
                "..ccccc..",
                "..ccccc..",
                ".ccc.ccc.",
                ".ccc.ccc.",
                "ccc...ccc",
            ),
            {"c": "#59e5ff"},
        ),
        "list": _bitmap(
            (
                "ccccccccc",
                ".........",
                "ccccccccc",
                ".........",
                "ccccccccc",
                ".........",
                "ccccccccc",
                ".........",
                "ccccccccc",
            ),
            {"c": "#edf7ff"},
        ),
        "live": _bitmap(
            (
                "...c.....",
                "..ccc....",
                ".ccccc...",
                "ccccccc..",
                ".ccccc...",
                "..ccc....",
                "...c.....",
                ".........",
                "...c.....",
            ),
            {"c": "#8bff9a"},
        ),
        "warn": _bitmap(
            (
                "....c....",
                "...ccc...",
                "..ccccc..",
                ".ccccc.cc",
                ".ccccc.cc",
                "...ccc...",
                "...ccc...",
                ".........",
                "...ccc...",
            ),
            {"c": "#ffc95a"},
        ),
        "error": _bitmap(
            (
                "cc.....cc",
                ".cc...cc.",
                "..cc.cc..",
                "...ccc...",
                "...ccc...",
                "..cc.cc..",
                ".cc...cc.",
                "cc.....cc",
                ".........",
            ),
            {"c": "#ff5c7b"},
        ),
    }


def build_logo_registry() -> dict[str, PixelBitmap]:
    return {
        "slate": _bitmap(
            (
                "...1111........",
                "..11..11.......",
                "......11.......",
                "....111........",
                "..111..........",
                ".11............",
                ".111111........",
                ".....111.......",
                "......11.......",
                "..11..11.......",
                "...1111........",
            ),
            {"1": "#59e5ff"},
        ),
        "meridian": _bitmap(
            (
                "11.......11....",
                "111.....111....",
                "1.11...11.1....",
                "1..11.11..1....",
                "1...111...1....",
                "1....1....1....",
                "1.........1....",
                "1.........1....",
                "1.........1....",
                "1.........1....",
                "1.........1....",
            ),
            {"1": "#ffc95a"},
        ),
        "harbor": _bitmap(
            (
                "11.....11......",
                "11.....11......",
                "11.....11......",
                "111111111......",
                "111111111......",
                "11.....11......",
                "11.....11......",
                "11.....11......",
                "11.....11......",
                "11.....11......",
                "11.....11......",
            ),
            {"1": "#8bff9a"},
        ),
        "ember": _bitmap(
            (
                "11111111.......",
                "11.............",
                "11.............",
                "111111.........",
                "111111.........",
                "11.............",
                "11.............",
                "11.............",
                "11111111.......",
                "11111111.......",
                "...............",
            ),
            {"1": "#ff7a63"},
        ),
    }


class PixelCanvas:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.image = Image.new("RGB", (width, height), (0, 0, 0))
        self.draw = ImageDraw.Draw(self.image)

    def clear(self, color: Color) -> None:
        self.draw.rectangle((0, 0, self.width, self.height), fill=color)

    def pixel(self, x: int, y: int, color: Color) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self.image.putpixel((x, y), color)

    def line(self, points: list[tuple[int, int]], color: Color, width: int = 1) -> None:
        self.draw.line(points, fill=color, width=width)

    def rect(self, rect: Rect, fill: Color | None = None, outline: Color | None = None) -> None:
        if rect.width <= 0 or rect.height <= 0:
            return
        self.draw.rectangle((rect.x, rect.y, rect.right - 1, rect.bottom - 1), fill=fill, outline=outline)

    def polygon(self, points: list[tuple[int, int]], fill: Color | None = None, outline: Color | None = None) -> None:
        self.draw.polygon(points, fill=fill, outline=outline)

    def circle(self, center_x: int, center_y: int, radius: int, fill: Color | None = None, outline: Color | None = None) -> None:
        self.draw.ellipse(
            (center_x - radius, center_y - radius, center_x + radius, center_y + radius),
            fill=fill,
            outline=outline,
        )

    def text(self, x: int, y: int, text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont, color: Color) -> None:
        self.draw.text((x, y), text, font=font, fill=color)

    def text_line(
        self,
        rect: Rect,
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        color: Color,
        align: str = "left",
        overflow: str = "ellipsis",
        tick: int = 0,
    ) -> None:
        display_text = fit_text(text, font, rect.width, mode=overflow if overflow != "marquee" else "ellipsis")
        text_width, text_height = measure_text(font, display_text)
        if overflow != "marquee" or measure_text(font, text)[0] <= rect.width:
            if align == "center":
                x = rect.x + max(0, (rect.width - text_width) // 2)
            elif align == "right":
                x = rect.right - text_width
            else:
                x = rect.x
            y = rect.y + max(0, (rect.height - text_height) // 2) - 1
            self.text(x, y, display_text, font, color)
            return

        text_width, text_height = measure_text(font, text)
        gap = "   "
        gap_width, _ = measure_text(font, gap)
        strip_width = text_width * 2 + gap_width
        strip = Image.new("RGBA", (strip_width, max(rect.height, text_height + 2)), (0, 0, 0, 0))
        strip_draw = ImageDraw.Draw(strip)
        strip_draw.text((0, 0), text, font=font, fill=color)
        strip_draw.text((text_width + gap_width, 0), text, font=font, fill=color)
        offset = tick % max(1, text_width + gap_width)
        crop = strip.crop((offset, 0, offset + rect.width, rect.height))
        self.image.paste(crop, (rect.x, rect.y), crop)

    def sync_to_matrix(self, matrix: LEDMatrix) -> None:
        pixels = self.image.load()
        for y in range(self.height):
            for x in range(self.width):
                matrix.SetPixel(x, y, *pixels[x, y])


class MockFlightProvider:
    """Animated mock data used by the demo scenes."""

    def __init__(self) -> None:
        self._seed_flights = (
            {
                "airline": "Slate Air",
                "flight_number": "SA128",
                "logo_key": "slate",
                "accent": rgb("#59e5ff"),
                "dep_code": "JFK",
                "arr_code": "ORD",
                "dep_lat": 40.6413,
                "dep_lon": -73.7781,
                "arr_lat": 41.9742,
                "arr_lon": -87.9073,
                "base_progress": 0.34,
                "speed": 452,
                "altitude": 32100,
                "heading": 281,
                "vertical_rate": 0,
            },
            {
                "airline": "Meridian",
                "flight_number": "MR205",
                "logo_key": "meridian",
                "accent": rgb("#ffc95a"),
                "dep_code": "BOS",
                "arr_code": "DCA",
                "dep_lat": 42.3656,
                "dep_lon": -71.0096,
                "arr_lat": 38.8512,
                "arr_lon": -77.0402,
                "base_progress": 0.58,
                "speed": 401,
                "altitude": 28600,
                "heading": 228,
                "vertical_rate": -300,
            },
            {
                "airline": "Harbor Jet",
                "flight_number": "HB611",
                "logo_key": "harbor",
                "accent": rgb("#8bff9a"),
                "dep_code": "ATL",
                "arr_code": "MIA",
                "dep_lat": 33.6407,
                "dep_lon": -84.4277,
                "arr_lat": 25.7959,
                "arr_lon": -80.2870,
                "base_progress": 0.21,
                "speed": 428,
                "altitude": 17800,
                "heading": 162,
                "vertical_rate": 1100,
            },
            {
                "airline": "Ember Regional",
                "flight_number": "EM044",
                "logo_key": "ember",
                "accent": rgb("#ff7a63"),
                "dep_code": "LAX",
                "arr_code": "PHX",
                "dep_lat": 33.9416,
                "dep_lon": -118.4085,
                "arr_lat": 33.4353,
                "arr_lon": -112.0078,
                "base_progress": 0.76,
                "speed": 356,
                "altitude": 9400,
                "heading": 90,
                "vertical_rate": -900,
            },
            {
                "airline": "Slate Air",
                "flight_number": "SA301",
                "logo_key": "slate",
                "accent": rgb("#59e5ff"),
                "dep_code": "SEA",
                "arr_code": "SFO",
                "dep_lat": 47.4502,
                "dep_lon": -122.3088,
                "arr_lat": 37.6213,
                "arr_lon": -122.3790,
                "base_progress": 0.49,
                "speed": 437,
                "altitude": 24000,
                "heading": 181,
                "vertical_rate": 200,
            },
        )

    def snapshot(self, elapsed_s: float) -> list[FlightSample]:
        flights: list[FlightSample] = []
        for index, item in enumerate(self._seed_flights):
            wobble = math.sin(elapsed_s * 0.12 + index * 0.8) * 0.04
            progress = clamp(item["base_progress"] + wobble, 0.03, 0.97)
            aircraft_lat = item["dep_lat"] + (item["arr_lat"] - item["dep_lat"]) * progress
            aircraft_lon = item["dep_lon"] + (item["arr_lon"] - item["dep_lon"]) * progress
            speed_kt = int(item["speed"] + math.sin(elapsed_s * 0.8 + index) * 14)
            altitude_ft = int(item["altitude"] + math.sin(elapsed_s * 0.45 + index * 0.5) * 900)
            vertical_rate = int(item["vertical_rate"] + math.cos(elapsed_s * 0.7 + index) * 150)
            if progress < 0.15:
                status = "Climb"
            elif progress > 0.84:
                status = "Arrive"
            elif altitude_ft < 12000:
                status = "Descend"
            else:
                status = "Cruise"
            flights.append(
                FlightSample(
                    airline=item["airline"],
                    flight_number=item["flight_number"],
                    logo_key=item["logo_key"],
                    accent=item["accent"],
                    dep_code=item["dep_code"],
                    arr_code=item["arr_code"],
                    dep_lat=item["dep_lat"],
                    dep_lon=item["dep_lon"],
                    arr_lat=item["arr_lat"],
                    arr_lon=item["arr_lon"],
                    progress=progress,
                    speed_kt=speed_kt,
                    altitude_ft=altitude_ft,
                    heading_deg=int((item["heading"] + elapsed_s * 2 + index * 7) % 360),
                    vertical_rate_fpm=vertical_rate,
                    status=status,
                    updated_s=int(2 + abs(math.sin(elapsed_s * 1.7 + index)) * 8),
                    aircraft_lat=aircraft_lat,
                    aircraft_lon=aircraft_lon,
                )
            )
        return flights


def draw_background(canvas: PixelCanvas, theme: Theme, elapsed_s: float) -> None:
    top = mix(theme.background, theme.panel, 0.18)
    bottom = mix(theme.background, theme.ocean_glow, 0.85)
    for y in range(canvas.height):
        amount = y / max(1, canvas.height - 1)
        canvas.line([(0, y), (canvas.width, y)], mix(top, bottom, amount))
    sweep = int((math.sin(elapsed_s * 0.35) * 0.5 + 0.5) * 36)
    canvas.rect(Rect(0, 0, canvas.width, 2), fill=mix(theme.cyan, theme.panel_hot, 0.45))
    canvas.rect(Rect(80 + sweep, 0, 10, 2), fill=theme.selection)


def draw_panel(canvas: PixelCanvas, rect: Rect, theme: Theme, accent: Color | None = None) -> None:
    accent = accent or theme.panel_hot
    canvas.rect(rect, fill=theme.panel)
    canvas.rect(Rect(rect.x, rect.y, rect.width, 1), fill=accent)
    canvas.rect(Rect(rect.x, rect.bottom - 1, rect.width, 1), fill=mix(theme.panel, accent, 0.3))
    canvas.rect(rect, outline=mix(theme.panel_alt, accent, 0.55))


def draw_scene_header(
    canvas: PixelCanvas,
    rect: Rect,
    fonts: FontRegistry,
    theme: Theme,
    title: str,
    subtitle: str,
    scene_index: int,
    scene_count: int,
) -> None:
    title_font = fonts.get("headline", 9)
    meta_font = fonts.get("mono", 7)
    canvas.text(rect.x, rect.y - 1, title, title_font, theme.text)
    canvas.text(rect.x, rect.y + 8, subtitle, meta_font, theme.text_dim)
    scene_label = f"{scene_index + 1}/{scene_count}"
    scene_width, _ = measure_text(meta_font, scene_label)
    canvas.text(rect.right - scene_width, rect.y + 1, scene_label, meta_font, theme.text_muted)


def draw_focus_frame(canvas: PixelCanvas, rect: Rect, color: Color) -> None:
    canvas.rect(rect, outline=color)
    canvas.rect(Rect(rect.x + 1, rect.y + 1, max(0, rect.width - 2), max(0, rect.height - 2)), outline=mix(color, (0, 0, 0), 0.5))


def draw_badge(canvas: PixelCanvas, rect: Rect, text: str, theme: Theme, tone: str) -> None:
    colors = {
        "good": theme.lime,
        "warn": theme.amber,
        "error": theme.rose,
        "neutral": theme.cyan,
    }
    accent = colors.get(tone, theme.cyan)
    canvas.rect(rect, fill=mix(theme.panel_alt, accent, 0.22), outline=mix(theme.panel, accent, 0.8))
    font = FontRegistry().get("mono", 7)
    canvas.text_line(rect.inset(2), text.upper(), font, accent, align="center", overflow="clip")


def draw_progress_bar(canvas: PixelCanvas, rect: Rect, theme: Theme, progress: float, accent: Color) -> None:
    progress = clamp(progress, 0.0, 1.0)
    canvas.rect(rect, fill=theme.panel_alt, outline=mix(theme.panel_alt, accent, 0.6))
    fill_width = int((rect.width - 2) * progress)
    if fill_width > 0:
        canvas.rect(Rect(rect.x + 1, rect.y + 1, fill_width, max(0, rect.height - 2)), fill=accent)
    marker_x = rect.x + 1 + fill_width
    canvas.rect(Rect(marker_x, rect.y - 1, 1, rect.height + 2), fill=theme.selection)


def draw_metric_tile(
    canvas: PixelCanvas,
    rect: Rect,
    theme: Theme,
    fonts: FontRegistry,
    icons: dict[str, PixelBitmap],
    icon_key: str,
    label: str,
    value: str,
    accent: Color,
) -> None:
    draw_panel(canvas, rect, theme, accent=accent)
    icon = icons[icon_key]
    icon.draw(canvas, rect.x + 2, rect.y + 3, scale=1)
    label_font = fonts.get("mono", 6)
    value_font = fonts.get("headline", 9)
    canvas.text_line(Rect(rect.x + 14, rect.y + 1, rect.width - 16, 8), label.upper(), label_font, theme.text_dim, overflow="clip")
    canvas.text_line(Rect(rect.x + 14, rect.y + 8, rect.width - 16, rect.height - 8), value, value_font, accent, overflow="clip")


def draw_logo_or_fallback(
    canvas: PixelCanvas,
    rect: Rect,
    logos: dict[str, PixelBitmap],
    fonts: FontRegistry,
    theme: Theme,
    logo_key: str,
    airline: str,
    accent: Color,
) -> None:
    bitmap = logos.get(logo_key)
    draw_panel(canvas, rect, theme, accent=accent)
    if bitmap is None or bitmap.width > rect.width - 4 or bitmap.height > rect.height - 4:
        font_size = max(8, min(18, rect.height + 2))
        font = fonts.get("headline", font_size)
        initial = airline[:1].upper()
        width, height = measure_text(font, initial)
        canvas.text(rect.center_x - width // 2, rect.center_y - height // 2 - 2, initial, font, accent)
        return
    scale = max(1, min((rect.width - 4) // max(1, bitmap.width), (rect.height - 4) // max(1, bitmap.height)))
    draw_x = rect.x + max(0, (rect.width - bitmap.width * scale) // 2)
    draw_y = rect.y + max(0, (rect.height - bitmap.height * scale) // 2)
    bitmap.draw(canvas, draw_x, draw_y, scale=scale)


def draw_route_widget(canvas: PixelCanvas, rect: Rect, theme: Theme, fonts: FontRegistry, flight: FlightSample) -> None:
    label_font = fonts.get("mono", 6)
    code_font = fonts.get("headline", 14 if rect.height >= 16 else 11)
    canvas.text(rect.x, rect.y, "FROM", label_font, theme.text_dim)
    canvas.text(rect.right - 17, rect.y, "TO", label_font, theme.text_dim)
    code_y = rect.y + 6
    canvas.text(rect.x, code_y, flight.dep_code, code_font, theme.text)
    arr_width, _ = measure_text(code_font, flight.arr_code)
    canvas.text(rect.right - arr_width, code_y, flight.arr_code, code_font, theme.text)
    line_y = rect.bottom - 4
    canvas.line([(rect.x + 30, line_y), (rect.right - 30, line_y)], theme.route)
    canvas.line([(rect.right - 32, line_y - 2), (rect.right - 28, line_y), (rect.right - 32, line_y + 2)], theme.route)


def draw_status_strip(canvas: PixelCanvas, rect: Rect, theme: Theme, fonts: FontRegistry, flight: FlightSample) -> None:
    live_rect = Rect(rect.x, rect.y, 22, rect.height)
    status_rect = Rect(rect.x + 24, rect.y, 32, rect.height)
    updated_rect = Rect(rect.x + 58, rect.y, rect.width - 58, rect.height)
    draw_badge(canvas, live_rect, "LIVE", theme, "good")
    tone = "warn" if flight.status in {"Climb", "Descend"} else "neutral"
    draw_badge(canvas, status_rect, flight.status, theme, tone)
    font = fonts.get("mono", 7)
    canvas.text_line(updated_rect, f"{flight.updated_s}s ago", font, theme.text_dim, align="right", overflow="clip")


def draw_flight_header(
    canvas: PixelCanvas,
    rect: Rect,
    logos: dict[str, PixelBitmap],
    fonts: FontRegistry,
    theme: Theme,
    flight: FlightSample,
) -> None:
    logo_rect = Rect(rect.x, rect.y, 30, rect.height)
    text_rect = Rect(rect.x + 34, rect.y, rect.width - 34, rect.height)
    draw_logo_or_fallback(canvas, logo_rect, logos, fonts, theme, flight.logo_key, flight.airline, flight.accent)
    title_font = fonts.get("headline", 11)
    meta_font = fonts.get("mono", 7)
    canvas.text_line(Rect(text_rect.x, text_rect.y, text_rect.width, 11), flight.airline, title_font, theme.text, overflow="ellipsis")
    canvas.text_line(
        Rect(text_rect.x, text_rect.y + 11, text_rect.width, text_rect.height - 11),
        flight.callsign,
        meta_font,
        mix(flight.accent, theme.text, 0.35),
        overflow="clip",
    )


def draw_list_row(
    canvas: PixelCanvas,
    rect: Rect,
    theme: Theme,
    fonts: FontRegistry,
    logos: dict[str, PixelBitmap],
    flight: FlightSample,
    selected: bool,
) -> None:
    row_fill = mix(theme.panel, flight.accent, 0.12 if selected else 0.04)
    canvas.rect(rect, fill=row_fill, outline=mix(theme.panel_alt, flight.accent, 0.45))
    if selected:
        draw_focus_frame(canvas, rect, theme.selection)
    logo_rect = Rect(rect.x + 1, rect.y + 1, 12, rect.height - 2)
    draw_logo_or_fallback(canvas, logo_rect, logos, fonts, theme, flight.logo_key, flight.airline, flight.accent)
    code_font = fonts.get("headline", 9)
    meta_font = fonts.get("mono", 6)
    canvas.text_line(Rect(rect.x + 16, rect.y + 1, 38, 9), flight.route_label, code_font, theme.text, overflow="clip")
    canvas.text_line(Rect(rect.x + 16, rect.y + 9, 28, 8), flight.callsign, meta_font, mix(theme.text_dim, flight.accent, 0.35), overflow="clip")
    canvas.text_line(Rect(rect.right - 32, rect.y + 1, 31, 8), f"{flight.speed_kt}KT", meta_font, flight.accent, align="right", overflow="clip")
    canvas.text_line(Rect(rect.right - 32, rect.y + 9, 31, 8), f"{flight.altitude_ft // 100:03d}", meta_font, theme.text_dim, align="right", overflow="clip")


@dataclass(frozen=True)
class MapViewport:
    center_lat: float
    center_lon: float
    zoom: float
    width: int
    height: int

    def project(self, lat: float, lon: float) -> tuple[int, int]:
        scale = 2.2 * (2 ** self.zoom)
        x = int(self.width / 2 + (lon - self.center_lon) * scale)
        y = int(self.height / 2 - (lat - self.center_lat) * scale * 1.4)
        return x, y


LOW_DETAIL_US = (
    (49.0, -124.0),
    (46.0, -123.0),
    (43.0, -124.0),
    (41.0, -123.0),
    (38.0, -122.0),
    (36.0, -121.0),
    (34.0, -118.0),
    (32.0, -117.0),
    (31.0, -112.0),
    (29.0, -107.0),
    (28.0, -99.0),
    (28.0, -95.0),
    (29.0, -90.0),
    (29.5, -85.0),
    (27.0, -82.0),
    (29.0, -80.0),
    (32.0, -79.0),
    (35.0, -77.0),
    (38.0, -75.0),
    (40.0, -74.0),
    (42.0, -70.0),
    (45.0, -68.0),
    (47.0, -72.0),
    (48.0, -80.0),
    (49.0, -90.0),
    (49.0, -100.0),
    (49.0, -110.0),
    (49.0, -124.0),
)


def draw_map_panel(
    canvas: PixelCanvas,
    rect: Rect,
    theme: Theme,
    fonts: FontRegistry,
    icons: dict[str, PixelBitmap],
    flight: FlightSample,
    zoom: float,
    elapsed_s: float,
) -> None:
    draw_panel(canvas, rect, theme, accent=theme.route)
    viewport = MapViewport(
        center_lat=flight.aircraft_lat,
        center_lon=flight.aircraft_lon,
        zoom=zoom,
        width=rect.width,
        height=rect.height,
    )
    inner = rect.inset(1)
    canvas.rect(inner, fill=theme.ocean)

    grid_phase = int(elapsed_s * 3) % 10
    for offset in range(-4, 5):
        x = inner.center_x + offset * 12 + grid_phase - 5
        canvas.line([(x, inner.y), (x, inner.bottom)], theme.grid)
    for offset in range(-3, 4):
        y = inner.center_y + offset * 10 + grid_phase - 5
        canvas.line([(inner.x, y), (inner.right, y)], theme.grid)

    polygon = []
    for lat, lon in LOW_DETAIL_US:
        x, y = viewport.project(lat, lon)
        polygon.append((rect.x + x, rect.y + y))
    if len(polygon) > 2:
        canvas.polygon(polygon, fill=theme.land, outline=theme.land_highlight)

    dep_x, dep_y = viewport.project(flight.dep_lat, flight.dep_lon)
    arr_x, arr_y = viewport.project(flight.arr_lat, flight.arr_lon)
    ac_x, ac_y = viewport.project(flight.aircraft_lat, flight.aircraft_lon)
    dep_x += rect.x
    dep_y += rect.y
    arr_x += rect.x
    arr_y += rect.y
    ac_x += rect.x
    ac_y += rect.y

    canvas.line([(dep_x, dep_y), (arr_x, arr_y)], mix(theme.route, flight.accent, 0.25))
    pulse_phase = math.sin(elapsed_s * 3.3) * 0.5 + 0.5
    canvas.circle(ac_x, ac_y, 5, outline=pulse(theme.selection, 0.3, 0.9, pulse_phase))
    canvas.circle(ac_x, ac_y, 2, fill=flight.accent)
    icons["pin"].draw(canvas, dep_x - 4, dep_y - 8)
    icons["pin"].draw(canvas, arr_x - 4, arr_y - 8)
    icons["plane"].draw(canvas, ac_x - 4, ac_y - 4)

    meta_font = fonts.get("mono", 6)
    canvas.text(rect.x + 4, rect.bottom - 8, f"ZOOM {zoom:.1f}", meta_font, theme.text_dim)
    canvas.text_line(Rect(rect.right - 28, rect.bottom - 8, 24, 7), flight.route_label, meta_font, theme.text_dim, align="right", overflow="clip")


@dataclass
class DemoContext:
    elapsed_s: float
    scene_elapsed_s: float
    scene_index: int
    scene_count: int
    flights: list[FlightSample]
    selected_flight: FlightSample
    selected_index: int
    auto_rotate: bool
    map_zoom: float


class CoreUIDemo:
    SCENE_ROTATE_SECONDS = 5.0
    FLIGHT_ROTATE_SECONDS = 3.5

    def __init__(self, width: int = 128, height: int = 64) -> None:
        self.width = width
        self.height = height
        self.theme = Theme()
        self.fonts = FontRegistry()
        self.icons = build_icon_registry(self.theme)
        self.logos = build_logo_registry()
        self.provider = MockFlightProvider()
        self.canvas = PixelCanvas(width, height)
        self.scene_index = 0
        self.selected_index = 0
        self.auto_rotate = True
        self.scene_started_at = 0.0
        self.last_flight_cycle_at = 0.0
        self.map_zoom = 1.65
        self._input_bound = False
        self.scenes = (
            ("Overview", "Scene manager and controls", self.render_overview_scene),
            ("Type Lab", "Multiple sizes and overflow", self.render_typography_scene),
            ("Asset Lab", "Icons, logos, and fallbacks", self.render_assets_scene),
            ("Widget Lab", "Badges, metrics, and progress", self.render_widget_scene),
            ("Hero", "Focused single-flight composition", self.render_hero_scene),
            ("List", "Dense list rows and selection", self.render_list_scene),
            ("Map", "Viewport, pins, and focus", self.render_map_scene),
            ("States", "Loading, stale, and error UI", self.render_state_scene),
        )

    def bind_inputs(self, matrix: InteractiveLEDMatrix) -> None:
        if self._input_bound:
            return
        root = getattr(matrix, "root", None)
        if root is None:
            return
        root.bind("<Right>", lambda _event: self.next_scene())
        root.bind("<Left>", lambda _event: self.previous_scene())
        root.bind("<Down>", lambda _event: self.next_flight())
        root.bind("<Up>", lambda _event: self.previous_flight())
        root.bind("<space>", lambda _event: self.toggle_auto_rotate())
        root.bind("m", lambda _event: self.next_scene())
        root.bind("a", lambda _event: self.toggle_auto_rotate())
        root.bind("=", lambda _event: self.adjust_zoom(0.15))
        root.bind("+", lambda _event: self.adjust_zoom(0.15))
        root.bind("-", lambda _event: self.adjust_zoom(-0.15))
        for index in range(min(9, len(self.scenes))):
            root.bind(str(index + 1), lambda _event, value=index: self.select_scene(value))
        self._input_bound = True

    def next_scene(self) -> None:
        self.select_scene((self.scene_index + 1) % len(self.scenes))

    def previous_scene(self) -> None:
        self.select_scene((self.scene_index - 1) % len(self.scenes))

    def select_scene(self, index: int) -> None:
        self.scene_index = index % len(self.scenes)
        self.scene_started_at = 0.0

    def next_flight(self) -> None:
        self.selected_index = (self.selected_index + 1) % len(self.provider.snapshot(0.0))

    def previous_flight(self) -> None:
        self.selected_index = (self.selected_index - 1) % len(self.provider.snapshot(0.0))

    def toggle_auto_rotate(self) -> None:
        self.auto_rotate = not self.auto_rotate

    def adjust_zoom(self, delta: float) -> None:
        self.map_zoom = clamp(self.map_zoom + delta, 0.6, 3.2)

    def _build_context(self, elapsed_s: float) -> DemoContext:
        flights = self.provider.snapshot(elapsed_s)
        selected_index = self.selected_index % len(flights)
        return DemoContext(
            elapsed_s=elapsed_s,
            scene_elapsed_s=0.0 if self.scene_started_at == 0.0 else elapsed_s - self.scene_started_at,
            scene_index=self.scene_index,
            scene_count=len(self.scenes),
            flights=flights,
            selected_flight=flights[selected_index],
            selected_index=selected_index,
            auto_rotate=self.auto_rotate,
            map_zoom=self.map_zoom,
        )

    def update(self, elapsed_s: float) -> DemoContext:
        if self.scene_started_at == 0.0:
            self.scene_started_at = elapsed_s
        if self.auto_rotate and elapsed_s - self.scene_started_at >= self.SCENE_ROTATE_SECONDS:
            self.next_scene()
            self.scene_started_at = elapsed_s
        if self.auto_rotate and elapsed_s - self.last_flight_cycle_at >= self.FLIGHT_ROTATE_SECONDS:
            self.next_flight()
            self.last_flight_cycle_at = elapsed_s
        return self._build_context(elapsed_s)

    def render_to_canvas(self, elapsed_s: float) -> PixelCanvas:
        context = self.update(elapsed_s)
        self.canvas.clear(self.theme.background)
        draw_background(self.canvas, self.theme, elapsed_s)
        _name, subtitle, renderer = self.scenes[self.scene_index]
        renderer(context)
        footer_font = self.fonts.get("mono", 6)
        auto_label = "AUTO" if self.auto_rotate else "MAN"
        canvas = self.canvas
        canvas.text(3, self.height - 7, auto_label, footer_font, self.theme.text_muted)
        for index in range(len(self.scenes)):
            x = self.width - 4 - index * 4
            color = self.theme.selection if index == self.scene_index else self.theme.text_muted
            canvas.pixel(x, self.height - 4, color)
            canvas.pixel(x, self.height - 3, color)
        return self.canvas

    def render_to_matrix(self, matrix: LEDMatrix, elapsed_s: float) -> None:
        self.render_to_canvas(elapsed_s).sync_to_matrix(matrix)

    def render_overview_scene(self, context: DemoContext) -> None:
        draw_scene_header(
            self.canvas,
            Rect(4, 4, 120, 12),
            self.fonts,
            self.theme,
            "CORE UI DEMO",
            "Right/Left scenes  Up/Down flights",
            context.scene_index,
            context.scene_count,
        )
        body_font = self.fonts.get("mono", 7)
        tiles = [
            ("Type", "text sizes"),
            ("Asset", "icons logos"),
            ("Widget", "bars metrics"),
            ("Hero", "single flight"),
            ("List", "dense rows"),
            ("Map", "pins zoom"),
            ("State", "loading errors"),
        ]
        start_y = 18
        for index, (name, desc) in enumerate(tiles):
            y = start_y + index * 6
            accent = self.theme.cyan if index % 2 == 0 else self.theme.amber
            self.canvas.rect(Rect(6, y + 1, 2, 2), fill=accent)
            self.canvas.text(11, y, name, body_font, self.theme.text)
            self.canvas.text(36, y, desc, body_font, self.theme.text_dim)
        self.canvas.text(4, 58, "Space: auto   +/-: map zoom", body_font, self.theme.text_muted)

    def render_typography_scene(self, context: DemoContext) -> None:
        draw_scene_header(
            self.canvas,
            Rect(4, 4, 120, 12),
            self.fonts,
            self.theme,
            "TYPOGRAPHY LAB",
            "Sizes, mono numerics, clip, ellipsis, marquee",
            context.scene_index,
            context.scene_count,
        )
        labels = [
            ("MICRO", self.fonts.get("mono", 6), self.theme.text_muted),
            ("SMALL", self.fonts.get("body", 8), self.theme.text_dim),
            ("MEDIUM", self.fonts.get("headline", 10), self.theme.text),
            ("HERO 462KT", self.fonts.get("headline", 15), self.theme.cyan),
        ]
        y = 18
        for text, font, color in labels:
            height = measure_text(font, text)[1] + 1
            self.canvas.text(6, y, text, font, color)
            y += height + 1
        overflow_rect = Rect(70, 18, 52, 14)
        draw_panel(self.canvas, overflow_rect, self.theme, accent=self.theme.amber)
        self.canvas.text(72, 20, "FIT", self.fonts.get("mono", 6), self.theme.amber)
        self.canvas.text_line(
            Rect(72, 26, 48, 5),
            "MERIDIAN REGIONAL EXPRESS",
            self.fonts.get("mono", 6),
            self.theme.text,
            overflow="ellipsis",
        )
        marquee_rect = Rect(6, 47, 116, 12)
        draw_panel(self.canvas, marquee_rect, self.theme, accent=self.theme.cyan)
        self.canvas.text(8, 49, "MARQ", self.fonts.get("mono", 6), self.theme.cyan)
        self.canvas.text_line(
            Rect(28, 48, 90, 9),
            "SLATE AIR  SA128  JFK -> ORD  ALT 32100  SPD 452KT",
            self.fonts.get("mono", 7),
            self.theme.text,
            overflow="marquee",
            tick=int(context.elapsed_s * 18),
        )

    def render_assets_scene(self, context: DemoContext) -> None:
        draw_scene_header(
            self.canvas,
            Rect(4, 4, 120, 12),
            self.fonts,
            self.theme,
            "ASSET LAB",
            "Custom icon registry, airline logos, fallback",
            context.scene_index,
            context.scene_count,
        )
        icon_keys = ("plane", "speed", "altitude", "heading", "clock", "pin")
        for index, key in enumerate(icon_keys):
            tile = Rect(4 + (index % 3) * 20, 18 + (index // 3) * 14, 18, 12)
            draw_panel(self.canvas, tile, self.theme, accent=self.theme.cyan if index % 2 == 0 else self.theme.amber)
            self.icons[key].draw(self.canvas, tile.x + 4, tile.y + 2)
        logo_rects = (
            Rect(66, 18, 27, 16),
            Rect(96, 18, 27, 16),
            Rect(66, 38, 27, 16),
            Rect(96, 38, 27, 16),
        )
        logo_keys = ("slate", "meridian", "harbor", "ember")
        airline_names = ("Slate Air", "Meridian", "Harbor Jet", "Ember")
        accents = (self.theme.cyan, self.theme.amber, self.theme.lime, self.theme.coral)
        for tile, key, airline, accent in zip(logo_rects, logo_keys, airline_names, accents):
            draw_logo_or_fallback(self.canvas, tile, self.logos, self.fonts, self.theme, key, airline, accent)
        draw_logo_or_fallback(self.canvas, Rect(66, 56, 14, 8), self.logos, self.fonts, self.theme, "missing", "Ghost Air", self.theme.rose)
        self.canvas.text(83, 57, "fallback", self.fonts.get("mono", 6), self.theme.text_dim)

    def render_widget_scene(self, context: DemoContext) -> None:
        draw_scene_header(
            self.canvas,
            Rect(4, 4, 120, 12),
            self.fonts,
            self.theme,
            "WIDGET LAB",
            "Status, progress, route, metric tiles",
            context.scene_index,
            context.scene_count,
        )
        flight = context.selected_flight
        draw_status_strip(self.canvas, Rect(4, 18, 120, 8), self.theme, self.fonts, flight)
        draw_progress_bar(self.canvas, Rect(4, 28, 120, 7), self.theme, flight.progress, flight.accent)
        draw_route_widget(self.canvas, Rect(4, 36, 120, 12), self.theme, self.fonts, flight)
        draw_metric_tile(self.canvas, Rect(4, 49, 38, 14), self.theme, self.fonts, self.icons, "speed", "SPD", f"{flight.speed_kt}", flight.accent)
        draw_metric_tile(self.canvas, Rect(45, 49, 38, 14), self.theme, self.fonts, self.icons, "altitude", "ALT", f"{flight.altitude_ft // 100:03d}", self.theme.lime)
        draw_metric_tile(self.canvas, Rect(86, 49, 38, 14), self.theme, self.fonts, self.icons, "heading", "HDG", f"{flight.heading_deg:03d}", self.theme.amber)

    def render_hero_scene(self, context: DemoContext) -> None:
        flight = context.selected_flight
        draw_scene_header(
            self.canvas,
            Rect(4, 4, 120, 12),
            self.fonts,
            self.theme,
            "HERO VIEW",
            "Single focused flight composition",
            context.scene_index,
            context.scene_count,
        )
        draw_flight_header(self.canvas, Rect(4, 18, 120, 18), self.logos, self.fonts, self.theme, flight)
        draw_status_strip(self.canvas, Rect(4, 38, 120, 8), self.theme, self.fonts, flight)
        draw_route_widget(self.canvas, Rect(4, 47, 120, 11), self.theme, self.fonts, flight)
        draw_progress_bar(self.canvas, Rect(4, 59, 120, 4), self.theme, flight.progress, flight.accent)
        self.canvas.text(86, 20, f"{flight.speed_kt}KT", self.fonts.get("headline", 11), flight.accent)
        self.canvas.text(85, 29, f"{flight.altitude_ft // 100}FL", self.fonts.get("mono", 7), self.theme.text_dim)

    def render_list_scene(self, context: DemoContext) -> None:
        draw_scene_header(
            self.canvas,
            Rect(4, 4, 120, 12),
            self.fonts,
            self.theme,
            "LIST VIEW",
            "Dense rows with selection stress test",
            context.scene_index,
            context.scene_count,
        )
        start_y = 17
        row_height = 11
        for index, flight in enumerate(context.flights[:4]):
            draw_list_row(
                self.canvas,
                Rect(4, start_y + index * 12, 120, row_height),
                self.theme,
                self.fonts,
                self.logos,
                flight,
                selected=index == context.selected_index % 4,
            )

    def render_map_scene(self, context: DemoContext) -> None:
        draw_scene_header(
            self.canvas,
            Rect(4, 4, 120, 12),
            self.fonts,
            self.theme,
            "MAP VIEW",
            "Viewport focus, zoom, pins, route overlay",
            context.scene_index,
            context.scene_count,
        )
        draw_map_panel(
            self.canvas,
            Rect(4, 18, 120, 46),
            self.theme,
            self.fonts,
            self.icons,
            context.selected_flight,
            context.map_zoom,
            context.elapsed_s,
        )

    def render_state_scene(self, context: DemoContext) -> None:
        draw_scene_header(
            self.canvas,
            Rect(4, 4, 120, 12),
            self.fonts,
            self.theme,
            "STATE LAB",
            "Loading, no-data, stale, and failure states",
            context.scene_index,
            context.scene_count,
        )
        phase = int(context.elapsed_s // 2) % 4
        card = Rect(8, 20, 112, 34)
        if phase == 0:
            draw_panel(self.canvas, card, self.theme, accent=self.theme.cyan)
            self.icons["live"].draw(self.canvas, 14, 31)
            self.canvas.text(30, 26, "Loading flights", self.fonts.get("headline", 10), self.theme.text)
            draw_progress_bar(self.canvas, Rect(30, 39, 72, 6), self.theme, (math.sin(context.elapsed_s * 2) * 0.5 + 0.5), self.theme.cyan)
        elif phase == 1:
            draw_panel(self.canvas, card, self.theme, accent=self.theme.amber)
            self.icons["warn"].draw(self.canvas, 14, 31)
            self.canvas.text(30, 26, "No nearby flights", self.fonts.get("headline", 10), self.theme.text)
            self.canvas.text(30, 38, "Expand range or wait", self.fonts.get("mono", 7), self.theme.text_dim)
        elif phase == 2:
            draw_panel(self.canvas, card, self.theme, accent=self.theme.amber)
            self.icons["clock"].draw(self.canvas, 14, 31)
            self.canvas.text(30, 26, "Feed stale", self.fonts.get("headline", 10), self.theme.text)
            self.canvas.text(30, 38, "Last update 42s ago", self.fonts.get("mono", 7), self.theme.text_dim)
        else:
            draw_panel(self.canvas, card, self.theme, accent=self.theme.rose)
            self.icons["error"].draw(self.canvas, 14, 31)
            self.canvas.text(30, 26, "Receiver offline", self.fonts.get("headline", 10), self.theme.text)
            self.canvas.text(30, 38, "Retrying connection", self.fonts.get("mono", 7), self.theme.text_dim)


def run_core_ui_demo(
    matrix: InteractiveLEDMatrix | None = None,
    options: RGBMatrixOptions | None = None,
    auto_close_ms: int | None = None,
) -> None:
    options = options or RGBMatrixOptions(limit_refresh_rate_hz=20)
    matrix = matrix or MockRGBMatrix(options)
    auto_close_value = os.environ.get("CORE_UI_AUTOCLOSE_MS")
    if auto_close_ms is None and auto_close_value:
        auto_close_ms = int(auto_close_value)

    demo = CoreUIDemo(matrix.width, matrix.height)
    demo.bind_inputs(matrix)
    start = time.monotonic()
    deadline = start + (auto_close_ms / 1000.0) if auto_close_ms and auto_close_ms > 0 else None
    frame_delay = 1.0 / max(1, options.limit_refresh_rate_hz)

    while True:
        if matrix.closed:
            break
        if deadline is not None and time.monotonic() >= deadline:
            matrix.close()
            break

        frame_start = time.monotonic()
        demo.render_to_matrix(matrix, frame_start - start)
        if not matrix.process():
            break

        sleep_time = frame_delay - (time.monotonic() - frame_start)
        if sleep_time > 0:
            time.sleep(sleep_time)


__all__ = [
    "CoreUIDemo",
    "FlightSample",
    "FontRegistry",
    "MapViewport",
    "MockFlightProvider",
    "PixelBitmap",
    "PixelCanvas",
    "Rect",
    "Theme",
    "build_icon_registry",
    "build_logo_registry",
    "fit_text",
    "measure_text",
    "run_core_ui_demo",
]
