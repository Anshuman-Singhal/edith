"""Friendly association (PLAN §3.5, L17, C52, C98; r4 nits defense#1 and ml nb1).

Each friendly PLI (teammates and self) is dead-reckoned to the detection time with
``course_deg``/``speed_mps``. A ``person`` track within

    radius = max(15 m, ce_m) + min(0.5 m/s · age_s, 15 m)

of the dead-reckoned position gets ``assoc_friend_uid``: no alert, no CoT, drawn as the
friend; affiliation stays ``unknown`` (I6). Association is sticky: released only after 3
consecutive updates beyond 2× the radius, or on track loss.

Ages (pinned here, D8; logged in docs/walkthroughs/e.md):
- ``age_true = t_det − pli.ts_ms``. Dead-reckoning and the radius growth both use
  ``min(age_true, 30 s)`` — the true PLI age, so the gate keeps growing with the
  dead-reckoning error during a TAK outage (ml nb1; the more conservative option under L26).
- Freshness (<30 s) applies only to the *first* association. While ``status.tak = lost`` the
  freshness age is measured from the moment the link was lost:
  ``age_fresh = t_det − max(pli.ts_ms, t_link_lost)`` (C98, defense nit 1).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

AGE_CAP_S = 30.0
FRESH_S = 30.0
BASE_RADIUS_M = 15.0
GROWTH_MPS = 0.5
GROWTH_CAP_M = 15.0
RELEASE_UPDATES = 3


@dataclass
class Pli:
    uid: str
    e: float
    n: float
    course_deg: float
    speed_mps: float
    ts_ms: int
    is_self: bool = False


@dataclass
class _Assoc:
    uid: str
    outside: int = 0


class FriendlyAssociator:
    def __init__(self) -> None:
        self.pli: dict[str, Pli] = {}
        self.tak_state = "ok"
        self.t_link_lost: int | None = None
        self._assoc: dict[int, _Assoc] = {}

    # -------------------------------------------------------------- inputs
    def on_pli(self, p: Pli) -> None:
        old = self.pli.get(p.uid)
        if old is None or p.ts_ms >= old.ts_ms:
            self.pli[p.uid] = p

    def on_tak_status(self, state: str, t_ms: int) -> None:
        if state == "lost" and self.tak_state != "lost":
            self.t_link_lost = t_ms
        if state != "lost":
            self.t_link_lost = None
        self.tak_state = state

    # -------------------------------------------------------------- geometry
    @staticmethod
    def age_true_s(p: Pli, t_ms: int) -> float:
        return max(0.0, (t_ms - p.ts_ms) / 1000.0)

    def age_fresh_s(self, p: Pli, t_ms: int) -> float:
        ref = p.ts_ms
        if self.tak_state == "lost" and self.t_link_lost is not None:
            ref = max(ref, self.t_link_lost)
        return max(0.0, (t_ms - ref) / 1000.0)

    @staticmethod
    def dead_reckon(p: Pli, t_ms: int) -> tuple[float, float]:
        a = min(FriendlyAssociator.age_true_s(p, t_ms), AGE_CAP_S)
        c = math.radians(p.course_deg)
        return p.e + p.speed_mps * a * math.sin(c), p.n + p.speed_mps * a * math.cos(c)

    @staticmethod
    def radius_m(p: Pli, t_ms: int, ce_m: float) -> float:
        a = min(FriendlyAssociator.age_true_s(p, t_ms), AGE_CAP_S)
        return max(BASE_RADIUS_M, ce_m) + min(GROWTH_MPS * a, GROWTH_CAP_M)

    def _dist(self, p: Pli, e: float, n: float, t_ms: int) -> float:
        de, dn = self.dead_reckon(p, t_ms)
        return math.hypot(e - de, n - dn)

    # -------------------------------------------------------------- evaluation
    def evaluate(self, track_id: int, cls: str, e: float, n: float, ce_m: float,
                 t_ms: int) -> str | None:
        """Call on every update of a metric track (before any alert). Returns the uid or None."""
        if cls != "person":
            return None
        cur = self._assoc.get(track_id)
        if cur is not None:
            p = self.pli.get(cur.uid)
            if p is not None:
                if self._dist(p, e, n, t_ms) > 2.0 * self.radius_m(p, t_ms, ce_m):
                    cur.outside += 1
                else:
                    cur.outside = 0
                if cur.outside < RELEASE_UPDATES:
                    return cur.uid
            del self._assoc[track_id]
        best: tuple[float, str] | None = None
        for p in self.pli.values():
            if self.age_fresh_s(p, t_ms) >= FRESH_S:
                continue
            d = self._dist(p, e, n, t_ms)
            if d <= self.radius_m(p, t_ms, ce_m) and (best is None or d < best[0]):
                best = (d, p.uid)
        if best is None:
            return None
        self._assoc[track_id] = _Assoc(best[1])
        return best[1]

    def on_track_lost(self, track_id: int) -> None:
        self._assoc.pop(track_id, None)

    def current(self, track_id: int) -> str | None:
        a = self._assoc.get(track_id)
        return a.uid if a else None
