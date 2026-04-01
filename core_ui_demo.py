#!/usr/bin/env python3
"""Core UI demo launcher with Font, Layout, Image, Marquee, Spinner, and Map pages."""

from __future__ import annotations

import ctypes
import functools
import gzip
import json
import math
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

try:
    import tkinter as tk
    from tkinter import colorchooser
    from tkinter import filedialog
except Exception:  # pragma: no cover - tkinter is optional in non-mock environments.
    tk = None
    colorchooser = None
    filedialog = None

try:
    from mapbox_vector_tile import decode as decode_mvt
except Exception:  # pragma: no cover - dependency may be missing during development.
    decode_mvt = None

from standard_led_matrix_interface import RGBMatrixOptions
from ui import (
    App,
    Column,
    FONT_3X5,
    FONT_4X6,
    FONT_5X7,
    Image,
    LoadingSpinner,
    Map,
    Marquee,
    Panel,
    Row,
    Text,
    colors,
    load_png_image_frame,
)
from ui.core.image_asset import ImageFrame
from ui.fonts.import_util import ALNUM_PUNCT_94

Color = tuple[int, int, int]


@dataclass
class MapStyle:
    bg: Color = (18, 18, 20)
    land: Color = (16, 52, 16)
    park: Color = (32, 108, 32)
    building: Color = (255, 0, 0)
    water: Color = (0, 86, 151)
    road: Color = (130, 130, 132)
    border: Color = (255, 255, 255)


def _clone_map_style(style: MapStyle) -> MapStyle:
    return MapStyle(
        bg=style.bg,
        land=style.land,
        park=style.park,
        building=style.building,
        water=style.water,
        road=style.road,
        border=style.border,
    )


_MAP_STYLE_PRESETS: dict[str, MapStyle] = {
    "Balanced": MapStyle(),
    "Muted Day": MapStyle(
        bg=(22, 24, 24),
        land=(22, 66, 22),
        park=(36, 116, 36),
        building=(130, 132, 130),
        water=(28, 108, 220),
        road=(165, 165, 165),
        border=(235, 235, 235),
    ),
    "Night Contrast": MapStyle(
        bg=(10, 10, 12),
        land=(12, 38, 12),
        park=(28, 92, 28),
        building=(112, 116, 112),
        water=(16, 72, 184),
        road=(182, 182, 182),
        border=(255, 255, 255),
    ),
    "Paper Map": MapStyle(
        bg=(24, 24, 22),
        land=(30, 70, 24),
        park=(52, 126, 42),
        building=(142, 144, 138),
        water=(38, 120, 220),
        road=(176, 176, 170),
        border=(245, 245, 240),
    ),
}


def _style_to_dict(style: MapStyle) -> dict[str, list[int]]:
    return {
        "bg": list(style.bg),
        "land": list(style.land),
        "park": list(style.park),
        "building": list(style.building),
        "water": list(style.water),
        "road": list(style.road),
        "border": list(style.border),
    }


def _set_map_style(state: "AppState", style: MapStyle) -> None:
    state.map_style = _clone_map_style(style)
    state.style_dirty = True


def _queue_map_reload(state: "AppState") -> None:
    # Drop the current tile and request a fresh fetch for updated view settings.
    state.map_tile_data = None
    state.map_error = None
    state.map_loading = False
    state.map_request = None
    state.style_dirty = True


def _view_step_degrees(zoom: int) -> float:
    # Move by 20% of the current tile span at this zoom level.
    return max(0.01, (360.0 / (2**max(1, zoom))) * 0.2)


