#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

namespace py = pybind11;

struct ClipRect {
    int x;
    int y;
    int right;
    int bottom;
};

class NativeCanvas {
public:
    NativeCanvas(int width, int height, py::tuple background)
        : width_(width), height_(height), pixels_(static_cast<size_t>(width) * static_cast<size_t>(height) * 3U, 0) {
        if (width_ <= 0 || height_ <= 0) {
            throw std::invalid_argument("width and height must be positive");
        }
        const auto [r, g, b] = to_rgb(background);
        clear(rgb_tuple(r, g, b));
    }

    int width() const { return width_; }

    int height() const { return height_; }

    py::bytes to_bytes() const {
        return py::bytes(reinterpret_cast<const char*>(pixels_.data()), static_cast<py::ssize_t>(pixels_.size()));
    }

    py::tuple get_pixel(int x, int y) const {
        if (!in_bounds(x, y)) {
            throw std::out_of_range("pixel coordinates out of bounds");
        }
        size_t base = pixel_base(x, y);
        return rgb_tuple(pixels_[base], pixels_[base + 1], pixels_[base + 2]);
    }

    void clear(py::tuple color) {
        const auto [r, g, b] = to_rgb(color);
        for (size_t i = 0; i < pixels_.size(); i += 3U) {
            pixels_[i] = r;
            pixels_[i + 1] = g;
            pixels_[i + 2] = b;
        }
    }

    void push_clip(int x, int y, int width, int height) {
        if (width <= 0 || height <= 0) {
            clip_stack_.push_back({0, 0, 0, 0});
            return;
        }
        clip_stack_.push_back({x, y, x + width, y + height});
    }

    void pop_clip() {
        if (!clip_stack_.empty()) {
            clip_stack_.pop_back();
        }
    }

    void pixel(int x, int y, py::tuple color) {
        if (!inside_clip(x, y)) {
            return;
        }
        const auto [r, g, b] = to_rgb(color);
        set_pixel_unchecked(x, y, r, g, b);
    }

    void blend_pixel(int x, int y, py::tuple color, double alpha) {
        if (!inside_clip(x, y) || alpha <= 0.0) {
            return;
        }
        if (alpha >= 1.0) {
            pixel(x, y, color);
            return;
        }

        const auto [r, g, b] = to_rgb(color);
        size_t base = pixel_base(x, y);
        pixels_[base] = blend_channel(pixels_[base], r, alpha);
        pixels_[base + 1] = blend_channel(pixels_[base + 1], g, alpha);
        pixels_[base + 2] = blend_channel(pixels_[base + 2], b, alpha);
    }

    void hline(int x, int y, int width, py::tuple color) {
        if (width <= 0) {
            return;
        }
        const auto [r, g, b] = to_rgb(color);
        for (int i = 0; i < width; ++i) {
            if (inside_clip(x + i, y)) {
                set_pixel_unchecked(x + i, y, r, g, b);
            }
        }
    }

    void vline(int x, int y, int height, py::tuple color) {
        if (height <= 0) {
            return;
        }
        const auto [r, g, b] = to_rgb(color);
        for (int i = 0; i < height; ++i) {
            if (inside_clip(x, y + i)) {
                set_pixel_unchecked(x, y + i, r, g, b);
            }
        }
    }

    void fill_rect(int x, int y, int width, int height, py::tuple color) {
        if (width <= 0 || height <= 0) {
            return;
        }
        const auto [r, g, b] = to_rgb(color);
        for (int row = 0; row < height; ++row) {
            for (int col = 0; col < width; ++col) {
                const int px = x + col;
                const int py = y + row;
                if (inside_clip(px, py)) {
                    set_pixel_unchecked(px, py, r, g, b);
                }
            }
        }
    }

    void outline_rect(int x, int y, int width, int height, py::tuple color) {
        if (width <= 0 || height <= 0) {
            return;
        }
        hline(x, y, width, color);
        hline(x, y + height - 1, width, color);
        vline(x, y, height, color);
        vline(x + width - 1, y, height, color);
    }

    void draw_text(
        int x,
        int y,
        const std::string& text,
        py::tuple color,
        int scale,
        int spacing,
        int space_width,
        py::dict glyph_map,
        py::tuple fallback_glyph
    ) {
        if (scale <= 0) {
            return;
        }

        const auto [r, g, b] = to_rgb(color);
        int cursor_x = x;
        const auto fallback = decode_glyph_tuple(fallback_glyph);

        for (size_t i = 0; i < text.size(); ++i) {
            const char ch = text[i];
            if (ch == '\n' || ch == '\r') {
                continue;
            }

            GlyphData glyph;
            bool draw = true;

            if (ch == '\t') {
                glyph = GlyphData{space_width * 4, {}};
                draw = false;
            } else if (std::isspace(static_cast<unsigned char>(ch))) {
                glyph = GlyphData{space_width, {}};
                draw = false;
            } else {
                py::object key = py::str(std::string(1, ch));
                if (glyph_map.contains(key)) {
                    glyph = decode_glyph_tuple(glyph_map[key]);
                } else {
                    glyph = fallback;
                }
            }

            if (draw) {
                draw_glyph(cursor_x, y, glyph, r, g, b, scale);
            }

            cursor_x += glyph.width * scale;
            if (i + 1 < text.size()) {
                cursor_x += spacing * scale;
            }
        }
    }

private:
    struct GlyphData {
        int width;
        std::vector<uint32_t> row_masks;
    };

