"""Cross-drone fusion (PLAN §3.5 Fusion): same class, Mahalanobis on the combined σ,
|Δt| < 5 s, inverse-variance merge. Per-feed tracks are never merged with another track of
the same feed (the feed tracker already decided they differ)."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .geo import ce90_from_cov
from .tracker import GATE_D2, KTrack

MAX_DT_MS = 5000
MAX_GATE_M = 25.0     # absolute cap on fusion distance (coasting tracks have large P)


@dataclass
class FusedTrack:
    track_id: int
    cls: str
    members: dict[str, KTrack] = field(default_factory=dict)   # asset_id → local track
    x: np.ndarray = field(default_factory=lambda: np.zeros(4))
    P: np.ndarray = field(default_factory=lambda: np.eye(4))
    first_seen_ms: int = 0
    last_seen_ms: int = 0
    confirmed_ms: int | None = None
    lost: bool = False
    source_assets: list[str] = field(default_factory=list)
    det_ids: list[str] = field(default_factory=list)
    conf: float = 0.0
    hits: int = 0
    last_meas: object | None = None

    @property
    def confirmed(self) -> bool:
        return self.confirmed_ms is not None

    @property
    def ce_m(self) -> float:
        return ce90_from_cov(self.P[:2, :2])


class Fusion:
    def __init__(self) -> None:
        self.tracks: dict[int, FusedTrack] = {}
        self._map: dict[tuple[str, int], int] = {}
        self._next = 1

    def _candidates(self, asset: str, lt: KTrack, t_ms: int):
        x, P = lt.predicted(t_ms)
        for ft in self.tracks.values():
            if ft.lost or ft.cls != lt.cls or asset in ft.members or not ft.members:
                continue
            if abs(lt.last_ms - ft.last_seen_ms) >= MAX_DT_MS:
                continue
            r = x[:2] - ft.x[:2]
            if float(np.hypot(*r)) > MAX_GATE_M:
                continue
            d2 = float(r @ np.linalg.solve(P[:2, :2] + ft.P[:2, :2], r))
            if d2 < GATE_D2:
                yield d2, ft

    def update(self, asset: str, local_tracks: list[KTrack], lost: list[KTrack],
               t_ms: int) -> None:
        for lt in lost:
            fid = self._map.pop((asset, lt.id), None)
            if fid is not None and fid in self.tracks:
                self.tracks[fid].members.pop(asset, None)
        for lt in local_tracks:
            key = (asset, lt.id)
            if key in self._map:
                continue
            best = min(self._candidates(asset, lt, t_ms), default=None, key=lambda c: c[0])
            if best is not None:
                ft = best[1]
            else:
                ft = FusedTrack(self._next, lt.cls, first_seen_ms=lt.first_ms)
                self._next += 1
                self.tracks[ft.track_id] = ft
            ft.members[asset] = lt
            self._map[key] = ft.track_id
        self._merge_pass(t_ms)
        for ft in self.tracks.values():
            if ft.lost:
                continue
            if not ft.members:
                ft.lost = True
                continue
            self._refresh(ft, t_ms)

    def _refresh(self, ft: FusedTrack, t_ms: int) -> None:
        info = np.zeros((2, 2))
        iv = np.zeros(2)
        best_v = None
        newest_ms = max(m.last_ms for m in ft.members.values())
        fresh = [m for m in ft.members.values() if newest_ms - m.last_ms < MAX_DT_MS]
        for lt in fresh:
            x, P = lt.predicted(t_ms)
            Pi = np.linalg.inv(P[:2, :2])
            info += Pi
            iv += Pi @ x[:2]
            tr = np.trace(P[2:, 2:])
            if best_v is None or tr < best_v[0]:
                best_v = (tr, x[2:], P[2:, 2:])
        Pp = np.linalg.inv(info)
        ft.x = np.array([*(Pp @ iv), *best_v[1]])
        ft.P = np.zeros((4, 4))
        ft.P[:2, :2] = Pp
        ft.P[2:, 2:] = best_v[2]
        mem = list(ft.members.values())
        ft.last_seen_ms = max(ft.last_seen_ms, *(m.last_ms for m in mem))
        ft.first_seen_ms = min(ft.first_seen_ms, *(m.first_ms for m in mem))
        for a in ft.members:
            if a not in ft.source_assets:
                ft.source_assets.append(a)
        if ft.confirmed_ms is None and any(m.confirmed for m in mem):
            ft.confirmed_ms = t_ms
        newest = max(mem, key=lambda m: m.last_ms)
        ft.conf = max(m.conf for m in mem)
        ft.hits = max(m.hits for m in mem)
        ft.last_meas = newest.last_meas
        ids = []
        for m in mem:
            ids.extend(m.det_ids)
        seen = set(ft.det_ids)
        ft.det_ids = (ft.det_ids + [i for i in ids if i not in seen])[-32:]

    def _merge_pass(self, t_ms: int) -> None:
        live = [f for f in self.tracks.values() if not f.lost and f.members]
        for i, a in enumerate(live):
            for b in live[i + 1:]:
                if a.lost or b.lost or a.cls != b.cls or set(a.members) & set(b.members):
                    continue
                self._refresh(a, t_ms)
                self._refresh(b, t_ms)
                if abs(a.last_seen_ms - b.last_seen_ms) >= MAX_DT_MS:
                    continue
                r = a.x[:2] - b.x[:2]
                if float(np.hypot(*r)) > MAX_GATE_M:
                    continue
                if float(r @ np.linalg.solve(a.P[:2, :2] + b.P[:2, :2], r)) >= GATE_D2:
                    continue
                keep, drop = (a, b) if a.track_id < b.track_id else (b, a)
                for asset, lt in drop.members.items():
                    keep.members[asset] = lt
                    self._map[(asset, lt.id)] = keep.track_id
                drop.members = {}
                drop.lost = True
                if drop.confirmed_ms is not None and (keep.confirmed_ms is None
                                                      or drop.confirmed_ms < keep.confirmed_ms):
                    keep.confirmed_ms = drop.confirmed_ms

    def live(self) -> list[FusedTrack]:
        return [f for f in self.tracks.values() if not f.lost]