def _open_map_style_editor(root: Any, state: "AppState", holder: dict[str, Any]) -> None:
    if tk is None:
        return

    existing = holder.get("window")
    if existing is not None and bool(existing.winfo_exists()):
        existing.lift()
        existing.focus_force()
        return

    window = tk.Toplevel(root)
    window.title("Map Style Editor")
    window.configure(bg="#111111")
    window.resizable(False, True)
    holder["window"] = window

    fields = ["bg", "land", "park", "building", "water", "road", "border"]
    color_vars: dict[str, Any] = {}
    color_buttons: dict[str, Any] = {}
    lat_var = tk.StringVar(value=f"{state.map_center_lat:.6f}")
    lon_var = tk.StringVar(value=f"{state.map_center_lon:.6f}")
    zoom_var = tk.IntVar(value=state.map_zoom)

    title = tk.Label(window, text="Live Map Colors", fg="#F0F0F0", bg="#111111")
    title.grid(row=0, column=0, columnspan=6, sticky="w", padx=8, pady=(8, 4))

    preset_names = list(_MAP_STYLE_PRESETS.keys())
    preset_var = tk.StringVar(value=preset_names[0])

    def sync_from_state() -> None:
        for field_name in fields:
            color = getattr(state.map_style, field_name)
            hex_color = f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"
            color_vars[field_name].set(hex_color)
            btn = color_buttons.get(field_name)
            if btn is not None:
                btn.configure(bg=hex_color, activebackground=hex_color)

    def apply_ui_to_state() -> None:
        for field_name in fields:
            raw = color_vars[field_name].get().strip()
            if len(raw) == 7 and raw.startswith("#"):
                try:
                    color = (int(raw[1:3], 16), int(raw[3:5], 16), int(raw[5:7], 16))
                except ValueError:
                    continue
                setattr(state.map_style, field_name, color)
        state.style_dirty = True

    def pick_color(field_name: str) -> None:
        if colorchooser is None:
            return
        current = color_vars[field_name].get().strip() or "#000000"
        chosen = colorchooser.askcolor(color=current, parent=window, title=f"Pick {field_name}")
        if chosen is None or chosen[1] is None:
            return
        color_vars[field_name].set(chosen[1])
        apply_ui_to_state()
        sync_from_state()

    def on_color_entry_commit(_event: Any | None = None) -> None:
        apply_ui_to_state()
        sync_from_state()

    def apply_view_to_state() -> None:
        try:
            lat_val = float(lat_var.get().strip())
            lon_val = float(lon_var.get().strip())
        except ValueError:
            sync_view_from_state()
            return
        state.map_center_lat = max(-85.0511, min(85.0511, lat_val))
        state.map_center_lon = max(-180.0, min(180.0, lon_val))
        state.map_zoom = max(1, min(16, int(zoom_var.get())))
        _queue_map_reload(state)
        sync_view_from_state()

    def sync_view_from_state() -> None:
        lat_var.set(f"{state.map_center_lat:.6f}")
        lon_var.set(f"{state.map_center_lon:.6f}")
        zoom_var.set(int(state.map_zoom))

    def pan(dx: float, dy: float) -> None:
        step = _view_step_degrees(state.map_zoom)
        state.map_center_lon = max(-180.0, min(180.0, state.map_center_lon + (dx * step)))
        state.map_center_lat = max(-85.0511, min(85.0511, state.map_center_lat + (dy * step)))
        sync_view_from_state()
        _queue_map_reload(state)

    def zoom(delta: int) -> None:
        state.map_zoom = max(1, min(16, state.map_zoom + delta))
        sync_view_from_state()
        _queue_map_reload(state)

    def apply_preset() -> None:
        chosen = preset_var.get()
        preset = _MAP_STYLE_PRESETS.get(chosen)
        if preset is None:
            return
        _set_map_style(state, preset)
        sync_from_state()

    def copy_json() -> None:
        payload = json.dumps(_style_to_dict(state.map_style), indent=2)
        root.clipboard_clear()
        root.clipboard_append(payload)

    def save_json() -> None:
        payload = json.dumps(_style_to_dict(state.map_style), indent=2)
        if filedialog is None:
            with open("map-style.json", "w", encoding="utf-8") as handle:
                handle.write(payload)
            return
        destination = filedialog.asksaveasfilename(
            parent=window,
            title="Save map style",
            defaultextension=".json",
            filetypes=(("JSON files", "*.json"), ("All files", "*.*")),
            initialfile="map-style.json",
        )
        if not destination:
            return
        with open(destination, "w", encoding="utf-8") as handle:
            handle.write(payload)

    preset_menu = tk.OptionMenu(window, preset_var, *preset_names)
    preset_menu.configure(bg="#222222", fg="#F0F0F0", highlightthickness=0)
    preset_menu.grid(row=1, column=0, columnspan=3, sticky="ew", padx=8, pady=4)

    tk.Button(window, text="Apply Preset", command=apply_preset).grid(
        row=1, column=3, columnspan=3, sticky="ew", padx=8, pady=4
    )

    row = 2
    for field_name in fields:
        tk.Label(window, text=field_name.upper(), fg="#D0D0D0", bg="#111111").grid(
            row=row, column=0, sticky="w", padx=8, pady=(8, 2)
        )
        color_var = tk.StringVar(value="#000000")
        color_vars[field_name] = color_var
        color_btn = tk.Button(
            window,
            text="Pick",
            width=8,
            command=lambda name=field_name: pick_color(name),
        )
        color_btn.grid(row=row, column=1, sticky="w", padx=(0, 6), pady=(8, 2))
        color_buttons[field_name] = color_btn
        entry = tk.Entry(window, textvariable=color_var, width=12)
        entry.grid(row=row, column=2, columnspan=2, sticky="w", padx=(0, 6), pady=(8, 2))
        entry.bind("<Return>", on_color_entry_commit)
        tk.Button(window, text="Apply", command=on_color_entry_commit).grid(
            row=row, column=4, columnspan=2, sticky="ew", padx=8, pady=(8, 2)
        )
        row += 1

    tk.Button(window, text="Copy JSON", command=copy_json).grid(
        row=row, column=0, columnspan=3, sticky="ew", padx=8, pady=(8, 8)
    )
    tk.Button(window, text="Save JSON", command=save_json).grid(
        row=row, column=3, columnspan=3, sticky="ew", padx=8, pady=(8, 8)
    )

    row += 1
    tk.Label(window, text="MAP VIEW", fg="#D0D0D0", bg="#111111").grid(
        row=row, column=0, columnspan=6, sticky="w", padx=8, pady=(8, 2)
    )
    row += 1
    tk.Button(window, text="Up", command=lambda: pan(0.0, 1.0)).grid(
        row=row, column=2, columnspan=2, sticky="ew", padx=8, pady=2
    )
    row += 1
    tk.Button(window, text="Left", command=lambda: pan(-1.0, 0.0)).grid(
        row=row, column=0, columnspan=2, sticky="ew", padx=8, pady=2
    )
    tk.Button(window, text="Right", command=lambda: pan(1.0, 0.0)).grid(
        row=row, column=4, columnspan=2, sticky="ew", padx=8, pady=2
    )
    tk.Button(window, text="Down", command=lambda: pan(0.0, -1.0)).grid(
        row=row, column=2, columnspan=2, sticky="ew", padx=8, pady=2
    )
    row += 1
    tk.Button(window, text="Zoom +", command=lambda: zoom(1)).grid(
        row=row, column=1, columnspan=2, sticky="ew", padx=8, pady=2
    )
    tk.Button(window, text="Zoom -", command=lambda: zoom(-1)).grid(
        row=row, column=3, columnspan=2, sticky="ew", padx=8, pady=2
    )

    row += 1
    tk.Label(window, text="LAT", fg="#A8A8A8", bg="#111111").grid(
        row=row, column=0, sticky="e", padx=(8, 2), pady=1
    )
    lat_entry = tk.Entry(window, textvariable=lat_var, width=16)
    lat_entry.grid(row=row, column=1, columnspan=3, sticky="w", padx=(0, 6), pady=1)
    lat_entry.bind("<Return>", lambda _event: apply_view_to_state())
    tk.Button(window, text="Apply", command=apply_view_to_state).grid(
        row=row, column=4, columnspan=2, sticky="ew", padx=8, pady=1
    )

    row += 1
    tk.Label(window, text="LON", fg="#A8A8A8", bg="#111111").grid(
        row=row, column=0, sticky="e", padx=(8, 2), pady=1
    )
    lon_entry = tk.Entry(window, textvariable=lon_var, width=16)
    lon_entry.grid(row=row, column=1, columnspan=3, sticky="w", padx=(0, 6), pady=1)
    lon_entry.bind("<Return>", lambda _event: apply_view_to_state())
    tk.Button(window, text="Apply", command=apply_view_to_state).grid(
        row=row, column=4, columnspan=2, sticky="ew", padx=8, pady=1
    )

    row += 1
    tk.Label(window, text="ZOOM", fg="#A8A8A8", bg="#111111").grid(
        row=row, column=0, sticky="e", padx=(8, 2), pady=1
    )
    tk.Scale(
        window,
        from_=1,
        to=16,
        orient="horizontal",
        showvalue=True,
        length=320,
        resolution=1,
        variable=zoom_var,
        command=lambda _value: apply_view_to_state(),
    ).grid(row=row, column=1, columnspan=5, sticky="w", padx=(0, 6), pady=1)

    sync_from_state()
    sync_view_from_state()

    def on_close() -> None:
        holder["window"] = None
        window.destroy()

    window.protocol("WM_DELETE_WINDOW", on_close)


