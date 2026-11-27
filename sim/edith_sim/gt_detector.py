"""Ground-truth detector (WS-E; sim spec §4, C59, C84, C96).

Runs inside the sim, reads ``FrameTruth`` records in-process (plus the *true* camera pose for
clutter projection) and emits ``[Detection]`` (``placement=offload, model=gt``) on UDP 5800+i
— the same path as a P3 offload server — at the camera's virtual rate capped at 4 Hz. It
applies ``pd``, ``fa_per_h``, latency, bbox noise, scripted ``confusions`` (entity → class,
e.g. the planted deer → person) and persistent ``clutter`` (fixed ground points that keep
producing a false detection). Every emitted detection is logged to
``runs/<ts>/gt_dets_<i>.jsonl`` as ``{det_id, entity_id|null}`` for the alert→entity join
(sim spec §5.1). Animals are emitted as ``other`` unless a confusion says otherwise.

Config (scenario ``gt_detector`` block)::

    pd: 0.95  fa_per_h: 2  latency_ms: 150  bbox_noise_px: 2  rate_hz: 4
    min_px_h: 8                          # below this height at detector input → miss
    confusions: {deer-1: person}
    clutter: [{id: clutter-1, e: 120, n: 380, conf: 0.20, cls: person, h_m: 1.7}]
"""

from __future__ import annotations

import json
import math
import random
import socket
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from edith_common.geo import lla_to_enu
from edith_common.ports import port

RATE_CAP_HZ = 4.0
TILE_SCALE = 416 / 692      # detector input scale for det_px_h (C58)
CLASS_MAP = {"person": "person", "vehicle": "vehicle", "animal": "other", "other": "other"}


def _lla_to_enu(lat: float, lon: float, alt: float, origin) -> tuple[float, float, float]:
    return lla_to_enu(lat, lon, alt, origin)


def _cam_R(meta: dict) -> np.ndarray:
    """World(ENU) ← optical for a stabilized gimbal (sim spec §4; same convention as
    companion perception/geo.py, which D8 tests)."""
    pe, g = meta["pose_est"], meta.get("gimbal") or {}
    y = math.radians(float(pe["yaw_deg"]) + float(g.get("yaw_deg", 0.0)))
    p = math.radians(float(g.get("pitch_deg", -60.0)))
    f = np.array([math.cos(y) * math.cos(p), math.sin(y) * math.cos(p), -math.sin(p)])  # NED
    r = np.array([-math.sin(y), math.cos(y), 0.0])
    d = np.cross(f, r)
    M = np.array([[0.0, 1, 0], [1, 0, 0], [0, 0, -1]])
    return M @ np.column_stack([r, d, f])


def project_ground(meta: dict, origin, e: float, n: float, z: float = 0.0):
    pe = meta["pose_est"]
    ce, cn, _ = _lla_to_enu(pe["lat"], pe["lon"], pe.get("alt_msl_m", 0.0), origin)
    c = np.array([ce, cn, float(meta.get("rel_alt_m", pe.get("alt_agl_m", 0.0)))])
    pc = _cam_R(meta).T @ (np.array([e, n, z]) - c)
    if pc[2] <= 0:
        return None
    k = meta["K"]
    return k["fx"] * pc[0] / pc[2] + k["cx"], k["fy"] * pc[1] / pc[2] + k["cy"], float(np.linalg.norm(pc))


@dataclass
class GtConfig:
    pd: float = 0.95
    fa_per_h: float = 0.0
    latency_ms: float = 150.0
    bbox_noise_px: float = 2.0
    rate_hz: float = 4.0
    min_px_h: float = 8.0
    min_visible_frac: float = 0.5
    confusions: dict[str, str] = field(default_factory=dict)
    clutter: list[dict] = field(default_factory=list)
    conf_range: tuple[float, float] = (0.55, 0.95)
    fa_conf_range: tuple[float, float] = (0.25, 0.45)

    @classmethod
    def from_scenario(cls, d: dict | None) -> GtConfig:
        d = dict(d or {})
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)


