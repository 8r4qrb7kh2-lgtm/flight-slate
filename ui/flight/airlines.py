"""Airline callsign → logo resolution."""

from __future__ import annotations

import functools
from pathlib import Path

from ui.core.image_asset import ImageFrame, load_png_image_frame


ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets" / "airlines"


# ICAO airline code → logo filename (under assets/airlines/).
# Pseudo-ICAOs (CCF, UNH, MHL, LFT) cover non-airline operators identified
# by N-number vanity suffix (e.g. medical helicopters).
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
    # Medical / air-ambulance operators in the Cleveland area.
    "CCF": "operators-cleveland-clinic-48.png",
    "UNH": "operators-university-hospitals-48.png",
    "MHL": "operators-metrohealth-48.png",
    "LFT": "operators-lifeflight-48.png",
    # STAT MedEvac (Pittsburgh-based, regional). Real callsign prefix is
    # "STAT" so the standard 3-letter resolver returns "STA"; map that here.
    "STA": "operators-stat-medevac-48.png",
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


# Vanity suffixes on N-number callsigns that identify non-airline operators.
# Matched against the trailing letters of e.g. "N431CC" → suffix "CC".
# Helicopters often broadcast their tail number as the callsign and use
# operator-meaningful letters at the end.
_N_NUMBER_OPERATOR_SUFFIXES: dict[str, str] = {
    "CC": "CCF",  # Cleveland Clinic Critical Care Transport
    "UH": "UNH",  # University Hospitals
    "MH": "MHL",  # MetroHealth (Metro Life Flight)
    "LF": "LFT",  # LifeFlight
    "MV": "STA",  # STAT MedEvac (e.g. N911MV)
}


def _n_number_suffix_match(callsign: str) -> str | None:
    """Match an N-number callsign to a known operator by its 2-letter suffix.

    Returns the pseudo-ICAO if the callsign looks like 'N' + digits + 2 letters
    and the suffix is in our table; otherwise None. Prevents bogus matches on
    non-N-number alpha strings.
    """
    if not callsign.startswith("N") or len(callsign) < 4:
        return None
    suffix = callsign[-2:]
    if not suffix.isalpha():
        return None
    middle = callsign[1:-2]
    if not middle or not middle.isdigit():
        return None
    return _N_NUMBER_OPERATOR_SUFFIXES.get(suffix)


def resolve_airline_from_callsign(callsign: str | None) -> str | None:
    """Return a 3-letter ICAO (real or pseudo) for the callsign, or None."""
    if not callsign:
        return None
    cs = callsign.strip().upper()
    head = cs[:3]
    if head.isalpha():
        return head
    iata = cs[:2]
    if iata in _IATA_TO_ICAO:
        return _IATA_TO_ICAO[iata]
    return _n_number_suffix_match(cs)


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
