"""Constant-velocity Kalman tracker (PLAN §3.5 Tracker, L19, C56, C95).

One ``Tracker`` per feed. The same core runs in two spaces:
- **ground** (``geo_quality: metric``): z = ENU metres from ``geo.locate``; R = the geo
  covariance (σ from ce_m); predictions are tested against the current camera footprint.
- **image** (``geo_quality: pseudo``, replay): z = box bottom-centre in 1280×720 pixels;
  R = (0.1·box diagonal + 4 px)²·I; before each predict, track states are warped by the
  inter-tick homography (``motion.MotionEstimator``).

Association: same class, Mahalanobis d² < 9.21 (χ²₂ 99%), greedy by d². First pass with
conf ≥ 0.25 detections (which may also start tracks); ByteTrack-style second pass of
0.10 ≤ conf < 0.25 detections against the still-unmatched tracks (never starts tracks).
Confirmation: ≥3 hits in the last 5 in-view updates with mean hit conf ≥ τ_c
(person 0.30, vehicle 0.35).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

GATE_D2 = 9.21
CONF_FLOOR = 0.10
TRACK_START = 0.25
TAU_C = {"person": 0.30, "vehicle": 0.35, "other": 0.35}
WINDOW = 5
CONFIRM_HITS = 3


@dataclass
class Meas:
    det_id: str
    cls: str
    conf: float
    z: np.ndarray            # 2-vector (ENU m or px)
    R: np.ndarray            # 2×2
    t_ms: int
    bbox_norm: tuple[float, float, float, float] | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class TrackerParams:
    space: str = "ground"                       # ground | image
    accel_sigma: dict = field(default_factory=lambda: {"person": 1.0, "vehicle": 3.0,
                                                       "other": 2.0})
    vel0_sigma: dict = field(default_factory=lambda: {"person": 3.0, "vehicle": 12.0,
                                                      "other": 5.0})
    max_misses_tentative: int = 2               # consecutive in-view misses
    max_misses_confirmed: int = 6
    max_coast_s: float = 20.0                   # since last hit (also covers out-of-view)
    max_gate: float = 40.0                      # absolute innovation cap (m or px)
    low_pass_max_age_ms: int = 1500             # 2nd pass only for recently-hit tracks

    @classmethod
    def image(cls) -> TrackerParams:
        return cls(space="image", accel_sigma={"person": 60.0, "vehicle": 150.0, "other": 80.0},
                   vel0_sigma={"person": 40.0, "vehicle": 150.0, "other": 60.0},
                   max_coast_s=6.0, max_gate=250.0)


class KTrack:
    _next = 1

    def __init__(self, m: Meas, p: TrackerParams):
        self.id = KTrack._next
        KTrack._next += 1
        self.cls = m.cls
        self.p = p
        self.x = np.array([m.z[0], m.z[1], 0.0, 0.0])
        v0 = p.vel0_sigma.get(m.cls, 5.0)
        self.P = np.diag([m.R[0, 0], m.R[1, 1], v0 * v0, v0 * v0])
        self.P[:2, :2] = m.R
        self.t_ms = m.t_ms
        self.first_ms = self.last_ms = m.t_ms
        self.history: list[tuple[bool, float]] = [(True, m.conf)]
        self.misses = 0
        self.confirmed = False
        self.confirmed_ms: int | None = None
        self.lost = False
        self.det_ids: list[str] = [m.det_id]
        self.last_meas = m
        self.hits_total = 1
        self._check_confirm(m.t_ms)

    # ------------------------------------------------------------------ kalman
    def predict(self, t_ms: int) -> None:
        dt = (t_ms - self.t_ms) / 1000.0
        if dt <= 0:
            return
        F = np.eye(4)
        F[0, 2] = F[1, 3] = dt
        q = self.p.accel_sigma.get(self.cls, 2.0) ** 2
        Q1 = q * np.array([[dt ** 3 / 3, dt ** 2 / 2], [dt ** 2 / 2, dt]])
        Q = np.zeros((4, 4))
        Q[np.ix_([0, 2], [0, 2])] = Q1
        Q[np.ix_([1, 3], [1, 3])] = Q1
        self.x = F @ self.x
        self.P = F @ self.P @ F.T + Q
        self.t_ms = t_ms

    def predicted(self, t_ms: int) -> tuple[np.ndarray, np.ndarray]:
        """(x, P) predicted to t_ms without mutating the track."""
        dt = max(0.0, (t_ms - self.t_ms) / 1000.0)
        F = np.eye(4)
        F[0, 2] = F[1, 3] = dt
        q = self.p.accel_sigma.get(self.cls, 2.0) ** 2
        Q1 = q * np.array([[dt ** 3 / 3, dt ** 2 / 2], [dt ** 2 / 2, dt]])
        Q = np.zeros((4, 4))
        Q[np.ix_([0, 2], [0, 2])] = Q1
        Q[np.ix_([1, 3], [1, 3])] = Q1
        return F @ self.x, F @ self.P @ F.T + Q

    def d2(self, m: Meas) -> float:
        S = self.P[:2, :2] + m.R
        r = m.z - self.x[:2]
        return float(r @ np.linalg.solve(S, r))

    def update(self, m: Meas) -> None:
        H = np.zeros((2, 4))
        H[0, 0] = H[1, 1] = 1.0
        S = H @ self.P @ H.T + m.R
        Kg = self.P @ H.T @ np.linalg.inv(S)
        self.x = self.x + Kg @ (m.z - H @ self.x)
        self.P = (np.eye(4) - Kg @ H) @ self.P
        self.P = 0.5 * (self.P + self.P.T)
        self._record(True, m.conf, m.t_ms)
        self.last_ms = m.t_ms
        self.misses = 0
        self.hits_total += 1
        self.det_ids = (self.det_ids + [m.det_id])[-32:]
        self.last_meas = m

    def warp(self, Hm: np.ndarray) -> None:
        """Apply an image homography (prev → cur) to the position, velocity and covariance."""
        x, y = self.x[0], self.x[1]
        p = Hm @ np.array([x, y, 1.0])
        nx, ny = p[0] / p[2], p[1] / p[2]
        # Jacobian of the projective map at (x, y)
        w = p[2]
        J = np.array([[Hm[0, 0] - nx * Hm[2, 0], Hm[0, 1] - nx * Hm[2, 1]],
                      [Hm[1, 0] - ny * Hm[2, 0], Hm[1, 1] - ny * Hm[2, 1]]]) / w
        T = np.eye(4)
        T[:2, :2] = J
        T[2:, 2:] = J
        self.x = np.array([nx, ny, *(J @ self.x[2:])])
        self.P = T @ self.P @ T.T

    # ---------------------------------------------------------------- bookkeeping
    def _record(self, hit: bool, conf: float, t_ms: int) -> None:
        self.history = (self.history + [(hit, conf)])[-WINDOW:]
        self._check_confirm(t_ms)

    def miss(self, t_ms: int) -> None:
        self.misses += 1
        self._record(False, 0.0, t_ms)

    def _check_confirm(self, t_ms: int) -> None:
        if self.confirmed:
            return
        hits = [c for h, c in self.history if h]
        if len(hits) >= CONFIRM_HITS and sum(hits) / len(hits) >= TAU_C.get(self.cls, 0.35):
            self.confirmed = True
            self.confirmed_ms = t_ms

    @property
    def hits(self) -> int:
        return sum(1 for h, _ in self.history if h)

    @property
    def conf(self) -> float:
        hits = [c for h, c in self.history if h]
        return sum(hits) / len(hits) if hits else 0.0

    @property
    def pos(self) -> np.ndarray:
        return self.x[:2]


class Tracker:
    """Per-feed tracker. ``step`` once per processed frame (even when it has no detections)."""

    def __init__(self, params: TrackerParams | None = None):
        self.p = params or TrackerParams()
        self.tracks: list[KTrack] = []
        self.lost: list[KTrack] = []

    def reset(self) -> None:
        """Splice boundary (pseudo feeds): drop every track."""
        for t in self.tracks:
            t.lost = True
        self.lost.extend(self.tracks)
        self.tracks = []

    def step(self, t_ms: int, meas: list[Meas],
             visible: Callable[[np.ndarray], bool] | None = None,
             warp: np.ndarray | None = None) -> list[KTrack]:
        """Predict, associate, update; ``visible(pos)`` says whether a predicted position is
        inside the current footprint (misses count only then); ``warp`` = image homography."""
        if warp is not None:
            for t in self.tracks:
                t.warp(warp)
        for t in self.tracks:
            t.predict(t_ms)
        meas = [m for m in meas if m.conf >= CONF_FLOOR]
        hi = sorted((m for m in meas if m.conf >= TRACK_START), key=lambda m: -m.conf)
        lo = [m for m in meas if m.conf < TRACK_START]
        unmatched_t = list(self.tracks)
        matched: set[int] = set()

        def assign(ms: list[Meas], low: bool = False) -> list[Meas]:
            pairs = []
            for i, m in enumerate(ms):
                for t in unmatched_t:
                    if t.cls != m.cls:
                        continue
                    if low and t_ms - t.last_ms > self.p.low_pass_max_age_ms:
                        continue
                    if float(np.hypot(*(m.z - t.x[:2]))) > self.p.max_gate:
                        continue
                    d2 = t.d2(m)
                    if d2 < GATE_D2:
                        pairs.append((d2, i, t))
            pairs.sort(key=lambda x: x[0])
            used_m: set[int] = set()
            for _d2, i, t in pairs:
                if i in used_m or t.id in matched:
                    continue
                t.update(ms[i])
                used_m.add(i)
                matched.add(t.id)
            unmatched_t[:] = [t for t in unmatched_t if t.id not in matched]
            return [m for i, m in enumerate(ms) if i not in used_m]

        left_hi = assign(hi)
        assign(lo, low=True)
        for t in unmatched_t:
            if visible is None or visible(t.pos):
                t.miss(t_ms)
        for m in left_hi:
            self.tracks.append(KTrack(m, self.p))
        keep = []
        for t in self.tracks:
            limit = self.p.max_misses_confirmed if t.confirmed else self.p.max_misses_tentative
            if t.misses > limit or (t_ms - t.last_ms) / 1000.0 > self.p.max_coast_s:
                t.lost = True
                self.lost.append(t)
            else:
                keep.append(t)
        self.tracks = keep
        return self.tracks


def pixel_sigma(bbox_w_px: float, bbox_h_px: float) -> float:
    """Image-plane measurement σ (C95): 0.1·box diagonal + 4 px."""
    return 0.1 * math.hypot(bbox_w_px, bbox_h_px) + 4.0