@dataclass
class AppState:
    page_index: int = 0
    marquee_x: float = 0.0
    marquee_y: float = 0.0
    spinner_phase: float = 0.0
    image_index: int = 0
    map_center_lat: float = 41.4993
    map_center_lon: float = -81.6944
    map_zoom: int = 12
    map_view_aspect: float = 1.0
    map_tile_data: dict[str, Any] | None = None
    map_loading: bool = False
    map_error: str | None = None
    map_request: Future[dict[str, Any]] | None = None
    map_style: MapStyle = field(default_factory=MapStyle)
    style_dirty: bool = False


DEMO_PAGES = [
    "font-demo",
    "layout-demo",
    "image-demo",
    "marquee-demo",
    "spinner-demo",
    "map-demo",
]
MARQUEE_X_PIXELS_PER_SECOND = 12
MARQUEE_Y_PIXELS_PER_SECOND = 10
SPINNER_PHASE_STEPS_PER_SECOND = 12
TARGET_REFRESH_HZ = 120
MISS_LOG_INTERVAL_S = 1.0

MAPBOX_TILESET = "mapbox.mapbox-streets-v8"
MAPBOX_STYLE = "mapbox://styles/mapbox/streets-v12@00"
MAPBOX_STYLE_OWNER = "jackstoller"
MAPBOX_TOKEN = os.environ.get("MAPBOX_TOKEN", "")
ASSETS_DIR = Path(__file__).resolve().with_name("assets")
IMAGE_SWITCH_SECONDS = 1.25
AUTO_PAGE_SECONDS = 6.0