    int width_;
    int height_;
    std::vector<uint8_t> pixels_;
    std::vector<ClipRect> clip_stack_;

    static uint8_t blend_channel(uint8_t base, uint8_t top, double alpha) {
        const double value = std::round(static_cast<double>(base) + (static_cast<double>(top) - static_cast<double>(base)) * alpha);
        return static_cast<uint8_t>(std::clamp<int>(static_cast<int>(value), 0, 255));
    }

    static std::tuple<uint8_t, uint8_t, uint8_t> to_rgb(const py::tuple& color) {
        if (py::len(color) != 3) {
            throw std::invalid_argument("color must be a 3-tuple");
        }
        return {
            clamp_channel(py::cast<int>(color[0])),
            clamp_channel(py::cast<int>(color[1])),
            clamp_channel(py::cast<int>(color[2]))
        };
    }

    static uint8_t clamp_channel(int value) {
        return static_cast<uint8_t>(std::clamp(value, 0, 255));
    }

    static py::tuple rgb_tuple(uint8_t r, uint8_t g, uint8_t b) {
        return py::make_tuple(static_cast<int>(r), static_cast<int>(g), static_cast<int>(b));
    }

    bool in_bounds(int x, int y) const {
        return x >= 0 && y >= 0 && x < width_ && y < height_;
    }

    bool inside_clip(int x, int y) const {
        if (!in_bounds(x, y)) {
            return false;
        }
        for (const auto& clip : clip_stack_) {
            if (!(x >= clip.x && x < clip.right && y >= clip.y && y < clip.bottom)) {
                return false;
            }
        }
        return true;
    }

    size_t pixel_base(int x, int y) const {
        return (static_cast<size_t>(y) * static_cast<size_t>(width_) + static_cast<size_t>(x)) * 3U;
    }

    void set_pixel_unchecked(int x, int y, uint8_t r, uint8_t g, uint8_t b) {
        if (!in_bounds(x, y)) {
            return;
        }
        size_t base = pixel_base(x, y);
        pixels_[base] = r;
        pixels_[base + 1] = g;
        pixels_[base + 2] = b;
    }

    static GlyphData decode_glyph_tuple(const py::handle& glyph_tuple_handle) {
        py::tuple glyph_tuple = py::reinterpret_borrow<py::tuple>(glyph_tuple_handle);
        if (py::len(glyph_tuple) != 2) {
            throw std::invalid_argument("glyph must be (width, row_masks)");
        }

        GlyphData glyph;
        glyph.width = py::cast<int>(glyph_tuple[0]);
        py::tuple rows = py::cast<py::tuple>(glyph_tuple[1]);
        glyph.row_masks.reserve(static_cast<size_t>(py::len(rows)));
        for (py::handle value : rows) {
            glyph.row_masks.push_back(py::cast<uint32_t>(value));
        }
        return glyph;
    }

    void draw_glyph(int x, int y, const GlyphData& glyph, uint8_t r, uint8_t g, uint8_t b, int scale) {
        if (glyph.width <= 0) {
            return;
        }

        for (size_t row_index = 0; row_index < glyph.row_masks.size(); ++row_index) {
            uint32_t mask = glyph.row_masks[row_index];
            for (int col = 0; col < glyph.width; ++col) {
                const int shift = glyph.width - 1 - col;
                if (((mask >> shift) & 1U) == 0U) {
                    continue;
                }
                for (int sy = 0; sy < scale; ++sy) {
                    for (int sx = 0; sx < scale; ++sx) {
                        const int px = x + col * scale + sx;
                        const int py = y + static_cast<int>(row_index) * scale + sy;
                        if (inside_clip(px, py)) {
                            set_pixel_unchecked(px, py, r, g, b);
                        }
                    }
                }
            }
        }
    }
};

PYBIND11_MODULE(_render_native, m) {
    m.doc() = "Native rendering backend for flight-slate core UI";

    py::class_<NativeCanvas>(m, "NativeCanvas")
        .def(py::init<int, int, py::tuple>())
        .def_property_readonly("width", &NativeCanvas::width)
        .def_property_readonly("height", &NativeCanvas::height)
        .def("to_bytes", &NativeCanvas::to_bytes)
        .def("get_pixel", &NativeCanvas::get_pixel)
        .def("clear", &NativeCanvas::clear)
        .def("push_clip", &NativeCanvas::push_clip)
        .def("pop_clip", &NativeCanvas::pop_clip)
        .def("pixel", &NativeCanvas::pixel)
        .def("blend_pixel", &NativeCanvas::blend_pixel)
        .def("hline", &NativeCanvas::hline)
        .def("vline", &NativeCanvas::vline)
        .def("fill_rect", &NativeCanvas::fill_rect)
        .def("outline_rect", &NativeCanvas::outline_rect)
        .def("draw_text", &NativeCanvas::draw_text);
}
