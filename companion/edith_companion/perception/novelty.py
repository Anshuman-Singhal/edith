"""Novelty (PLAN §3.5): a confirmed track is novel if no *other* same-class track was seen
within max(15 m, ce_m) in the last 120 s. Pseudo tracks skip metre-based novelty (ml nb3)
and are reported novel (1.0)."""

from __future__ import annotations

import math
from collections import deque

WINDOW_MS = 120_000
MIN_RADIUS_M = 15.0


class Novelty:
    def __init__(self) -> None:
        self._seen: deque[tuple[int, int, str, float, float]] = deque()  # t, id, cls, e, n

    def observe(self, track_id: int, cls: str, e: float, n: float, t_ms: int) -> None:
        self._seen.append((t_ms, track_id, cls, e, n))
        while self._seen and t_ms - self._seen[0][0] > WINDOW_MS:
            self._seen.popleft()

    def score(self, track_id: int, cls: str, e: float, n: float, ce_m: float, t_ms: int) -> float:
        r = max(MIN_RADIUS_M, ce_m)
        for t, tid, c, se, sn in self._seen:
            if tid != track_id and c == cls and t_ms - t <= WINDOW_MS \
                    and math.hypot(e - se, n - sn) <= r:
                return 0.0
        return 1.0
