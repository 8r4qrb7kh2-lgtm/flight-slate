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
def _indexes() -> tuple[dict[str, Airport], dict[str, Airport]]:
    """Build IATA and ICAO indexes in a single pass over airports.dat.

    OpenFlights has ~6k airports with IATA codes and another ~1.6k with
    only ICAO codes (small/private fields). The ICAO index is needed to
    resolve destinations like Custer (KTTF) that GA aircraft commonly
    head to but lack a public IATA code.
    """
    iata_idx: dict[str, Airport] = {}
    icao_idx: dict[str, Airport] = {}
    if not DATA_FILE.exists():
        return iata_idx, icao_idx
    with DATA_FILE.open("r", encoding="utf-8", newline="") as fp:
        for row in csv.reader(fp):
            if len(row) < 8:
                continue
            try:
                lat = float(row[6])
                lon = float(row[7])
            except ValueError:
                continue
            iata = row[4].strip().upper()
            icao = row[5].strip().upper()
            if iata == "\\N":
                iata = ""
            if icao == "\\N":
                icao = ""
            airport = Airport(
                iata=iata,
                city=row[2].strip(),
                latitude=lat,
                longitude=lon,
            )
            if iata and len(iata) == 3:
                iata_idx[iata] = airport
            if icao and len(icao) == 4:
                icao_idx[icao] = airport
    return iata_idx, icao_idx


def lookup(iata: str | None) -> Airport | None:
    if not iata:
        return None
    return _indexes()[0].get(iata.strip().upper())


def lookup_icao(icao: str | None) -> Airport | None:
    if not icao:
        return None
    return _indexes()[1].get(icao.strip().upper())
