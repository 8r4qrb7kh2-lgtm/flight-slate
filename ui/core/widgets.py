"""Declarative core widgets: Panel and Text."""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, floor, sin, tau
from typing import Any

from ui.core.bitmap_font import BitmapFont
from ui.core.canvas import PixelCanvas, Rect
from ui.core.colors import Color, colors
from ui.core.image_asset import ImageFrame


class Widget:
    def draw(self, canvas: PixelCanvas, rect: Rect) -> None:
        raise NotImplementedError


@dataclass
class Text(Widget):
    text: str
    font: BitmapFont
    align: str = "left"
    overflow: str = "clip"
    overflow_axis: str = "x"
    overflow_offset: float = 0.0
    overflow_gap: int | None = None
    color: Color = colors.WHITE
    line_spacing: int | None = None

    def draw(self, canvas: PixelCanvas, rect: Rect) -> None:
        if rect.width <= 0 or rect.height <= 0:
            return

        if self.overflow == "overflow":
            self._draw_overflow(canvas, rect)
            return

        line_height = self.font.height
        line_spacing = self.font.spacing * 2 if self.line_spacing is None else max(0, self.line_spacing)
        lines = self._resolve_lines(rect.width)
        draw_y = rect.y

        with canvas.clip(rect):
            for line in lines:
                if draw_y + line_height > rect.bottom:
                    break
                line_width, _ = self.font.measure(line)
                if self.align == "center":
                    draw_x = rect.x + max(0, (rect.width - line_width) // 2)
                elif self.align == "right":
                    draw_x = rect.x + max(0, rect.width - line_width)
                else:
                    draw_x = rect.x
                self.font.render(canvas, draw_x, draw_y, line, self.color)
                draw_y += line_height + line_spacing

    def _draw_overflow(self, canvas: PixelCanvas, rect: Rect) -> None:
        axis = "y" if self.overflow_axis == "y" else "x"
        gap = self.font.spacing * 4 if self.overflow_gap is None else max(0, self.overflow_gap)

        if axis == "x":
            content_extent = self.font.measure(self.text)[0]
            child = Text(
                text=self.text,
                font=self.font,
                align="left",
                overflow="clip",
                color=self.color,
                line_spacing=self.line_spacing,
            )
        else:
            line_spacing = self.font.spacing * 2 if self.line_spacing is None else max(0, self.line_spacing)
            lines = _wrap_text(self.font, self.text, rect.width)
            line_count = max(1, len(lines))
            content_extent = (line_count * self.font.height) + ((line_count - 1) * line_spacing)
            child = Text(
                text=self.text,
                font=self.font,
                align=self.align,
                overflow="wrap",
                color=self.color,
                line_spacing=self.line_spacing,
            )

        Marquee(
            child=child,
            axis=axis,
            offset=self.overflow_offset,
            content_extent=content_extent,
            gap=gap,
        ).draw(canvas, rect)

    def _resolve_lines(self, width: int) -> list[str]:
        if self.overflow == "wrap":
            return _wrap_text(self.font, self.text, width)
        return [self.font.clip(self.text, width)]


@dataclass
class Panel(Widget):
    child: Widget
    padding: int = 0
    bg: Color = colors.BLACK
    border: Color | None = None

    def draw(self, canvas: PixelCanvas, rect: Rect) -> None:
        canvas.rect(rect, fill=self.bg, outline=self.border)

        border_inset = 1 if self.border is not None else 0
        inset = self.padding + border_inset
        inner_x = rect.x + inset
        inner_y = rect.y + inset
        inner_width = max(0, rect.width - inset * 2)
        inner_height = max(0, rect.height - inset * 2)
        if self.child is None or inner_width == 0 or inner_height == 0:
            return

        self.child.draw(canvas, Rect(inner_x, inner_y, inner_width, inner_height))


@dataclass
class Image(Widget):
    frame: ImageFrame | None
    fit: str = "contain"
    bg: Color | None = None

    def draw(self, canvas: PixelCanvas, rect: Rect) -> None:
        if rect.width <= 0 or rect.height <= 0:
            return

        if self.bg is not None:
            canvas.rect(rect, fill=self.bg)

        if self.frame is None:
            return

        src_w = self.frame.width
        src_h = self.frame.height
        if src_w <= 0 or src_h <= 0:
            return

        mode = self.fit.lower().strip()
        if mode == "stretch":
            draw_w = rect.width
            draw_h = rect.height
        elif mode in {"none", "original", "native"}:
            draw_w = src_w
            draw_h = src_h
        else:
            scale = min(rect.width / src_w, rect.height / src_h)
            if scale <= 0:
                return
            draw_w = max(1, int(src_w * scale))
            draw_h = max(1, int(src_h * scale))

        origin_x = rect.x + max(0, (rect.width - draw_w) // 2)
        origin_y = rect.y + max(0, (rect.height - draw_h) // 2)

        with canvas.clip(rect):
            for dy in range(draw_h):
                src_y = (dy * src_h) // draw_h
                for dx in range(draw_w):
                    src_x = (dx * src_w) // draw_w
                    argb = self.frame.argb_pixels[(src_y * src_w) + src_x]
                    alpha = (argb >> 24) & 0xFF
                    if alpha == 0:
                        continue

                    color = ((argb >> 16) & 0xFF, (argb >> 8) & 0xFF, argb & 0xFF)
                    dst_x = origin_x + dx
                    dst_y = origin_y + dy
                    if alpha >= 255:
                        canvas.pixel(dst_x, dst_y, color)
                    else:
                        canvas.blend_pixel(dst_x, dst_y, color, alpha / 255.0)


@dataclass
class Marquee(Widget):
    child: Widget
    axis: str = "x"
    offset: float = 0.0
    content_extent: int | None = None
    gap: int = 0

    def draw(self, canvas: PixelCanvas, rect: Rect) -> None:
        if rect.width <= 0 or rect.height <= 0 or self.child is None:
            return

        axis = "y" if self.axis == "y" else "x"
        axis_total = rect.height if axis == "y" else rect.width
        if axis_total <= 0:
            return

        gap = max(0, self.gap)
        content_extent = self.content_extent
        if content_extent is None:
            content_extent = _estimate_axis_extent(self.child, rect, axis)
        if content_extent is None or content_extent <= 0:
            self.child.draw(canvas, rect)
            return

        step = content_extent + gap
        if step <= 0:
            self.child.draw(canvas, rect)
            return

        integer_offset = int(floor(self.offset))
        self._draw_integer(canvas, rect, axis, axis_total, content_extent, step, integer_offset)

    def _draw_integer(
        self,
        canvas: PixelCanvas,
        rect: Rect,
        axis: str,
        axis_total: int,
        content_extent: int,
        step: int,
        offset: int,
    ) -> None:
        shift = offset % step
        start = -shift
        with canvas.clip(rect):
            while start < axis_total:
                if axis == "x":
                    child_rect = Rect(rect.x + start, rect.y, content_extent, rect.height)
                else:
                    child_rect = Rect(rect.x, rect.y + start, rect.width, content_extent)
                self.child.draw(canvas, child_rect)
                start += step


@dataclass
class Column(Widget):
    children: list[Widget]
    gap: int = 0
    sizes: list[int] | None = None

    def draw(self, canvas: PixelCanvas, rect: Rect) -> None:
        if rect.width <= 0 or rect.height <= 0 or not self.children:
            return

        if self.sizes is not None:
            _draw_weighted_stack(
                canvas=canvas,
                rect=rect,
                children=self.children,
                gap=self.gap,
                sizes=self.sizes,
                horizontal=False,
            )
            return

        cursor_y = rect.y
        for index, child in enumerate(self.children):
            if cursor_y >= rect.bottom:
                break

            child_height = _estimate_height(child, rect.width)
            remaining = rect.bottom - cursor_y
            if child_height <= 0:
                child_height = remaining
            draw_height = min(child_height, remaining)
            child.draw(canvas, Rect(rect.x, cursor_y, rect.width, draw_height))
            cursor_y += draw_height
            if index != len(self.children) - 1:
                cursor_y += self.gap


@dataclass
class Row(Widget):
    children: list[Widget]
    gap: int = 0
    sizes: list[int] | None = None

    def draw(self, canvas: PixelCanvas, rect: Rect) -> None:
        if rect.width <= 0 or rect.height <= 0 or not self.children:
            return

        if self.sizes is None:
            slot_count = len(self.children)
            sizes = [1] * slot_count
        else:
            slot_count = len(self.sizes)
            sizes = self.sizes

        _draw_weighted_stack(
            canvas=canvas,
            rect=rect,
            children=self.children,
            gap=self.gap,
            sizes=sizes,
            horizontal=True,
        )


def _wrap_text(font: BitmapFont, text: str, width: int) -> list[str]:
    if not text:
        return [""]

    wrapped: list[str] = []
    current = ""

    for char in text:
        candidate = current + char
        if not current:
            current = char
            continue

        if font.measure(candidate)[0] <= width:
            current = candidate
            continue

        wrapped.append(current)
        current = char

    if current:
        wrapped.append(current)

    return wrapped


def _estimate_height(widget: Widget, width: int) -> int:
    if isinstance(widget, Text):
        line_spacing = widget.font.spacing * 2 if widget.line_spacing is None else max(0, widget.line_spacing)
        line_count = len(widget._resolve_lines(width))
        if line_count <= 0:
            return 0
        return (line_count * widget.font.height) + ((line_count - 1) * line_spacing)
    if isinstance(widget, Panel):
        border_inset = 1 if widget.border is not None else 0
        inset = widget.padding + border_inset
        inner_width = max(0, width - inset * 2)
        child_height = _estimate_height(widget.child, inner_width)
        return child_height + (inset * 2)
    if isinstance(widget, Column):
        total = 0
        for idx, child in enumerate(widget.children):
            total += _estimate_height(child, width)
            if idx != len(widget.children) - 1:
                total += widget.gap
        return total
    return 0


def _draw_weighted_stack(
    canvas: PixelCanvas,
    rect: Rect,
    children: list[Widget],
    gap: int,
    sizes: list[int],
    horizontal: bool,
) -> None:
    if not sizes:
        raise ValueError("sizes must contain at least one slot")

    if len(children) > len(sizes):
        raise ValueError("children exceed configured slot count")

    if any(size < 0 for size in sizes):
        raise ValueError("sizes must be non-negative")

    size_total = sum(sizes)
    if size_total <= 0:
        raise ValueError("sizes must sum to a positive value")

    gap = max(0, gap)
    slot_count = len(sizes)
    axis_total = rect.width if horizontal else rect.height
    usable_total = max(0, axis_total - (gap * (slot_count - 1)))
    slot_extents = _allocate_weighted_extents(usable_total, sizes)

    cursor_x = rect.x
    cursor_y = rect.y
    for index, slot_extent in enumerate(slot_extents):
        if index < len(children) and slot_extent > 0:
            if horizontal:
                child_rect = Rect(cursor_x, rect.y, slot_extent, rect.height)
            else:
                child_rect = Rect(rect.x, cursor_y, rect.width, slot_extent)
            children[index].draw(canvas, child_rect)

        if horizontal:
            cursor_x += slot_extent
            if index != slot_count - 1:
                cursor_x += gap
        else:
            cursor_y += slot_extent
            if index != slot_count - 1:
                cursor_y += gap


def _allocate_weighted_extents(total: int, sizes: list[int]) -> list[int]:
    if total <= 0:
        return [0] * len(sizes)

    size_total = sum(sizes)
    cumulative = 0
    previous_edge = 0
    extents: list[int] = []

    # Derive slot edges from cumulative integer proportions.
    for size in sizes:
        cumulative += size
        edge = (total * cumulative) // size_total
        extents.append(edge - previous_edge)
        previous_edge = edge

    return extents


def _estimate_axis_extent(widget: Widget, rect: Rect, axis: str) -> int:
    if isinstance(widget, Text):
        if axis == "x":
            return widget.font.measure(widget.text)[0]

        line_spacing = widget.font.spacing * 2 if widget.line_spacing is None else max(0, widget.line_spacing)
        lines = widget._resolve_lines(rect.width)
        line_count = max(1, len(lines))
        return (line_count * widget.font.height) + ((line_count - 1) * line_spacing)

    if isinstance(widget, Panel):
        border_inset = 1 if widget.border is not None else 0
        inset = widget.padding + border_inset
        inner_rect = Rect(
            rect.x,
            rect.y,
            max(0, rect.width - inset * 2),
            max(0, rect.height - inset * 2),
        )
        return _estimate_axis_extent(widget.child, inner_rect, axis) + (inset * 2)

    if isinstance(widget, Row):
        if axis == "y":
            return rect.height
        total = 0
        for index, child in enumerate(widget.children):
            total += _estimate_axis_extent(child, rect, axis)
            if index != len(widget.children) - 1:
                total += widget.gap
        return total

    if isinstance(widget, Column):
        if axis == "x":
            widest = 0
            for child in widget.children:
                widest = max(widest, _estimate_axis_extent(child, rect, axis))
            return widest
        total = 0
        for index, child in enumerate(widget.children):
            total += _estimate_axis_extent(child, rect, axis)
            if index != len(widget.children) - 1:
                total += widget.gap
        return total

    return rect.height if axis == "y" else rect.width


@dataclass
class LoadingSpinner(Widget):
    phase: float = 0.0
    color: Color = colors.WHITE
    radius: int = 9
    spokes: int = 12

    def draw(self, canvas: PixelCanvas, rect: Rect) -> None:
        if rect.width <= 0 or rect.height <= 0:
            return

        cx = rect.x + (rect.width / 2.0)
        cy = rect.y + (rect.height / 2.0)
        spoke_count = max(6, self.spokes)
        radius = max(3, self.radius)

        with canvas.clip(rect):
            for index in range(spoke_count):
                # Create a soft trailing fade that rotates with phase.
                rel = (index - self.phase) % spoke_count
                alpha = max(0.2, 1.0 - (rel / spoke_count))
                angle = ((index / spoke_count) * tau) - (tau / 4.0)
                x = int(round(cx + (cos(angle) * radius)))
                y = int(round(cy + (sin(angle) * radius)))
                canvas.blend_pixel(x, y, self.color, alpha)
                # Star-like glow around each spoke endpoint.
                canvas.blend_pixel(x + 1, y, self.color, alpha * 0.65)
                canvas.blend_pixel(x - 1, y, self.color, alpha * 0.65)
                canvas.blend_pixel(x, y + 1, self.color, alpha * 0.65)
                canvas.blend_pixel(x, y - 1, self.color, alpha * 0.65)
                canvas.blend_pixel(x + 1, y + 1, self.color, alpha * 0.35)
                canvas.blend_pixel(x - 1, y + 1, self.color, alpha * 0.35)
                canvas.blend_pixel(x + 1, y - 1, self.color, alpha * 0.35)
                canvas.blend_pixel(x - 1, y - 1, self.color, alpha * 0.35)
            # Bright center glint for stronger "loading" focus.
            canvas.blend_pixel(int(round(cx)), int(round(cy)), self.color, 1.0)


@dataclass
class Map(Widget):
    center_lat: float
    center_lon: float
    zoom: int
    tile_data: dict[str, Any] | None = None
    loading: bool = False
    bg: Color = (18, 18, 20)
    # Base land is a dim green so overlays remain readable.
    land_color: Color = (16, 52, 16)
    water_color: Color = (20, 95, 210)
    # Parks are clearly brighter than regular land.
    park_color: Color = (32, 108, 32)
    building_color: Color = (120, 124, 120)
    border_color: Color = colors.WHITE
    road_color: Color = (150, 150, 150)
    spinner_phase: float = 0.0

    def draw(self, canvas: PixelCanvas, rect: Rect) -> None:
        if rect.width <= 0 or rect.height <= 0:
            return

        canvas.rect(rect, fill=self.bg, outline=None)
        content = Rect(rect.x + 1, rect.y + 1, max(0, rect.width - 2), max(0, rect.height - 2))
        if content.width <= 0 or content.height <= 0:
            return

        canvas.rect(content, fill=self.land_color, outline=None)

        if self.tile_data is not None:
            # Keep all map vectors constrained to the content rect.
            with canvas.clip(content):
                if isinstance(self.tile_data, dict) and "tiles" in self.tile_data:
                    _draw_map_view(
                        canvas=canvas,
                        rect=content,
                        zoom=self.zoom,
                        tile_bundle=self.tile_data,
                        water_color=self.water_color,
                        park_color=self.park_color,
                        building_color=self.building_color,
                        border_color=self.border_color,
                        road_color=self.road_color,
                    )
                else:
                    _draw_map_tile(
                        canvas=canvas,
                        rect=content,
                        zoom=self.zoom,
                        tile_data=self.tile_data,
                        water_color=self.water_color,
                        park_color=self.park_color,
                        building_color=self.building_color,
                        border_color=self.border_color,
                        road_color=self.road_color,
                    )

        if self.loading:
            with canvas.clip(content):
                for y in range(content.y, content.bottom):
                    for x in range(content.x, content.right):
                        canvas.blend_pixel(x, y, colors.BLACK, 0.55)
            spinner_size = min(content.width, content.height)
            LoadingSpinner(
                phase=self.spinner_phase,
                color=colors.WHITE,
                radius=max(4, spinner_size // 6),
                spokes=12,
            ).draw(canvas, content)


_MAP_MAJOR_ROAD_CLASSES = {"motorway", "trunk", "primary", "secondary"}
_MAP_PARK_CLASSES = {"park", "national_park", "nature_reserve", "recreation_ground", "grass"}
_MAP_URBAN_CLASSES = {"building", "residential", "commercial", "industrial", "retail"}


def _admin_rank(props: dict[str, Any]) -> int:
    admin_level_raw = props.get("admin_level")
    try:
        return int(str(admin_level_raw))
    except Exception:
        pass

    cls = str(props.get("class") or props.get("type") or "").lower()
    if cls in {"country", "disputed", "international", "national"}:
        return 2
    if cls in {"state", "province", "region"}:
        return 4
    if cls in {"county", "district"}:
        return 6
    if cls in {"city", "municipality", "locality"}:
        return 8
    return 99


def _should_draw_admin(props: dict[str, Any], zoom: int) -> bool:
    # Keep only broad borders at continent/country views.
    rank = _admin_rank(props)
    if zoom <= 2:
        return rank <= 2
    if zoom <= 3:
        return rank <= 4
    if zoom <= 5:
        return rank <= 5
    if zoom <= 7:
        return rank <= 6
    if zoom <= 8:
        return rank <= 7
    return True


def _allowed_road_classes(zoom: int) -> set[str]:
    # Avoid gray-road washout at low zoom by showing only the most important roads.
    if zoom <= 3:
        return set()
    if zoom <= 5:
        return {"motorway"}
    if zoom <= 7:
        return {"motorway", "trunk"}
    if zoom <= 9:
        return {"motorway", "trunk", "primary"}
    if zoom <= 12:
        return {"motorway", "trunk", "primary"}
    if zoom <= 14:
        return {"motorway", "trunk", "primary", "secondary"}
    return {"motorway", "trunk", "primary", "secondary", "tertiary"}


def _road_density_mod(zoom: int) -> int:
    # Additional decimation to reduce visual clutter without random flicker.
    if zoom <= 5:
        return 99
    if zoom <= 7:
        return 6
    if zoom <= 9:
        return 4
    if zoom <= 12:
        return 3
    if zoom <= 14:
        return 2
    return 1


def _road_bucket(props: dict[str, Any]) -> int:
    token = str(props.get("id") or props.get("osm_id") or props.get("name") or props.get("ref") or "")
    h = 0
    for ch in token:
        h = ((h * 131) + ord(ch)) & 0xFFFFFFFF
    return h


def _draw_map_tile(
    *,
    canvas: PixelCanvas,
    rect: Rect,
    zoom: int,
    tile_data: dict[str, Any],
    water_color: Color,
    park_color: Color,
    building_color: Color,
    border_color: Color,
    road_color: Color,
) -> None:
    for layer_name in ("water", "waterway"):
        layer = tile_data.get(layer_name)
        if not layer:
            continue
        extent = int(layer.get("extent", 4096))
        for feature in layer.get("features", []):
            _draw_feature_geometry(canvas, rect, extent, feature.get("geometry", {}), water_color, 1)

    for layer_name in ("landuse", "landcover"):
        layer = tile_data.get(layer_name)
        if not layer:
            continue
        extent = int(layer.get("extent", 4096))
        for feature in layer.get("features", []):
            props = feature.get("properties", {})
            if props.get("class") not in _MAP_PARK_CLASSES:
                continue
            geometry = feature.get("geometry", {})
            geom_type = geometry.get("type")
            coords = geometry.get("coordinates", [])
            if geom_type == "Polygon":
                _draw_polygon_geometry(canvas, rect, [coords], extent, park_color)
            elif geom_type == "MultiPolygon":
                _draw_polygon_geometry(canvas, rect, coords, extent, park_color)

    for layer_name in ("building", "building_part", "landuse_overlay", "landuse"):
        layer = tile_data.get(layer_name)
        if not layer:
            continue
        extent = int(layer.get("extent", 4096))
        for feature in layer.get("features", []):
            props = feature.get("properties", {})
            if layer_name in {"landuse_overlay", "landuse"}:
                if props.get("class") not in _MAP_URBAN_CLASSES:
                    continue
            geometry = feature.get("geometry", {})
            geom_type = geometry.get("type")
            coords = geometry.get("coordinates", [])
            if geom_type == "Polygon":
                _draw_polygon_geometry(canvas, rect, [coords], extent, building_color)
            elif geom_type == "MultiPolygon":
                _draw_polygon_geometry(canvas, rect, coords, extent, building_color)

    admin = tile_data.get("admin")
    if admin:
        extent = int(admin.get("extent", 4096))
        for feature in admin.get("features", []):
            props = feature.get("properties", {})
            if not _should_draw_admin(props, zoom):
                continue
            _draw_feature_geometry(canvas, rect, extent, feature.get("geometry", {}), border_color, 1)

    roads = tile_data.get("road")
    if roads:
        extent = int(roads.get("extent", 4096))
        allowed_classes = _allowed_road_classes(zoom)
        sample_mod = _road_density_mod(zoom)
        for feature in roads.get("features", []):
            props = feature.get("properties", {})
            road_class = props.get("class")
            if road_class not in allowed_classes:
                continue
            if sample_mod > 1 and (_road_bucket(props) % sample_mod) != 0:
                continue
            # Keep roads crisp on low-res matrix to avoid fat merged corridors.
            width = 1
            _draw_feature_geometry(canvas, rect, extent, feature.get("geometry", {}), road_color, width)


def _draw_map_view(
    *,
    canvas: PixelCanvas,
    rect: Rect,
    zoom: int,
    tile_bundle: dict[str, Any],
    water_color: Color,
    park_color: Color,
    building_color: Color,
    border_color: Color,
    road_color: Color,
) -> None:
    min_world_x = float(tile_bundle.get("min_world_x", 0.0))
    min_world_y = float(tile_bundle.get("min_world_y", 0.0))
    world_width = max(
        1e-9,
        float(tile_bundle.get("world_width", tile_bundle.get("world_tiles", 1.0))),
    )
    world_height = max(
        1e-9,
        float(tile_bundle.get("world_height", tile_bundle.get("world_tiles", 1.0))),
    )
    tiles = tile_bundle.get("tiles", [])

    for tile in tiles:
        tile_data = tile.get("data")
        if not isinstance(tile_data, dict):
            continue
        tile_x = int(tile.get("x_unwrapped", tile.get("x", 0)))
        tile_y = int(tile.get("y", 0))
        _draw_map_tile_in_view(
            canvas=canvas,
            rect=rect,
            zoom=zoom,
            tile_data=tile_data,
            tile_x=tile_x,
            tile_y=tile_y,
            min_world_x=min_world_x,
            min_world_y=min_world_y,
            world_width=world_width,
            world_height=world_height,
            water_color=water_color,
            park_color=park_color,
            building_color=building_color,
            border_color=border_color,
            road_color=road_color,
        )


def _draw_map_tile_in_view(
    *,
    canvas: PixelCanvas,
    rect: Rect,
    zoom: int,
    tile_data: dict[str, Any],
    tile_x: int,
    tile_y: int,
    min_world_x: float,
    min_world_y: float,
    world_width: float,
    world_height: float,
    water_color: Color,
    park_color: Color,
    building_color: Color,
    border_color: Color,
    road_color: Color,
) -> None:
    for layer_name in ("water", "waterway"):
        layer = tile_data.get(layer_name)
        if not layer:
            continue
        extent = int(layer.get("extent", 4096))
        for feature in layer.get("features", []):
            _draw_feature_geometry_view(
                canvas,
                rect,
                extent,
                tile_x,
                tile_y,
                min_world_x,
                min_world_y,
                world_width,
                world_height,
                feature.get("geometry", {}),
                water_color,
                1,
            )

    for layer_name in ("landuse", "landcover"):
        layer = tile_data.get(layer_name)
        if not layer:
            continue
        extent = int(layer.get("extent", 4096))
        for feature in layer.get("features", []):
            props = feature.get("properties", {})
            if props.get("class") not in _MAP_PARK_CLASSES:
                continue
            geometry = feature.get("geometry", {})
            geom_type = geometry.get("type")
            coords = geometry.get("coordinates", [])
            if geom_type == "Polygon":
                _draw_polygon_geometry_view(
                    canvas,
                    rect,
                    [coords],
                    extent,
                    tile_x,
                    tile_y,
                    min_world_x,
                    min_world_y,
                    world_width,
                    world_height,
                    park_color,
                )
            elif geom_type == "MultiPolygon":
                _draw_polygon_geometry_view(
                    canvas,
                    rect,
                    coords,
                    extent,
                    tile_x,
                    tile_y,
                    min_world_x,
                    min_world_y,
                    world_width,
                    world_height,
                    park_color,
                )

    for layer_name in ("building", "building_part", "landuse_overlay", "landuse"):
        layer = tile_data.get(layer_name)
        if not layer:
            continue
        extent = int(layer.get("extent", 4096))
        for feature in layer.get("features", []):
            props = feature.get("properties", {})
            if layer_name in {"landuse_overlay", "landuse"} and props.get("class") not in _MAP_URBAN_CLASSES:
                continue
            geometry = feature.get("geometry", {})
            geom_type = geometry.get("type")
            coords = geometry.get("coordinates", [])
            if geom_type == "Polygon":
                _draw_polygon_geometry_view(
                    canvas,
                    rect,
                    [coords],
                    extent,
                    tile_x,
                    tile_y,
                    min_world_x,
                    min_world_y,
                    world_width,
                    world_height,
                    building_color,
                )
            elif geom_type == "MultiPolygon":
                _draw_polygon_geometry_view(
                    canvas,
                    rect,
                    coords,
                    extent,
                    tile_x,
                    tile_y,
                    min_world_x,
                    min_world_y,
                    world_width,
                    world_height,
                    building_color,
                )

    admin = tile_data.get("admin")
    if admin:
        extent = int(admin.get("extent", 4096))
        for feature in admin.get("features", []):
            props = feature.get("properties", {})
            if not _should_draw_admin(props, zoom):
                continue
            _draw_feature_geometry_view(
                canvas,
                rect,
                extent,
                tile_x,
                tile_y,
                min_world_x,
                min_world_y,
                world_width,
                world_height,
                feature.get("geometry", {}),
                border_color,
                1,
            )

    roads = tile_data.get("road")
    if roads:
        extent = int(roads.get("extent", 4096))
        allowed_classes = _allowed_road_classes(zoom)
        sample_mod = _road_density_mod(zoom)
        for feature in roads.get("features", []):
            props = feature.get("properties", {})
            if props.get("class") not in allowed_classes:
                continue
            if sample_mod > 1 and (_road_bucket(props) % sample_mod) != 0:
                continue
            _draw_feature_geometry_view(
                canvas,
                rect,
                extent,
                tile_x,
                tile_y,
                min_world_x,
                min_world_y,
                world_width,
                world_height,
                feature.get("geometry", {}),
                road_color,
                1,
            )


def _draw_feature_geometry(
    canvas: PixelCanvas,
    rect: Rect,
    extent: int,
    geometry: dict[str, Any],
    color: Color,
    width: int,
) -> None:
    geom_type = geometry.get("type")
    coords = geometry.get("coordinates", [])
    if geom_type == "Polygon":
        _draw_polygon_geometry(canvas, rect, [coords], extent, color)
    elif geom_type == "MultiPolygon":
        _draw_polygon_geometry(canvas, rect, coords, extent, color)
    elif geom_type == "LineString":
        _draw_linestring(canvas, rect, coords, extent, color, width)
    elif geom_type == "MultiLineString":
        for line in coords:
            _draw_linestring(canvas, rect, line, extent, color, width)


def _tile_to_screen(point: list[float], rect: Rect, extent: int) -> tuple[float, float]:
    denom = max(1, extent - 1)
    norm_x = min(max(point[0] / denom, 0.0), 1.0)
    norm_y = min(max(point[1] / denom, 0.0), 1.0)
    x = rect.x + (norm_x * max(1, rect.width - 1))
    y = rect.y + (norm_y * max(1, rect.height - 1))
    return x, y


def _tile_to_screen_view(
    point: list[float],
    rect: Rect,
    extent: int,
    tile_x: int,
    tile_y: int,
    min_world_x: float,
    min_world_y: float,
    world_width: float,
    world_height: float,
) -> tuple[float, float]:
    denom = max(1, extent - 1)
    local_x = min(max(point[0] / denom, 0.0), 1.0)
    local_y = min(max(point[1] / denom, 0.0), 1.0)
    world_x = tile_x + local_x
    world_y = tile_y + local_y
    content_w = max(1.0, float(rect.width - 1))
    content_h = max(1.0, float(rect.height - 1))
    scale = min(content_w / world_width, content_h / world_height)
    draw_w = world_width * scale
    draw_h = world_height * scale
    origin_x = rect.x + ((content_w - draw_w) * 0.5)
    origin_y = rect.y + ((content_h - draw_h) * 0.5)
    x = origin_x + ((world_x - min_world_x) * scale)
    y = origin_y + ((world_y - min_world_y) * scale)
    return x, y


def _draw_feature_geometry_view(
    canvas: PixelCanvas,
    rect: Rect,
    extent: int,
    tile_x: int,
    tile_y: int,
    min_world_x: float,
    min_world_y: float,
    world_width: float,
    world_height: float,
    geometry: dict[str, Any],
    color: Color,
    width: int,
) -> None:
    geom_type = geometry.get("type")
    coords = geometry.get("coordinates", [])
    if geom_type == "Polygon":
        _draw_polygon_geometry_view(
            canvas,
            rect,
            [coords],
            extent,
            tile_x,
            tile_y,
            min_world_x,
            min_world_y,
            world_width,
            world_height,
            color,
        )
    elif geom_type == "MultiPolygon":
        _draw_polygon_geometry_view(
            canvas,
            rect,
            coords,
            extent,
            tile_x,
            tile_y,
            min_world_x,
            min_world_y,
            world_width,
            world_height,
            color,
        )
    elif geom_type == "LineString":
        _draw_linestring_view(
            canvas,
            rect,
            coords,
            extent,
            tile_x,
            tile_y,
            min_world_x,
            min_world_y,
            world_width,
            world_height,
            color,
            width,
        )
    elif geom_type == "MultiLineString":
        for line in coords:
            _draw_linestring_view(
                canvas,
                rect,
                line,
                extent,
                tile_x,
                tile_y,
                min_world_x,
                min_world_y,
                world_width,
                world_height,
                color,
                width,
            )


def _draw_linestring_view(
    canvas: PixelCanvas,
    rect: Rect,
    line: list[list[float]],
    extent: int,
    tile_x: int,
    tile_y: int,
    min_world_x: float,
    min_world_y: float,
    world_width: float,
    world_height: float,
    color: Color,
    width: int,
) -> None:
    if len(line) < 2:
        return
    points = [
        _tile_to_screen_view(
            point,
            rect,
            extent,
            tile_x,
            tile_y,
            min_world_x,
            min_world_y,
            world_width,
            world_height,
        )
        for point in line
    ]
    for index in range(len(points) - 1):
        x0, y0 = points[index]
        x1, y1 = points[index + 1]
        _draw_line(canvas, int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1)), color, width)


def _draw_polygon_geometry_view(
    canvas: PixelCanvas,
    rect: Rect,
    coordinates: Any,
    extent: int,
    tile_x: int,
    tile_y: int,
    min_world_x: float,
    min_world_y: float,
    world_width: float,
    world_height: float,
    color: Color,
) -> None:
    for polygon in coordinates:
        if not polygon:
            continue
        outer = [
            _tile_to_screen_view(
                point,
                rect,
                extent,
                tile_x,
                tile_y,
                min_world_x,
                min_world_y,
                world_width,
                world_height,
            )
            for point in polygon[0]
        ]
        holes = [
            [
                _tile_to_screen_view(
                    point,
                    rect,
                    extent,
                    tile_x,
                    tile_y,
                    min_world_x,
                    min_world_y,
                    world_width,
                    world_height,
                )
                for point in hole
            ]
            for hole in polygon[1:]
        ]
        _fill_polygon(canvas, rect, outer, holes, color)


def _draw_linestring(
    canvas: PixelCanvas,
    rect: Rect,
    line: list[list[float]],
    extent: int,
    color: Color,
    width: int,
) -> None:
    if len(line) < 2:
        return
    points = [_tile_to_screen(point, rect, extent) for point in line]
    for index in range(len(points) - 1):
        x0, y0 = points[index]
        x1, y1 = points[index + 1]
        _draw_line(canvas, int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1)), color, width)


