"""Airline callsign → logo resolution."""

from __future__ import annotations

import functools
from pathlib import Path

from ui.core.image_asset import ImageFrame, load_png_image_frame


ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets" / "airlines"


# ICAO airline code → logo filename (under assets/airlines/).
# Covers every logo currently shipped with the project.
_AIRLINE_LOGOS: dict[str, str] = {
    "ACA": "airlines-air-canada-48.png",
    "ASA": "airlines-alaskan-48.png",
    "AAY": "airlines-allegiant-48.png",
    "PCM": "airlines-amazon-48.png",  # Amazon Air via ATSG carriers
    "GTI": "airlines-amazon-48.png",
    "AAL": "airlines-american-48.png",
    "MXY": "airlines-breeze-48.png",
    "DAL": "airlines-delta-48.png",
    "DHL": "airlines-dh-48l.png",
    "DHK": "airlines-dh-48l.png",
    "FDX": "airlines-fedex-48.png",
    "FFT": "airlines-frontier-48.png",
    "JBU": "airlines-jetblue-48.png",
    "SWA": "airlines-southwest-48.png",
    "NKS": "airlines-spirit-48.png",
    "UAL": "airlines-united-48.png",
    "UPS": "airlines-ups-48.png",
}


# IATA 2-letter codes that sometimes show up in consumer feeds instead of ICAO.
_IATA_TO_ICAO: dict[str, str] = {
    "AC": "ACA",
    "AS": "ASA",
    "G4": "AAY",
    "AA": "AAL",
    "MX": "MXY",
    "DL": "DAL",
    "DH": "DHL",
    "FX": "FDX",
    "F9": "FFT",
    "B6": "JBU",
    "WN": "SWA",
    "NK": "NKS",
    "UA": "UAL",
    "5X": "UPS",
}


def resolve_airline_from_callsign(callsign: str | None) -> str | None:
    """Return a 3-letter ICAO code from a callsign's prefix, or None if unknown."""
    if not callsign:
        return None
    head = callsign[:3].upper()
    if head.isalpha():
        return head
    iata = callsign[:2].upper()
    return _IATA_TO_ICAO.get(iata)


@functools.lru_cache(maxsize=64)
def load_airline_logo(airline_icao: str | None) -> ImageFrame | None:
    """Load the airline logo PNG for the given ICAO code, or None if missing."""
    if not airline_icao:
        return None
    logo_name = _AIRLINE_LOGOS.get(airline_icao.upper())
    if logo_name is None:
        return None
    logo_path = ASSETS_DIR / logo_name
    if not logo_path.exists():
        return None
    try:
        return load_png_image_frame(logo_path)
    except Exception:
        return None
