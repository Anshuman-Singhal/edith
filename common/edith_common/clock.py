"""ScaledClock (interfaces §1, C61, C94).

    now_ns = T0 + (wall_ns − T0) × speed

so timestamps stay epoch-like. The supervisor exports EDITH_T0_NS and EDITH_SPEED; every
process builds its clock with `ScaledClock.from_env()`, so all processes agree.
"""

from __future__ import annotations

import asyncio
import os
import time

__all__ = ["ScaledClock", "ENV_T0", "ENV_SPEED"]

ENV_T0 = "EDITH_T0_NS"
ENV_SPEED = "EDITH_SPEED"

# Default T0 when EDITH_T0_NS is unset: wall time at import, rounded down to the second.
_IMPORT_T0_NS = (time.time_ns() // 1_000_000_000) * 1_000_000_000


class ScaledClock:
    __slots__ = ("_t0", "_speed", "_int_speed")

    def __init__(self, t0_ns: int, speed: float = 1.0):
        speed = float(speed)
        if not speed > 0 or speed != speed:
            raise ValueError(f"speed must be > 0, got {speed!r}")
        self._t0 = int(t0_ns)
        self._speed = speed
        self._int_speed = int(speed) if speed.is_integer() else None

    @classmethod
    def from_env(cls, environ: dict | None = None) -> ScaledClock:
        env = os.environ if environ is None else environ
        t0 = env.get(ENV_T0)
        speed = env.get(ENV_SPEED)
        return cls(int(t0) if t0 else _IMPORT_T0_NS, float(speed) if speed else 1.0)

    @staticmethod
    def env(t0_ns: int, speed: float) -> dict[str, str]:
        """Environment variables that make `from_env()` reproduce this clock."""
        return {ENV_T0: str(int(t0_ns)), ENV_SPEED: repr(float(speed))}

    @property
    def t0_ns(self) -> int:
        return self._t0

    @property
    def speed(self) -> float:
        return self._speed

    def scale_wall_ns(self, wall_ns: int) -> int:
        d = int(wall_ns) - self._t0
        if self._int_speed is not None:
            return self._t0 + d * self._int_speed
        return self._t0 + round(d * self._speed)

    def now_ns(self) -> int:
        return self.scale_wall_ns(time.time_ns())

    def now_ms(self) -> int:
        return self.now_ns() // 1_000_000

    def now_s(self) -> float:
        return self.now_ns() / 1e9

    def wall_to_sim_s(self, wall_s: float) -> float:
        return float(wall_s) * self._speed

    def sim_to_wall_s(self, sim_s: float) -> float:
        return float(sim_s) / self._speed

    def sleep(self, sim_s: float) -> None:
        if sim_s > 0:
            time.sleep(self.sim_to_wall_s(sim_s))

    async def asleep(self, sim_s: float) -> None:
        await asyncio.sleep(max(0.0, self.sim_to_wall_s(sim_s)))

    def __repr__(self) -> str:
        return f"ScaledClock(t0_ns={self._t0}, speed={self._speed})"