def _draw_line(
    canvas: PixelCanvas,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    color: Color,
    width: int,
) -> None:
    width = max(1, width)
    dx = abs(x1 - x0)
    sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0)
    sy = 1 if y0 < y1 else -1
    err = dx + dy

    while True:
        if width == 1:
            canvas.pixel(x0, y0, color)
        elif width == 2:
            canvas.pixel(x0, y0, color)
            # Use a directional pair so width=2 stays exactly two pixels thick.
            if dx >= abs(dy):
                canvas.pixel(x0, y0 + 1, color)
            else:
                canvas.pixel(x0 + 1, y0, color)
        else:
            half = width // 2
            for oy in range(-half, half + 1):
                for ox in range(-half, half + 1):
                    canvas.pixel(x0 + ox, y0 + oy, color)
        if x0 == x1 and y0 == y1:
            return
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def _draw_polygon_geometry(
    canvas: PixelCanvas,
    rect: Rect,
    coordinates: Any,
    extent: int,
    color: Color,
) -> None:
    for polygon in coordinates:
        if not polygon:
            continue
        outer = [_tile_to_screen(point, rect, extent) for point in polygon[0]]
        holes = [[_tile_to_screen(point, rect, extent) for point in hole] for hole in polygon[1:]]
        _fill_polygon(canvas, rect, outer, holes, color)


