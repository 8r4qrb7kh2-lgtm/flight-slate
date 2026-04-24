"""Static airport lookup sourced from OpenFlights airports.dat.

Enriches API results that return IATA codes only (e.g. AirLabs) with the
coordinates and city names needed for plausibility checking and the
dep/arr footer display.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import cache
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "airports.dat"


@dataclass(frozen=True)
class Airport:
    iata: str
    city: str
    latitude: float
    longitude: float


@cache
def _index() -> dict[str, Airport]:
    idx: dict[str, Airport] = {}
    if not DATA_FILE.exists():
        return idx
    with DATA_FILE.open("r", encoding="utf-8", newline="") as fp:
        for row in csv.reader(fp):
            if len(row) < 8:
                continue
            iata = row[4].strip()
            if not iata or iata == "\\N" or len(iata) != 3:
                continue
            try:
                lat = float(row[6])
                lon = float(row[7])
            except ValueError:
                continue
            idx[iata.upper()] = Airport(
                iata=iata.upper(),
                city=row[2].strip(),
                latitude=lat,
                longitude=lon,
            )
    return idx


def lookup(iata: str | None) -> Airport | None:
    if not iata:
        return None
    return _index().get(iata.strip().upper())
