"""Offline geocoder for H1B LOCATION strings.

Loads data/lookups/us_cities.csv (from
https://github.com/kelvins/US-Cities-Database) and resolves LOCATION values
like 'MOUNTAIN VIEW, CA' to (lat, lon).

Disambiguation:
- (city, state) is the primary key; state is required.
- When several rows share (city, state), we pick the one with the most
  letters in CITY as a deterministic tiebreak. This is crude but fine for
  plotting: both entries are usually nearby suburbs of the same metro.
- Common name variants are normalised (e.g. 'ST.' -> 'SAINT', 'MT.' -> 'MOUNT').
- Unresolved locations return None and are ignored by the caller.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CITY_DB = PROJECT_ROOT / "data" / "lookups" / "us_cities.csv"

_LOC_RE = re.compile(r"^\s*(.+?)\s*,+\s*([A-Za-z]{2})\s*$")

_ALIASES: Dict[tuple[str, str], tuple[str, str]] = {
    # (input city upper, state) -> (DB city upper, state)
    ("WINSTON SALEM", "NC"): ("WINSTON-SALEM", "NC"),
    # Unincorporated or adjacent census-designated places -> nearest city in DB
    ("MOFFETT FIELD", "CA"): ("MOUNTAIN VIEW", "CA"),
    ("NASA AMES RESEARCH CENTER", "CA"): ("MOUNTAIN VIEW", "CA"),
    ("REDWOOD SHORES", "CA"): ("REDWOOD CITY", "CA"),
    ("PLAYA VISTA", "CA"): ("LOS ANGELES", "CA"),
    ("MARINA DEL REY", "CA"): ("LOS ANGELES", "CA"),
    ("ALOHA", "OR"): ("BEAVERTON", "OR"),
    ("TIMONIUM", "MD"): ("LUTHERVILLE TIMONIUM", "MD"),
    ("FOSTER CITY", "CA"): ("SAN MATEO", "CA"),
    ("MOUNTAIN HOUSE", "CA"): ("TRACY", "CA"),
    ("SILICON VALLEY", "CA"): ("SAN JOSE", "CA"),
    ("NEW YORK CITY", "NY"): ("NEW YORK", "NY"),
    # Common typos
    ("SAN FRANCSICO", "CA"): ("SAN FRANCISCO", "CA"),
    ("SAN FRANCISO", "CA"): ("SAN FRANCISCO", "CA"),
    ("MOUTAIN VIEW", "CA"): ("MOUNTAIN VIEW", "CA"),
    # Name variants / CDP -> city
    ("WASHINGTON DC", "DC"): ("WASHINGTON", "DC"),
    ("WASHINGTON D.C.", "DC"): ("WASHINGTON", "DC"),
    ("ST. LOUIS", "MO"): ("SAINT LOUIS", "MO"),
    ("QUEENS", "NY"): ("NEW YORK", "NY"),
    ("BROOKLYN", "NY"): ("NEW YORK", "NY"),
    ("BRONX", "NY"): ("NEW YORK", "NY"),
    ("MCLEAN", "VA"): ("VIENNA", "VA"),
    ("FARMERS BRANCH", "TX"): ("DALLAS", "TX"),
    ("NEWCASTLE", "WA"): ("BELLEVUE", "WA"),
    ("CULVER", "CA"): ("LOS ANGELES", "CA"),
    ("HENRICO", "VA"): ("RICHMOND", "VA"),
    ("FARMINGTON HILLS", "MI"): ("FARMINGTON", "MI"),
}


def _normalise(city: str) -> str:
    city = city.strip().upper()
    city = re.sub(r"\bST\.?\b", "SAINT", city)
    city = re.sub(r"\bMT\.?\b", "MOUNT", city)
    city = re.sub(r"\bFT\.?\b", "FORT", city)
    city = re.sub(r"\s+", " ", city)
    return city


@lru_cache(maxsize=1)
def _load_lookup() -> Dict[Tuple[str, str], Tuple[float, float]]:
    if not CITY_DB.exists():
        raise FileNotFoundError(
            f"Missing {CITY_DB}. Download from "
            "https://github.com/kelvins/US-Cities-Database/blob/main/csv/us_cities.csv"
        )
    raw = pd.read_csv(CITY_DB)
    raw = raw.rename(
        columns={
            "CITY": "city",
            "STATE_CODE": "state",
            "LATITUDE": "lat",
            "LONGITUDE": "lon",
        }
    )
    raw["city_up"] = raw["city"].astype(str).map(_normalise)
    raw = raw.sort_values("city", key=lambda s: s.str.len(), ascending=False)
    raw = raw.drop_duplicates(subset=["city_up", "state"], keep="first")
    out = {
        (row.city_up, row.state): (float(row.lat), float(row.lon))
        for row in raw.itertuples()
    }
    return out


def geocode_location(location: str) -> Optional[Tuple[float, float]]:
    """Resolve 'CITY, ST' (or similar) to (lat, lon) or None."""
    if not isinstance(location, str):
        return None
    m = _LOC_RE.match(location)
    if not m:
        return None
    city_raw, state = m.group(1), m.group(2).upper()
    city = _normalise(city_raw)

    alias = _ALIASES.get((city, state))
    if alias is not None:
        city = _normalise(alias[0])
        state = alias[1]

    lookup = _load_lookup()
    hit = lookup.get((city, state))
    if hit is not None:
        return hit

    # Fallback: try stripping trailing directional/qualifier words
    stripped = re.sub(r"\b(EAST|WEST|NORTH|SOUTH|NE|NW|SE|SW)\b", "", city).strip()
    stripped = re.sub(r"\s+", " ", stripped)
    if stripped and stripped != city:
        hit = lookup.get((stripped, state))
        if hit is not None:
            return hit

    return None


def coverage_report(df: pd.DataFrame, column: str = "LOCATION") -> dict:
    total = df[column].notna().sum()
    resolved = df[column].dropna().map(lambda x: geocode_location(x) is not None).sum()
    return {"total": int(total), "resolved": int(resolved), "hit_rate": resolved / total if total else 0.0}


if __name__ == "__main__":
    samples = [
        "MOUNTAIN VIEW, CA",
        "NEW YORK, NY",
        "REDMOND, WA",
        "WINSTON SALEM, NC",
        "ST. LOUIS, MO",
        "BROOMFIELD, CO",
        "NOWHERE LAND, XX",
    ]
    for s in samples:
        print(f"{s!r:35} -> {geocode_location(s)}")