def _fill_polygon(
    canvas: PixelCanvas,
    rect: Rect,
    outer_ring: list[tuple[float, float]],
    holes: list[list[tuple[float, float]]],
    color: Color,
) -> None:
    if len(outer_ring) < 3:
        return

    min_x = max(rect.x, int(min(point[0] for point in outer_ring)))
    max_x = min(rect.right - 1, int(max(point[0] for point in outer_ring)))
    min_y = max(rect.y, int(min(point[1] for point in outer_ring)))
    max_y = min(rect.bottom - 1, int(max(point[1] for point in outer_ring)))

    for y in range(min_y, max_y + 1):
        for x in range(min_x, max_x + 1):
            px = x + 0.5
            py = y + 0.5
            if not _point_in_ring(px, py, outer_ring):
                continue
            if any(_point_in_ring(px, py, hole) for hole in holes):
                continue
            canvas.pixel(x, y, color)


def _point_in_ring(px: float, py: float, ring: list[tuple[float, float]]) -> bool:
    if len(ring) < 3:
        return False
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        intersects = ((yi > py) != (yj > py)) and (
            px < ((xj - xi) * (py - yi) / ((yj - yi) if (yj - yi) != 0 else 1e-9) + xi)
        )
        if intersects:
            inside = not inside
        j = i
    return inside
