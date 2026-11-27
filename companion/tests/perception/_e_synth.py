"""Synthetic camera + truth for the D8 tests (no data/, no simd). Test-only: may use truth."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import numpy as np
from edith_common.geo import Origin
from edith_companion.perception.geo import (
    CamPose,
    Intrinsics,
    enu_to_latlon,
    ground_to_pixel,
    pixel_to_ground,
)

ORIGIN = Origin(40.0700, -88.6300, 210.0, -33.0)
K720 = Intrinsics.from_hfov(1280, 720, 70.0)
NAV = {"rp": 1.0, "yaw": 3.0, "alt": 1.5}


@dataclass
class Target:
    id: str
    cls: str
    e: float
    n: float
    ve: float = 0.0
    vn: float = 0.0
    h_m: float = 1.7

    def at(self, t_s: float) -> tuple[float, float]:
        return self.e + self.ve * t_s, self.n + self.vn * t_s


def meta_for(asset: str, fid: int, t_ms: int, e: float, n: float, h: float, yaw: float,
             pitch: float, K: Intrinsics = K720, rng: random.Random | None = None,
             nav: dict | None = None, body_roll: float = 0.0):
    """Returns (true CamPose, FrameMeta dict with pose_est = true + nav noise)."""
    nav = NAV if nav is None else nav
    g = rng.gauss if rng else (lambda mu, s: 0.0)
    true_roll = g(0, nav["rp"])          # stabilized horizon-reference error (C96)
    true_pose = CamPose.stabilized(e, n, h, yaw, pitch, true_roll)
    lat, lon = enu_to_latlon(e, n, ORIGIN)
    meta = {
        "frame_id": fid, "t_capture_ms": t_ms, "t_sim_ms": t_ms, "asset_id": asset,
        "pose_est": {"lat": lat, "lon": lon, "alt_msl_m": ORIGIN.alt_msl_m + h, "alt_agl_m": h,
                     "roll_deg": body_roll + g(0, nav["rp"]), "pitch_deg": g(0, nav["rp"]),
                     "yaw_deg": (yaw + g(0, nav["yaw"])) % 360},
        "rel_alt_m": h + g(0, nav["alt"]),
        "gimbal": {"mode": "stabilized", "pitch_deg": pitch + g(0, nav["rp"]), "yaw_deg": 0.0},
        "K": {"fx": K.fx, "fy": K.fy, "cx": K.cx, "cy": K.cy}, "w": K.w, "h": K.h,
        "pose_source": "sidecar", "video": "off",
    }
    return true_pose, meta


def box_for(pose: CamPose, K: Intrinsics, e: float, n: float, h_m: float, cls: str):
    foot = ground_to_pixel(pose, K, e, n, 0.0)
    head = ground_to_pixel(pose, K, e, n, h_m)
    if foot is None or head is None:
        return None
    u, v = foot
    if not (0 <= u < K.w and 0 <= v < K.h) or pixel_to_ground(pose, K, u, v) is None:
        return None
    bh = max(2.0, v - head[1])
    bw = bh * (0.4 if cls == "person" else 2.2)
    return u, v, bw, bh


def detections(asset: str, fid: int, t_ms: int, pose: CamPose, targets: list[Target],
               t_s: float, rng: random.Random, pd: float = 0.95, px_sigma: float = 2.0,
               K: Intrinsics = K720, conf=(0.5, 0.9)):
    """Detections for every in-view target. Returns (dets, {entity: (e, n)} in view)."""
    dets, inview = [], {}
    for tg in targets:
        e, n = tg.at(t_s)
        b = box_for(pose, K, e, n, tg.h_m, tg.cls)
        if b is None:
            continue
        inview[tg.id] = (e, n)
        if rng.random() > pd:
            continue
        u, v, bw, bh = b
        u += rng.gauss(0, px_sigma)
        v += rng.gauss(0, px_sigma)
        dets.append({"det_id": f"{asset}-{fid}-{tg.id}", "frame_id": fid, "frame_ts_ms": t_ms,
                     "source": {"asset_id": asset, "sensor_id": "eo0"}, "cls": tg.cls,
                     "conf": rng.uniform(*conf),
                     "bbox_norm": [(u - bw / 2) / K.w, (v - bh) / K.h, bw / K.w, bh / K.h]})
    return dets, inview


def lawnmower(t_s: float, speed: float = 8.0, leg: float = 240.0, spacing: float = 68.0,
              e0: float = 0.0, n0: float = 0.0) -> tuple[float, float, float]:
    """(e, n, yaw) along a north/south lawnmower starting at (e0, n0) heading north."""
    d = speed * t_s
    period = leg + spacing
    k, r = divmod(d, period)
    k = int(k)
    if r < leg:
        n = n0 + (r if k % 2 == 0 else leg - r)
        return e0 + k * spacing, n, 0.0 if k % 2 == 0 else 180.0
    return e0 + k * spacing + (r - leg), n0 + (leg if k % 2 == 0 else 0.0), 90.0


def entity_of(det_id: str) -> str:
    return det_id.rsplit("-", 1)[-1]


def majority_entity(det_ids: list[str]) -> str | None:
    if not det_ids:
        return None
    ents = [entity_of(d) for d in det_ids]
    return max(set(ents), key=ents.count)


def dist(a, b) -> float:
    return math.dist(a, b)


def np_rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)