def _read_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


def _default_hardware_mapping() -> str:
    env_value = os.environ.get("FLIGHT_SLATE_HARDWARE_MAPPING")
    if env_value and env_value.strip():
        return env_value.strip()
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        # Headless Linux boxes (Pi) should default to the physical matrix.
        return "adafruit-hat-pwm"
    return "mock"


def _build_matrix_options() -> RGBMatrixOptions:
    return RGBMatrixOptions(
        rows=_read_int_env("FLIGHT_SLATE_MATRIX_ROWS", 64),
        cols=_read_int_env("FLIGHT_SLATE_MATRIX_COLS", 128),
        chain_length=_read_int_env("FLIGHT_SLATE_MATRIX_CHAIN", 1),
        parallel=_read_int_env("FLIGHT_SLATE_MATRIX_PARALLEL", 1),
        brightness=max(1, min(100, _read_int_env("FLIGHT_SLATE_MATRIX_BRIGHTNESS", 100))),
        hardware_mapping=_default_hardware_mapping(),
        pwm_bits=max(1, min(11, _read_int_env("FLIGHT_SLATE_MATRIX_PWM_BITS", 11))),
        limit_refresh_rate_hz=max(1, _read_int_env("FLIGHT_SLATE_REFRESH_HZ", TARGET_REFRESH_HZ)),
    )


@functools.lru_cache(maxsize=1)
def _load_asset_png_frames() -> list[tuple[str, ImageFrame]]:
    if not ASSETS_DIR.exists():
        return []

    entries: list[tuple[str, ImageFrame]] = []
    for path in sorted(ASSETS_DIR.rglob("*")):
        if not path.is_file() or path.suffix.lower() != ".png":
            continue
        try:
            frame = load_png_image_frame(path)
        except Exception:
            continue
        rel_name = str(path.relative_to(ASSETS_DIR))
        entries.append((rel_name, frame))
    return entries


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

    def __exit__(self, exc_type, exc, tb) -> None:
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
            # Finish with a short spin to avoid timer quantization misses.
            while time.perf_counter() < deadline:
                pass
            return


def clamp_page(index: int) -> int:
    return max(0, min(index, len(DEMO_PAGES) - 1))


def _build_font_demo_page() -> Panel:
    return Panel(
        padding=2,
        bg=colors.BLACK,
        border=colors.BLUE,
        child=Column(
            gap=1,
            sizes=[8, 10, 10, 34],
            children=[
                Text(
                    align="center",
                    font=FONT_5X7,
                    overflow="clip",
                    text="FONT DEMO",
                ),
                Text(
                    align="left",
                    font=FONT_3X5,
                    overflow="wrap",
                    text="3x5: ABC123!?",
                ),
                Text(
                    align="left",
                    font=FONT_4X6,
                    overflow="wrap",
                    text="4x6: MERIDIAN",
                ),
                Text(
                    align="left",
                    font=FONT_5X7,
                    overflow="wrap",
                    text=f"{ALNUM_PUNCT_94}",
                ),
            ],
        ),
    )


