"""Geodesy helpers (interfaces §1 "Geo", C57, C65). WGS-84 throughout.

- ENU <-> LLA via pymap3d. Altitudes in and out are MSL; the site geoid constant
  `Origin.geoid_n_m` converts to ellipsoid height (hae = msl + N) internally.
- MGRS via the `mgrs` package. `to_mgrs` truncates (standard MGRS); `from_mgrs` returns the
  centre of the grid cell, so a 5-digit round trip is within 0.71 m.
- Bearing/range are WGS-84 geodesics (pymap3d Vincenty inverse).
- Clock wording, CE90 helpers and the banner range label (hud §6, C65).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

import mgrs as _mgrs
import pymap3d
from pymap3d import vincenty

__all__ = [
    "CE90_K",
    "SCENARIO_ORIGIN",
    "SCENARIO_ORIGIN_MGRS",
    "Origin",
    "bearing_deg",
    "bearing_enu_deg",
    "bearing_from_clock",
    "ce90_from_sigma",
    "clock_from_bearing",
    "clock_hour",
    "enu_to_lla",
    "from_mgrs",
    "hae_m",
    "lla_to_enu",
    "range_label",
    "range_m",
    "round_range_m",
    "sigma_from_ce90",
    "to_mgrs",
    "wrap180",
    "wrap360",
]

CE90_K = 2.146  # CE90 radius = 2.146 sigma for a circular bivariate normal (C57)


@dataclass(frozen=True, slots=True)
class Origin:
    """ENU origin. `alt_msl_m` is the origin's MSL altitude; `geoid_n_m` is the site geoid
    separation N (EGM96, ≈ −33 m at the Piatt County site, UNVERIFIED), so hae = msl + N."""

    lat: float
    lon: float
    alt_msl_m: float = 0.0
    geoid_n_m: float = 0.0


# Demo site (PLAN §3.6, C13): 40.0700 N, 88.6300 W, 210 m MSL -> MGRS 16TCK 61002 36799.
SCENARIO_ORIGIN = Origin(lat=40.0700, lon=-88.6300, alt_msl_m=210.0, geoid_n_m=-33.0)
SCENARIO_ORIGIN_MGRS = "16TCK6100236799"


def wrap360(d: float) -> float:
    """Wrap to [0, 360)."""
    r = math.fmod(float(d), 360.0)
    if r < 0:
        r += 360.0
    return 0.0 if r >= 360.0 else r


def wrap180(d: float) -> float:
    """Wrap to [-180, 180)."""
    return wrap360(float(d) + 180.0) - 180.0


def hae_m(alt_msl_m: float, origin: Origin) -> float:
    return float(alt_msl_m) + origin.geoid_n_m


def lla_to_enu(lat: float, lon: float, alt_msl_m: float, origin: Origin) -> tuple[float, float, float]:
    e, n, u = pymap3d.geodetic2enu(
        lat, lon, hae_m(alt_msl_m, origin),
        origin.lat, origin.lon, hae_m(origin.alt_msl_m, origin),
    )
    return float(e), float(n), float(u)


def enu_to_lla(e: float, n: float, u: float, origin: Origin) -> tuple[float, float, float]:
    lat, lon, h = pymap3d.enu2geodetic(
        e, n, u, origin.lat, origin.lon, hae_m(origin.alt_msl_m, origin)
    )
    return float(lat), float(lon), float(h) - origin.geoid_n_m


@lru_cache(maxsize=1)
def _m() -> _mgrs.MGRS:
    return _mgrs.MGRS()


def to_mgrs(lat: float, lon: float, digits: int = 5) -> str:
    """MGRS string with no spaces, e.g. "16TCK6100236799" (digits per axis, 0..5)."""
    if not 0 <= digits <= 5:
        raise ValueError("digits must be 0..5")
    s = _m().toMGRS(float(lat), float(lon), MGRSPrecision=digits)
    return s.decode() if isinstance(s, bytes) else str(s)


def from_mgrs(s: str) -> tuple[float, float]:
    """(lat, lon) of the centre of the MGRS cell. Spaces are ignored."""
    lat, lon = _m().toLatLon("".join(s.split()).upper())
    return float(lat), float(lon)


def _inverse(lat1: float, lon1: float, lat2: float, lon2: float) -> tuple[float, float]:
    dist, az = vincenty.vdist(lat1, lon1, lat2, lon2)
    return float(dist), wrap360(float(az))


def range_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Geodesic distance on WGS-84 (metres)."""
    return _inverse(lat1, lon1, lat2, lon2)[0]


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial geodesic bearing from point 1 to point 2, degrees true [0, 360)."""
    return _inverse(lat1, lon1, lat2, lon2)[1]


def bearing_enu_deg(de: float, dn: float) -> float:
    """Bearing of an ENU offset, degrees clockwise from north [0, 360)."""
    return wrap360(math.degrees(math.atan2(de, dn)))


def clock_hour(rel_deg: float) -> int:
    """Relative bearing -> clock hour 1..12 (12 = dead ahead, 30° sectors centred on hours)."""
    h = int(math.floor(wrap360(rel_deg) / 30.0 + 0.5)) % 12
    return 12 if h == 0 else h


def clock_from_bearing(rel_deg: float) -> str:
    """Relative bearing -> "2 o'clock" (clock_from_bearing(62) == "2 o'clock")."""
    return f"{clock_hour(rel_deg)} o'clock"


def bearing_from_clock(hour: int, heading_deg: float) -> float:
    """Clock hour relative to `heading_deg` -> true bearing [0, 360)."""
    if not 1 <= int(hour) <= 12:
        raise ValueError("hour must be 1..12")
    return wrap360(heading_deg + (int(hour) % 12) * 30.0)


def sigma_from_ce90(ce_m: float) -> float:
    return float(ce_m) / CE90_K


def ce90_from_sigma(sigma_m: float) -> float:
    return float(sigma_m) * CE90_K


def _step_m(ce_m: float | None) -> int:
    """Rounding step: max(50 m, ce_m), taken up to a whole multiple of 50 m so the banner only
    ever shows 50 m multiples (interfaces §4, C65)."""
    ce = 0.0 if ce_m is None else max(0.0, float(ce_m))
    return 50 * max(1, math.ceil(max(50.0, ce) / 50.0 - 1e-9))


def round_range_m(range_m: float, ce_m: float | None = None) -> int:
    """Range rounded to the nearest step (see `_step_m`), never below one step."""
    step = _step_m(ce_m)
    r = max(0.0, float(range_m))
    return max(step, int(math.floor(r / step + 0.5)) * step)


def range_label(range_m: float, ce_m: float | None = None) -> str:
    """Banner range: "~400 m" below 1 km; "~" dropped at ≥1 km: "1.2 km" (C65)."""
    r = round_range_m(range_m, ce_m)
    if r < 1000:
        return f"~{r} m"
    # One decimal of km: re-round the raw range to max(100 m, step) in 100 m units.
    step = 100 * math.ceil(_step_m(ce_m) / 100)
    km = max(1000, int(math.floor(max(0.0, float(range_m)) / step + 0.5)) * step)
    return f"{km / 1000:.1f} km"
