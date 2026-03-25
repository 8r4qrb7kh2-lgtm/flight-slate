from __future__ import annotations

from setuptools import Extension, find_packages, setup


def build_extensions() -> list[Extension]:
    try:
        from pybind11.setup_helpers import Pybind11Extension
    except Exception:
        return []

    return [
        Pybind11Extension(
            "ui.native._render_native",
            ["ui/native/render_native.cpp"],
            cxx_std=17,
        )
    ]


setup(
    name="flight-slate",
    version="0.1.0",
    packages=find_packages(include=["ui", "ui.*"]),
    ext_modules=build_extensions(),
)
