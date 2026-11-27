"""Tracking metrics shared by the D8 tests and the D9 bench."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping

Pos = tuple[float, float]


def idf1(frames: Iterable[tuple[Mapping[str, Pos], Mapping[int, Pos]]], thr: float) -> float:
    """IDF1 = 2·IDTP / (2·IDTP + IDFP + IDFN) with a one-to-one GT↔hypothesis identity map.

    ``frames`` yields ``(gt {id: (x, y)}, hyp {id: (x, y)})`` per frame; a pair matches in a
    frame if within ``thr``. The identity map is chosen greedily by co-occurrence count, which
    can only under-estimate IDTP (conservative)."""
    co: dict[tuple[str, int], int] = defaultdict(int)
    n_gt = n_hyp = 0
    for gt, hyp in frames:
        n_gt += len(gt)
        n_hyp += len(hyp)
        for g, gp in gt.items():
            for h, hp in hyp.items():
                if math.dist(gp, hp) <= thr:
                    co[(g, h)] += 1
    used_g: set[str] = set()
    used_h: set[int] = set()
    idtp = 0
    for (g, h), c in sorted(co.items(), key=lambda kv: -kv[1]):
        if g in used_g or h in used_h:
            continue
        used_g.add(g)
        used_h.add(h)
        idtp += c
    denom = n_gt + n_hyp
    return 2.0 * idtp / denom if denom else 1.0


def duplicate_rate(track_entities: Mapping[int, str | None]) -> float:
    """Confirmed tracks per GT entity that has ≥1 track (tracks mapped to None are ignored)."""
    ents = [e for e in track_entities.values() if e is not None]
    return len(ents) / len(set(ents)) if ents else 0.0
