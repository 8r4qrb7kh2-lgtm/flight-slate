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
    "EIN": "airlines-aer-lingus-48.png",
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
    "EI": "EIN",
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
    "UH": "UNH",  # University Hospitals (in-house registrations, if any)
    "MH": "MHL",  # MetroHealth (Metro Life Flight)
    "LF": "LFT",  # LifeFlight
    # STAT MedEvac fleet uses N###ME (for "MedEvac") most commonly, with
    # a smaller number on the older ``MV`` suffix. Both map to the same
    # logo since they belong to the same operator.
    "ME": "STA",
    "MV": "STA",
}


# Specific tail numbers that the suffix table can't disambiguate. PHI
# Health (``PH`` suffix) flies under contract for multiple hospital
# systems in Cleveland — the airframe registration alone doesn't tell
# you which one this trip belongs to, so we list them out one by one.
# Add more entries as new tails get observed; if a tail isn't in here
# the resolver falls through to no logo, which is preferable to
# guessing wrong about a med-evac mission.
_N_NUMBER_TAIL_OVERRIDES: dict[str, str] = {
    "N325PH": "UNH",  # University Hospitals med-evac (PHI airframe)
    "N344PH": "UNH",  # University Hospitals med-evac (PHI airframe)
}


def _n_number_suffix_match(callsign: str) -> str | None:
    """Match an N-number callsign to a known operator.

    Tail-number overrides win over the generic suffix table — required
    when the same suffix (e.g. ``PH`` for PHI airframes) is shared by
    multiple operators contracting from the same fleet.

    Returns the pseudo-ICAO if recognized, otherwise None. Validates the
    N-number shape so non-N-number alpha strings can't slip through.
    """
    if not callsign.startswith("N") or len(callsign) < 4:
        return None
    suffix = callsign[-2:]
    if not suffix.isalpha():
        return None
    middle = callsign[1:-2]
    if not middle or not middle.isdigit():
        return None
    override = _N_NUMBER_TAIL_OVERRIDES.get(callsign)
    if override is not None:
        return override
    return _N_NUMBER_OPERATOR_SUFFIXES.get(suffix)


def is_known_airline(airline_icao: str | None) -> bool:
    """True if we have a logo asset registered for this ICAO code.

    Used to validate FR24's ``painted_as`` (marketing-airline) field before
    overriding the operating-airline derived from the callsign — junky values
    (synthetic codes, blanks, charter brands) shouldn't replace clean data.
    """
    if not airline_icao:
        return False
    return airline_icao.upper() in _AIRLINE_LOGOS


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
