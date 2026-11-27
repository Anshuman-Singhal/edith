"""Private shim for the D1 ``edith_common`` API (geo + clock).

Uses ``edith_common.geo`` / ``edith_common.clock`` when present (D1), otherwise a minimal local
fallback with the same names. Delete the fallback once D1 is on main.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

try:  # D1
    from edith_common.geo import CE90_K, Origin, enu_to_lla, lla_to_enu  # type: ignore
except Exception:  # pragma: no cover - exercised only before D1 merges
    import pymap3d

    CE90_K = 2.146

    @dataclass(frozen=True)
    class Origin:  # type: ignore[no-redef]
        lat: float
        lon: float
        alt_msl_m: float = 0.0
        geoid_n_m: float = 0.0

    def lla_to_enu(lat, lon, alt_msl_m, origin):  # type: ignore[no-redef]
        e, n, u = pymap3d.geodetic2enu(lat, lon, alt_msl_m, origin.lat, origin.lon,
                                       origin.alt_msl_m)
        return float(e), float(n), float(u)

    def enu_to_lla(e, n, u, origin):  # type: ignore[no-redef]
        la, lo, al = pymap3d.enu2geodetic(e, n, u, origin.lat, origin.lon, origin.alt_msl_m)
        return float(la), float(lo), float(al)

try:  # D1
    from edith_common.clock import ScaledClock  # type: ignore
except Exception:  # pragma: no cover
    import os

    class ScaledClock:  # type: ignore[no-redef]
        def __init__(self, t0_ns: int, speed: float = 1.0):
            self.t0_ns, self.speed = int(t0_ns), float(speed)

        @classmethod
        def from_env(cls) -> ScaledClock:
            t0 = int(os.environ.get("EDITH_T0_NS", (time.time_ns() // 10**6) * 10**6))
            return cls(t0, float(os.environ.get("EDITH_SPEED", "1.0")))

        def now_ns(self) -> int:
            return int(self.t0_ns + (time.time_ns() - self.t0_ns) * self.speed)

        def now_ms(self) -> int:
            return self.now_ns() // 1_000_000


PIATT_ORIGIN = Origin(40.0700, -88.6300, 210.0, -33.0)


def port(base: int, i: int = 0) -> int:
    """Port ``base + i`` shifted by ``EDITH_PORT_BASE`` (C77)."""
    import os

    return base + i + int(os.environ.get("EDITH_PORT_BASE", "0") or 0)


def hypot(*a: float) -> float:
    return math.sqrt(sum(x * x for x in a))
