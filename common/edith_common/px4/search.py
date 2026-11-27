"""Lawnmower search planner shared by ``AssetAdapter.search`` and the lint pre-run (C87).

Legs run north-south (leg 1 is flown north, from the west edge). Spacing is the centre-line
ground width × (1 − overlap); the leg count is ``ceil(width_e / spacing)`` and the legs are
spread evenly, one at the centre of each strip, so the real overlap is ≥ the requested one.
At 60 m AGL, pitch −60°, HFOV 70°, overlap 0.3 the nominal spacing is ≈68 m, which gives 5 legs
at 60 m for a 300 m square (legs at −120, −60, 0, 60, 120 m east of its centre).
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def centre_ground_width_m(alt_agl_m: float, hfov_deg: float, pitch_deg: float) -> float:
    """Ground width across the optical axis where it meets the ground (flat earth)."""
    dep = math.radians(abs(pitch_deg))
    if dep <= 0:
        raise ValueError("pitch must point below the horizon")
    slant = alt_agl_m / math.sin(dep)
    return 2.0 * slant * math.tan(math.radians(hfov_deg) / 2.0)


def leg_spacing_m(alt_agl_m: float, hfov_deg: float = 70.0, pitch_deg: float = -60.0,
                  overlap: float = 0.3) -> float:
    return centre_ground_width_m(alt_agl_m, hfov_deg, pitch_deg) * (1.0 - overlap)


def _span_at_e(polygon: Sequence[tuple[float, float]], x: float) -> tuple[float, float] | None:
    ys = []
    n = len(polygon)
    for i in range(n):
        (x1, y1), (x2, y2) = polygon[i], polygon[(i + 1) % n]
        if x1 == x2:
            if abs(x - x1) < 1e-9:
                ys += [y1, y2]
            continue
        if min(x1, x2) - 1e-9 <= x <= max(x1, x2) + 1e-9:
            ys.append(y1 + (y2 - y1) * (x - x1) / (x2 - x1))
    return (min(ys), max(ys)) if ys else None


def plan_search(polygon: Sequence[tuple[float, float]], alt_agl_m: float, *,
                overlap: float = 0.3, hfov_deg: float = 70.0,
                pitch_deg: float = -60.0) -> list[tuple[float, float, float]]:
    """Return lawnmower waypoints ``[(e, n, alt_agl_m), …]`` for a convex ENU polygon (m)."""
    if len(polygon) < 3:
        raise ValueError("polygon needs ≥3 vertices")
    spacing = leg_spacing_m(alt_agl_m, hfov_deg, pitch_deg, overlap)
    xs = [p[0] for p in polygon]
    x0, x1 = min(xs), max(xs)
    width = x1 - x0
    n_legs = max(1, math.ceil(width / spacing - 1e-9))
    step = width / n_legs
    wps: list[tuple[float, float, float]] = []
    for i in range(n_legs):
        x = x0 + (i + 0.5) * step
        span = _span_at_e(polygon, x)
        if span is None:
            continue
        lo, hi = span
        ends = [(x, lo), (x, hi)] if i % 2 == 0 else [(x, hi), (x, lo)]
        wps += [(e, n, float(alt_agl_m)) for e, n in ends]
    return wps


def square(centre_e: float, centre_n: float, side_m: float) -> list[tuple[float, float]]:
    h = side_m / 2.0
    return [(centre_e - h, centre_n - h), (centre_e + h, centre_n - h),
            (centre_e + h, centre_n + h), (centre_e - h, centre_n + h)]