class GtDetector:
    def __init__(self, cfg: GtConfig, asset_id: str, instance: int = 0, seed: int = 0,
                 origin=None, log_path: str | Path | None = None,
                 send_host: str | None = None):
        self.cfg, self.asset_id, self.instance, self.origin = cfg, asset_id, instance, origin
        self.rng = random.Random(f"{seed}:{asset_id}:gt")
        self._last_emit_ms: float | None = None
        self._queue: list[tuple[float, bytes]] = []
        self._log = open(log_path, "a") if log_path else None
        self._sock = None
        self._dest = None
        if send_host:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._dest = (send_host, port("detections", instance))
        self.n_det = 0

    def close(self) -> None:
        if self._log:
            self._log.close()
        if self._sock:
            self._sock.close()

    # ------------------------------------------------------------------ core
    def _rate_ok(self, t_ms: float) -> bool:
        period = 1000.0 / min(self.cfg.rate_hz, RATE_CAP_HZ)
        if self._last_emit_ms is not None and t_ms - self._last_emit_ms < period - 1.0:
            return False
        self._last_emit_ms = t_ms
        return True

    def _noisy(self, bbox, w: int, h: int) -> list[float]:
        s = self.cfg.bbox_noise_px
        x, y, bw, bh = bbox
        g = self.rng.gauss
        x2, y2 = x * w + g(0, s), y * h + g(0, s)
        bw2, bh2 = max(1.0, bw * w + g(0, s)), max(1.0, bh * h + g(0, s))
        return [x2 / w, y2 / h, bw2 / w, bh2 / h]

    def detect(self, truth: dict, true_meta: dict | None = None) -> list[dict] | None:
        """One FrameTruth record → detections (None if skipped by the rate cap)."""
        t = float(truth.get("t_sim_ms", 0))
        if not self._rate_ok(t):
            return None
        w = int((true_meta or {}).get("w", 1280))
        h = int((true_meta or {}).get("h", 720))
        fid = truth["frame_id"]
        out: list[tuple[dict, str | None]] = []
        lo, hi = self.cfg.conf_range
        for ob in truth.get("objects", []):
            if ob.get("visible_frac", 1.0) < self.cfg.min_visible_frac:
                continue
            px_h = ob["bbox_norm"][3] * h * TILE_SCALE
            if px_h < self.cfg.min_px_h or self.rng.random() > self.cfg.pd:
                continue
            ent = ob.get("entity_id")
            cls = self.cfg.confusions.get(ent, CLASS_MAP.get(ob.get("cls"), "other"))
            out.append((self._det(fid, t, cls, self.rng.uniform(lo, hi),
                                  self._noisy(ob["bbox_norm"], w, h), px_h, true_meta), ent))
        if true_meta is not None and self.origin is not None:
            for c in self.cfg.clutter:
                d = self._clutter(c, fid, t, true_meta, w, h)
                if d is not None:
                    out.append((d, None))
        if self.cfg.fa_per_h > 0:
            dt_s = 1.0 / min(self.cfg.rate_hz, RATE_CAP_HZ)
            lam = self.cfg.fa_per_h / 3600.0 * dt_s
            if self.rng.random() < lam:
                bw, bh = self.rng.uniform(0.01, 0.04), self.rng.uniform(0.02, 0.08)
                bb = [self.rng.uniform(0, 1 - bw), self.rng.uniform(0, 1 - bh), bw, bh]
                flo, fhi = self.cfg.fa_conf_range
                out.append((self._det(fid, t, self.rng.choice(["person", "vehicle"]),
                                      self.rng.uniform(flo, fhi), bb, bh * h * TILE_SCALE,
                                      true_meta), None))
        dets = []
        for k, (d, ent) in enumerate(out):
            d["det_id"] = f"gt-{self.asset_id}-{fid}-{k}"
            dets.append(d)
            if self._log:
                self._log.write(json.dumps({"det_id": d["det_id"], "entity_id": ent}) + "\n")
        if self._log:
            self._log.flush()
        self.n_det += len(dets)
        return dets

    def _clutter(self, c: dict, fid, t, meta: dict, w: int, h: int) -> dict | None:
        e, n = (c["at"] if "at" in c else (c["e"], c["n"]))
        hm = float(c.get("h_m", 1.7 if c.get("cls", "person") == "person" else 1.5))
        foot = project_ground(meta, self.origin, e, n, 0.0)
        top = project_ground(meta, self.origin, e, n, hm)
        if foot is None or top is None:
            return None
        u, v, _ = foot
        bh = max(1.0, v - top[1])
        bw = bh * (0.4 if c.get("cls", "person") == "person" else 2.0)
        if not (0 <= u < w and 0 <= v < h) or bh * TILE_SCALE < self.cfg.min_px_h:
            return None
        bb = self._noisy([(u - bw / 2) / w, (v - bh) / h, bw / w, bh / h], w, h)
        return self._det(fid, t, c.get("cls", "person"), float(c.get("conf", 0.2)), bb,
                         bh * TILE_SCALE, meta)

    def _det(self, fid, t, cls, conf, bbox, px_h, meta) -> dict:
        tc = (meta or {}).get("t_capture_ms", t)
        return {
            "det_id": "", "frame_id": fid, "frame_ts_ms": tc,
            "source": {"asset_id": self.asset_id, "sensor_id": "eo0"},
            "cls": cls, "conf": round(conf, 4), "bbox_norm": [round(x, 6) for x in bbox],
            "tile": None, "det_px_h": round(px_h, 2),
            "infer": {"placement": "offload", "model": "gt", "model_sha": "gt",
                      "t_capture_ms": tc, "t_start_ms": tc, "t_end_ms": tc + self.cfg.latency_ms},
        }

    # ------------------------------------------------------------------ transport
    def on_frame(self, truth: dict, true_meta: dict | None, now_ms: float) -> None:
        dets = self.detect(truth, true_meta)
        if dets is None:
            return
        self._queue.append((now_ms + self.cfg.latency_ms, json.dumps(dets).encode()))
        self.pump(now_ms)

    def pump(self, now_ms: float) -> int:
        """Send every queued datagram whose latency has elapsed."""
        due = [q for q in self._queue if q[0] <= now_ms]
        self._queue = [q for q in self._queue if q[0] > now_ms]
        if self._sock is not None:
            for _, payload in due:
                self._sock.sendto(payload, self._dest)
        return len(due)
