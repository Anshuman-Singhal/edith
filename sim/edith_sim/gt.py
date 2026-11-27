"""Ground-truth helpers: analytic camera FOV and the ``gt_events.jsonl`` logger (sim spec §8).

Truth: only bench/, tests/, the scenario runner and gt_detector may import this (C59).
Camera model (stabilized gimbal, sim §4): yaw = body heading, pitch relative to the horizon,
body roll/pitch ignored; optical frame x-right, y-down, z-forward.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from edith_sim.scenario.model import Camera


def in_fov(cam_e: float, cam_n: float, cam_u: float, heading_deg: float, cam: Camera,
           e: float, n: float, u: float = 0.0) -> bool:
    de, dn, du = e - cam_e, n - cam_n, u - cam_u
    h, p = math.radians(heading_deg), math.radians(cam.pitch)
    fwd = (math.sin(h) * math.cos(p), math.cos(h) * math.cos(p), math.sin(p))
    right = (math.cos(h), -math.sin(h), 0.0)
    # down = right × fwd, negated to point down in the image
    up = (right[1] * fwd[2] - right[2] * fwd[1], right[2] * fwd[0] - right[0] * fwd[2],
          right[0] * fwd[1] - right[1] * fwd[0])
    z = de * fwd[0] + dn * fwd[1] + du * fwd[2]
    if z <= 0 or math.sqrt(de * de + dn * dn + du * du) > cam.max_range_m:
        return False
    x = de * right[0] + dn * right[1]
    y = -(de * up[0] + dn * up[1] + du * up[2])
    th = math.tan(math.radians(cam.hfov) / 2)
    tv = th * cam.h / cam.w
    return abs(x / z) <= th and abs(y / z) <= tv


class GtLogger:
    def __init__(self, path: Path | None = None) -> None:
        self.records: list[dict] = []
        self._fh = None
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            self._fh = Path(path).open("a", buffering=1)

    def log(self, kind: str, t: float, **kw) -> None:
        rec = {"kind": kind, "t_sim_ms": int(round(t * 1000)), **kw}
        self.records.append(rec)
        if self._fh:
            self._fh.write(json.dumps(rec, sort_keys=True) + "\n")

    def close(self) -> None:
        if self._fh:
            self._fh.close()


class FovTracker:
    """Turns per-tick in-FOV booleans into ``entity_in_fov{asset, entity, t_enter, t_exit,
    min_range}`` intervals; ``on_dwell`` fires once per interval when it reaches ``dwell_s``."""

    def __init__(self, logger: GtLogger | None = None) -> None:
        self.logger = logger
        self.open: dict[tuple[str, str], dict] = {}
        self.intervals: dict[tuple[str, str], list[tuple[float, float]]] = {}

    def update(self, t: float, asset: str, entity: str, seen: bool, rng: float) -> None:
        key = (asset, entity)
        cur = self.open.get(key)
        if seen and cur is None:
            self.open[key] = {"t_enter": t, "min_range": rng}
        elif seen:
            cur["min_range"] = min(cur["min_range"], rng)
        elif cur is not None:
            self._close(key, t)

    def _close(self, key, t: float) -> None:
        cur = self.open.pop(key)
        self.intervals.setdefault(key, []).append((cur["t_enter"], t))
        if self.logger:
            self.logger.log("entity_in_fov", t, asset=key[0], entity=key[1],
                            t_enter=cur["t_enter"], t_exit=t,
                            min_range=round(cur["min_range"], 1))

    def finish(self, t: float) -> None:
        for key in list(self.open):
            self._close(key, t)

    def first_dwell(self, asset: str, entity: str, min_dwell_s: float) -> float | None:
        """Time at which the first interval of ≥ min_dwell_s reached its dwell."""
        for a, b in self.intervals.get((asset, entity), []):
            if b - a >= min_dwell_s - 1e-9:
                return a + min_dwell_s
        return None
