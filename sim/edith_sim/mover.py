"""Seeded entity / teammate mover (sim spec §5, §8). Pure function of (scenario, seed, t)."""

from __future__ import annotations

import hashlib
import json
import math
import random

from edith_sim.scenario.model import PathPt, Scenario


def interp_path(path: list[PathPt], t: float) -> tuple[float, float, float]:
    """(e, n, heading_deg) along a timed path; clamps at the ends."""
    if t <= path[0].t or len(path) == 1:
        p = path[0]
        nxt = path[1] if len(path) > 1 else p
        h = p.heading if p.heading is not None else _hd(p, nxt)
        return p.e, p.n, h
    for a, b in zip(path, path[1:], strict=False):
        if t <= b.t:
            f = (t - a.t) / (b.t - a.t) if b.t > a.t else 1.0
            h = a.heading if a.heading is not None else _hd(a, b)
            return a.e + (b.e - a.e) * f, a.n + (b.n - a.n) * f, h
    p = path[-1]
    return p.e, p.n, p.heading if p.heading is not None else _hd(path[-2], p)


def _hd(a: PathPt, b: PathPt) -> float:
    if (a.e, a.n) == (b.e, b.n):
        return 0.0
    return math.degrees(math.atan2(b.e - a.e, b.n - a.n)) % 360.0


class Mover:
    LOITER_PERIOD_S = 60.0

    def __init__(self, scenario: Scenario, seed: int | None = None) -> None:
        self.sc = scenario
        rng = random.Random(scenario.seed if seed is None else seed)
        self._phase = {e.id: rng.uniform(0, 2 * math.pi) for e in scenario.entities}

    def entity(self, eid: str, t: float) -> tuple[float, float, float]:
        ent = next(e for e in self.sc.entities if e.id == eid)
        e, n, h = interp_path(ent.path, t)
        if ent.loiter_radius_m:
            th = self._phase[eid] + 2 * math.pi * t / self.LOITER_PERIOD_S
            e += ent.loiter_radius_m * math.cos(th)
            n += ent.loiter_radius_m * math.sin(th)
            h = (math.degrees(-th)) % 360.0
        return e, n, h

    def entities(self, t: float) -> dict[str, tuple[float, float, float]]:
        return {ent.id: self.entity(ent.id, t) for ent in self.sc.entities}

    def operator(self, t: float) -> tuple[float, float, float]:
        return interp_path(self.sc.operator.path, t)

    def teammates(self, t: float) -> dict[str, tuple[float, float, float]]:
        return {p.callsign: interp_path(p.path, t) for p in self.sc.teammates}

    def sha256(self, dt: float = 1.0) -> str:
        h = hashlib.sha256()
        steps = int(self.sc.duration_s / dt) + 1
        for k in range(steps):
            t = k * dt
            row = {"t": t, "ent": self.entities(t), "op": self.operator(t),
                   "tm": self.teammates(t)}
            h.update(json.dumps(row, sort_keys=True, default=lambda x: round(x, 4)).encode())
        return h.hexdigest()