def _build_layout_demo_page() -> Panel:
    return Panel(
        padding=1,
        bg=colors.BLACK,
        border=colors.CYAN,
        child=Column(
            gap=1,
            sizes=[8, 54],
            children=[
                Text(
                    align="center",
                    font=FONT_5X7,
                    overflow="clip",
                    text="ROW/COLUMN",
                ),
                Row(
                    gap=1,
                    sizes=[10, 90],
                    children=[
                        Panel(bg=colors.BLUE, border=colors.WHITE, child=None),
                        Column(
                            gap=1,
                            sizes=[1, 1, 1],
                            children=[
                                Row(
                                    gap=1,
                                    sizes=[1, 1],
                                    children=[
                                        Panel(bg=colors.CYAN, border=colors.WHITE, child=None),
                                        Panel(bg=colors.DIM_WHITE, border=colors.WHITE, child=None),
                                    ],
                                ),
                                Row(
                                    gap=1,
                                    sizes=[10, 90],
                                    children=[
                                        Panel(bg=colors.BLUE, border=colors.WHITE, child=None),
                                        Panel(bg=colors.DIM_WHITE, border=colors.WHITE, child=None),
                                    ],
                                ),
                                Row(
                                    gap=1,
                                    sizes=[1, 1, 1],
                                    children=[
                                        Panel(bg=colors.CYAN, border=colors.WHITE, child=None),
                                        Panel(bg=colors.BLUE, border=colors.WHITE, child=None),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        ),
    )


def _build_image_demo_page(state: AppState) -> Panel:
    images = _load_asset_png_frames()
    if not images:
        image_body: Panel | Text = Panel(
            padding=1,
            bg=colors.BLACK,
            border=colors.CYAN,
            child=Text(
                align="center",
                font=FONT_3X5,
                overflow="wrap",
                text="NO PNG IN ASSETS",
                color=colors.WHITE,
            ),
        )
        image_label = Text(
            align="center",
            font=FONT_3X5,
            overflow="clip",
            text="ASSETS/*.PNG",
            color=colors.DIM_WHITE,
        )
    else:
        selected_index = state.image_index % len(images)
        rel_name, frame = images[selected_index]
        label = f"{selected_index + 1}/{len(images)} {Path(rel_name).stem.upper()}"
        image_body = Panel(
            padding=1,
            bg=colors.BLACK,
            border=colors.CYAN,
            child=Image(frame=frame, fit="original", bg=colors.BLACK),
        )
        image_label = Text(
            align="left",
            font=FONT_3X5,
            overflow="clip",
            text=label,
            color=colors.DIM_WHITE,
        )

    return Panel(
        padding=1,
        bg=colors.BLACK,
        border=colors.WHITE,
        child=Column(
            gap=1,
            sizes=[8, 8, 46],
            children=[
                Text(
                    align="center",
                    font=FONT_5X7,
                    overflow="clip",
                    text="IMAGE",
                ),
                image_label,
                image_body,
            ],
        ),
    )


def _build_marquee_demo_page(state: AppState) -> Panel:
    horizontal_banner = Text(
        align="left",
        font=FONT_4X6,
        overflow="overflow",
        overflow_axis="x",
        overflow_offset=state.marquee_x,
        overflow_gap=4,
        text="  ARRIVALS: SEA 08:40  LAX 09:05  SFO 09:20  JFK 10:10  ",
    )
    vertical_feed = Text(
        align="left",
        font=FONT_3X5,
        overflow="overflow",
        overflow_axis="y",
        overflow_offset=state.marquee_y,
        overflow_gap=2,
        text="GATE A1 OPEN  GATE A3 BOARDING  GATE B4 DELAYED  GATE C2 NOW BOARDING  ",
    )
    generic_content = Marquee(
        axis="x",
        offset=state.marquee_x,
        content_extent=34,
        gap=2,
        child=Panel(
            padding=1,
            border=colors.WHITE,
            bg=colors.BLUE,
            child=Text(
                align="center",
                font=FONT_3X5,
                overflow="clip",
                text="GENERIC TILE",
                color=colors.WHITE,
            ),
        ),
    )
    return Panel(
        padding=1,
        bg=colors.BLACK,
        border=colors.WHITE,
        child=Column(
            gap=1,
            sizes=[8, 10, 20, 22],
            children=[
                Text(
                    align="center",
                    font=FONT_5X7,
                    overflow="clip",
                    text="MARQUEE",
                ),
                horizontal_banner,
                Panel(
                    padding=1,
                    bg=colors.BLACK,
                    border=colors.CYAN,
                    child=vertical_feed,
                ),
                generic_content,
            ],
        ),
    )


def _build_spinner_demo_page(state: AppState) -> Panel:
    return Panel(
        padding=1,
        bg=colors.BLACK,
        border=colors.CYAN,
        child=Column(
            gap=1,
            sizes=[8, 16, 36],
            children=[
                Text(
                    align="center",
                    font=FONT_5X7,
                    overflow="clip",
                    text="LOADING",
                ),
                Text(
                    align="center",
                    font=FONT_3X5,
                    overflow="clip",
                    text="FADE + SPIN",
                    color=colors.DIM_WHITE,
                ),
                Panel(
                    padding=1,
                    bg=colors.BLACK,
                    border=colors.WHITE,
                    child=LoadingSpinner(
                        phase=state.spinner_phase,
                        color=colors.WHITE,
                        radius=12,
                        spokes=14,
                    ),
                ),
            ],
        ),
    )


def _build_map_demo_page(state: AppState) -> Panel:
    header = Text(
        align="center",
        font=FONT_5X7,
        overflow="clip",
        text="MAP CLEVELAND",
        color=colors.WHITE,
    )
    footer_text = f"Z{state.map_zoom} LAT {state.map_center_lat:.2f} LON {state.map_center_lon:.2f}"
    if state.map_error:
        footer_text = "MAP LOAD ERROR"

    return Panel(
        padding=1,
        bg=colors.BLACK,
        border=colors.WHITE,
        child=Map(
            center_lat=state.map_center_lat,
            center_lon=state.map_center_lon,
            zoom=state.map_zoom,
            tile_data=state.map_tile_data,
            loading=state.map_loading,
            bg=state.map_style.bg,
            land_color=state.map_style.land,
            park_color=state.map_style.park,
            building_color=state.map_style.building,
            water_color=state.map_style.water,
            road_color=state.map_style.road,
            border_color=state.map_style.border,
            spinner_phase=state.spinner_phase,
        )
    )


def build_pages(state: AppState) -> list[Panel]:
    return [
        _build_font_demo_page(),
        _build_layout_demo_page(),
        _build_image_demo_page(state),
        _build_marquee_demo_page(state),
        _build_spinner_demo_page(state),
        _build_map_demo_page(state),
    ]


def _lon_lat_to_tile(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    lat = max(min(lat, 85.0511), -85.0511)
    n = 2**zoom
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - (math.log(math.tan(lat_rad) + (1.0 / math.cos(lat_rad))) / math.pi)) * 0.5 * n)
    return max(0, min(n - 1, x)), max(0, min(n - 1, y))


def _lon_lat_to_world_tile(lon: float, lat: float, zoom: int) -> tuple[float, float]:
    lat = max(min(lat, 85.0511), -85.0511)
    n = 2**zoom
    x = ((lon + 180.0) / 360.0) * n
    lat_rad = math.radians(lat)
    y = (1.0 - (math.log(math.tan(lat_rad) + (1.0 / math.cos(lat_rad))) / math.pi)) * 0.5 * n
    return x, y


def _resolve_style_uri(style: str, owner: str) -> str:
    if style.startswith("mapbox://"):
        return style
    return f"mapbox://styles/{owner}/{style}"


@functools.lru_cache(maxsize=256)
def _fetch_decoded_tile(zoom: int, x: int, y: int) -> dict[str, Any]:
    if decode_mvt is None:
        raise RuntimeError("mapbox-vector-tile is not installed")

    style_uri = _resolve_style_uri(MAPBOX_STYLE, MAPBOX_STYLE_OWNER)
    encoded_style = urllib.parse.quote(style_uri, safe=":/@")

    base_url = f"https://api.mapbox.com/v4/{MAPBOX_TILESET}/{zoom}/{x}/{y}.mvt"
    urls = [
        f"{base_url}?style={encoded_style}&access_token={MAPBOX_TOKEN}",
        f"{base_url}?access_token={MAPBOX_TOKEN}",
    ]

    payload: bytes | None = None
    last_error: Exception | None = None
    for url in urls:
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                payload = response.read()
                break
        except urllib.error.HTTPError as exc:
            last_error = RuntimeError(f"map request HTTP {exc.code}: {exc.reason}")
            continue
        except urllib.error.URLError as exc:
            last_error = RuntimeError(f"map request failed: {exc.reason}")
            continue

    if payload is None:
        raise RuntimeError(str(last_error) if last_error is not None else "map request failed")

    if payload.startswith(b"\x1f\x8b"):
        payload = gzip.decompress(payload)

    return decode_mvt(payload, default_options={"y_coord_down": True})


def _fetch_map_tile(center_lat: float, center_lon: float, zoom: int, view_aspect: float = 1.0) -> dict[str, Any]:
    world_x, world_y = _lon_lat_to_world_tile(center_lon, center_lat, zoom)
    n = 2**zoom

    # Keep zoom scale consistent in both axes; extend the longer axis by aspect ratio.
    aspect = max(1e-6, float(view_aspect))
    if aspect >= 1.0:
        world_width = aspect
        world_height = 1.0
    else:
        world_width = 1.0
        world_height = 1.0 / aspect

    min_world_x = world_x - (world_width / 2.0)
    max_world_x = world_x + (world_width / 2.0)
    min_world_y = world_y - (world_height / 2.0)
    max_world_y = world_y + (world_height / 2.0)

    min_tx = math.floor(min_world_x)
    max_tx = math.floor(max_world_x)
    min_ty = max(0, math.floor(min_world_y))
    max_ty = min(n - 1, math.floor(max_world_y))

    tiles: list[dict[str, Any]] = []
    for tile_y in range(min_ty, max_ty + 1):
        for tile_x_unwrapped in range(min_tx, max_tx + 1):
            tile_x_wrapped = tile_x_unwrapped % n
            tile_data = _fetch_decoded_tile(zoom, tile_x_wrapped, tile_y)
            tiles.append(
                {
                    "x": tile_x_wrapped,
                    "x_unwrapped": tile_x_unwrapped,
                    "y": tile_y,
                    "data": tile_data,
                }
            )

    return {
        "zoom": zoom,
        "center_world_x": world_x,
        "center_world_y": world_y,
        "min_world_x": min_world_x,
        "min_world_y": min_world_y,
        "world_width": world_width,
        "world_height": world_height,
        "tiles": tiles,
    }


def _read_map_aspect(app: App) -> float:
    cols = int(getattr(app.options, "cols", 0) or 0)
    rows = int(getattr(app.options, "rows", 0) or 0)
    if cols > 0 and rows > 0:
        return max(0.1, cols / rows)

    matrix = getattr(app, "matrix", None)
    width = int(getattr(matrix, "width", 0) or 0)
    height = int(getattr(matrix, "height", 0) or 0)
    if width > 0 and height > 0:
        return max(0.1, width / height)

    return 1.0


def _start_map_request(state: AppState, executor: ThreadPoolExecutor) -> None:
    if state.map_loading or state.map_tile_data is not None or state.map_request is not None:
        return
    state.map_error = None
    state.map_loading = True
    state.map_request = executor.submit(
        _fetch_map_tile,
        state.map_center_lat,
        state.map_center_lon,
        state.map_zoom,
        state.map_view_aspect,
    )


def _poll_map_request(state: AppState) -> bool:
    if state.map_request is None or not state.map_request.done():
        return False

    request = state.map_request
    state.map_request = None
    state.map_loading = False
    try:
        state.map_tile_data = request.result()
        state.map_error = None
    except Exception as exc:
        state.map_tile_data = None
        state.map_error = str(exc)
    return True


def _publish_perf_stats(
    app: App,
    *,
    target_hz: float,
    actual_hz: float,
    misses: int,
    frames: int,
    avg_overrun_ms: float,
    max_overrun_ms: float,
    minor_late: int,
    major_late: int,
) -> None:
    setter = getattr(app.matrix, "SetPerformanceStats", None)
    if callable(setter):
        setter(
            target_hz=target_hz,
            actual_hz=actual_hz,
            misses=misses,
            frames=frames,
            avg_overrun_ms=avg_overrun_ms,
            max_overrun_ms=max_overrun_ms,
            minor_late=minor_late,
            major_late=major_late,
        )
        return

    root = getattr(app.matrix, "root", None)
    if root is not None:
        root.title(
            "Mock RGB Matrix "
            f"{actual_hz:.1f}/{target_hz:.1f}Hz "
            f"miss {misses}/{frames} "
            f"avg {avg_overrun_ms:.2f}ms max {max_overrun_ms:.2f}ms"
        )


def main() -> int:
    try:
        with _HighResWindowsTimer(), ThreadPoolExecutor(max_workers=1) as map_executor:
            app = App(options=_build_matrix_options())
            state = AppState()
            editor_holder: dict[str, Any] = {"window": None}

            root = getattr(app.matrix, "root", None)
            if root is not None:
                root.bind(
                    "<KeyPress-c>",
                    lambda _event: _open_map_style_editor(root, state, editor_holder),
                )
                root.bind(
                    "<KeyPress-C>",
                    lambda _event: _open_map_style_editor(root, state, editor_holder),
                )

            start = time.perf_counter()
            frame_delay = 1.0 / max(1, app.options.limit_refresh_rate_hz)
            next_deadline = start + frame_delay
            stats_window_start = start
            frames_in_window = 0
            misses_in_window = 0
            max_overrun_ms = 0.0
            overrun_sum_ms = 0.0
            minor_late_in_window = 0
            major_late_in_window = 0
            needs_render = True

            while True:
                frame_start = time.perf_counter()
                event = app.poll_input()
                if event == "left":
                    state.page_index = clamp_page(state.page_index - 1)
                    needs_render = True
                elif event == "right":
                    state.page_index = clamp_page(state.page_index + 1)
                    needs_render = True
                elif event == "quit":
                    break

                elapsed_s = frame_start - start
                state.marquee_x = elapsed_s * MARQUEE_X_PIXELS_PER_SECOND
                state.marquee_y = elapsed_s * MARQUEE_Y_PIXELS_PER_SECOND
                state.spinner_phase = elapsed_s * SPINNER_PHASE_STEPS_PER_SECOND

                # Headless hardware mode has no keyboard events; auto-rotate demo pages.
                if root is None:
                    next_page = int(elapsed_s / AUTO_PAGE_SECONDS) % len(DEMO_PAGES)
                    if next_page != state.page_index:
                        state.page_index = next_page
                        needs_render = True

                if _load_asset_png_frames():
                    next_image_index = int(elapsed_s / IMAGE_SWITCH_SECONDS)
                    if next_image_index != state.image_index:
                        state.image_index = next_image_index
                        if state.page_index == 2:
                            needs_render = True

                if state.page_index == 3:
                    needs_render = True
                elif state.page_index == 4:
                    needs_render = True
                elif state.page_index == 5 and state.map_loading:
                    needs_render = True

                if state.page_index == 5:
                    state.map_view_aspect = _read_map_aspect(app)
                    _start_map_request(state, map_executor)

                if _poll_map_request(state):
                    needs_render = True

                if state.style_dirty:
                    needs_render = True
                    state.style_dirty = False

                if needs_render:
                    pages = build_pages(state)
                    app.Render(pages[state.page_index])
                    needs_render = False

                now = time.perf_counter()
                frames_in_window += 1
                overrun = now - next_deadline
                if overrun > 0:
                    overrun_ms = overrun * 1000.0
                    misses_in_window += 1
                    max_overrun_ms = max(max_overrun_ms, overrun_ms)
                    overrun_sum_ms += overrun_ms
                    if overrun_ms <= 0.5:
                        minor_late_in_window += 1
                    elif overrun_ms >= 2.0:
                        major_late_in_window += 1
                    # Reset phase if we missed by more than one frame period.
                    if overrun > frame_delay:
                        next_deadline = now + frame_delay
                    else:
                        next_deadline += frame_delay
                else:
                    _sleep_until(next_deadline)
                    next_deadline += frame_delay

                now = time.perf_counter()
                window_elapsed = now - stats_window_start
                if window_elapsed >= MISS_LOG_INTERVAL_S:
                    actual_hz = frames_in_window / max(1e-9, window_elapsed)
                    avg_overrun_ms = (
                        overrun_sum_ms / misses_in_window if misses_in_window > 0 else 0.0
                    )
                    _publish_perf_stats(
                        app,
                        target_hz=float(app.options.limit_refresh_rate_hz),
                        actual_hz=actual_hz,
                        misses=misses_in_window,
                        frames=frames_in_window,
                        avg_overrun_ms=avg_overrun_ms,
                        max_overrun_ms=max_overrun_ms,
                        minor_late=minor_late_in_window,
                        major_late=major_late_in_window,
                    )
                    if misses_in_window > 0:
                        print(
                            "[timing] "
                            f"target={app.options.limit_refresh_rate_hz}Hz "
                            f"actual={actual_hz:.1f}Hz "
                            f"misses={misses_in_window}/{frames_in_window} "
                            f"avg_overrun={avg_overrun_ms:.2f}ms "
                            f"max_overrun={max_overrun_ms:.2f}ms "
                            f"minor={minor_late_in_window} "
                            f"major={major_late_in_window}"
                        )
                    stats_window_start = now
                    frames_in_window = 0
                    misses_in_window = 0
                    max_overrun_ms = 0.0
                    overrun_sum_ms = 0.0
                    minor_late_in_window = 0
                    major_late_in_window = 0

            if not app.matrix.closed:
                app.matrix.close()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
