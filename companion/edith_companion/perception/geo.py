"""Pixel → ground geolocation with CE90 (PLAN §3.5 Geolocation, C57, C96; sim spec §4).

Conventions (shared with simd, sim spec §4):
- World frame: ENU metres from the scenario origin; the ground is the home-elevation plane
  z = 0 and the camera sits at z = h = ``rel_alt_m``.
- Optical frame: x right, y down, z forward. Pixel (u, v) → ray (u−cx)/fx, (v−cy)/fy, 1.
- ``gimbal.mode = stabilized`` (default): camera pitch is relative to the horizon, camera yaw is
  body yaw + gimbal yaw, body roll/pitch are ignored. ``body_fixed``: the gimbal angles are
  relative to the body and the body attitude (yaw, pitch, roll) applies.
- Rays less than 5° below the horizon are rejected.

CE90: the ground point's 2×2 covariance is propagated from the pose/pixel error budget
(camera pitch and roll σ_rp, yaw σ_yaw, height σ_alt, pixel σ_px incl. the box term) with a
numerical Jacobian, and CE90 is the exact 90% radius of that (generally elliptical) Gaussian.
For a circular error this reduces to PLAN's 2.146·√((σ_r²+σ_x²)/2).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from edith_common.geo import Origin, enu_to_lla, lla_to_enu

MIN_DEPRESSION_DEG = 5.0
_M_NED_TO_ENU = np.array([[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, -1.0]])


@dataclass(frozen=True)
class Intrinsics:
    fx: float
    fy: float
    cx: float
    cy: float
    w: int
    h: int

    @classmethod
    def from_hfov(cls, w: int, h: int, hfov_deg: float) -> Intrinsics:
        f = (w / 2) / math.tan(math.radians(hfov_deg) / 2)
        return cls(f, f, w / 2, h / 2, w, h)

    def scaled(self, w: int, h: int) -> Intrinsics:
        sx, sy = w / self.w, h / self.h
        return Intrinsics(self.fx * sx, self.fy * sy, self.cx * sx, self.cy * sy, w, h)


def _axes_ned(yaw_deg: float, pitch_deg: float, roll_deg: float = 0.0) -> np.ndarray:
    """Columns (right, down, forward) of a camera with the given yaw/pitch/roll, in NED."""
    y, p, r = (math.radians(a) for a in (yaw_deg, pitch_deg, roll_deg))
    f = np.array([math.cos(y) * math.cos(p), math.sin(y) * math.cos(p), -math.sin(p)])
    r0 = np.array([-math.sin(y), math.cos(y), 0.0])
    d0 = np.cross(f, r0)
    rr = math.cos(r) * r0 + math.sin(r) * d0
    dd = -math.sin(r) * r0 + math.cos(r) * d0
    return np.column_stack([rr, dd, f])


def _c_nb(yaw_deg: float, pitch_deg: float, roll_deg: float) -> np.ndarray:
    """Body (FRD) → NED direction cosine matrix, Rz(yaw)·Ry(pitch)·Rx(roll)."""
    y, p, r = (math.radians(a) for a in (yaw_deg, pitch_deg, roll_deg))
    cz, sz, cy, sy, cx, sx = math.cos(y), math.sin(y), math.cos(p), math.sin(p), math.cos(r), math.sin(r)
    rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1.0]])
    ry = np.array([[cy, 0, sy], [0, 1.0, 0], [-sy, 0, cy]])
    rx = np.array([[1.0, 0, 0], [0, cx, -sx], [0, sx, cx]])
    return rz @ ry @ rx


def _rot(axis: np.ndarray, ang: float) -> np.ndarray:
    a = axis / np.linalg.norm(axis)
    k = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + math.sin(ang) * k + (1 - math.cos(ang)) * (k @ k)


@dataclass(frozen=True)
class CamPose:
    """Camera centre (e, n, h above the home plane) and R = world(ENU) ← camera(optical)."""

    e: float
    n: float
    h: float
    R: np.ndarray

    @classmethod
    def stabilized(cls, e: float, n: float, h: float, yaw_deg: float, pitch_deg: float,
                   roll_deg: float = 0.0) -> CamPose:
        return cls(e, n, h, _M_NED_TO_ENU @ _axes_ned(yaw_deg, pitch_deg, roll_deg))

    @classmethod
    def body_fixed(cls, e: float, n: float, h: float, body_yaw: float, body_pitch: float,
                   body_roll: float, gimbal_pitch: float, gimbal_yaw: float = 0.0) -> CamPose:
        r_ned = _c_nb(body_yaw, body_pitch, body_roll) @ _axes_ned(gimbal_yaw, gimbal_pitch)
        return cls(e, n, h, _M_NED_TO_ENU @ r_ned)

    @property
    def centre(self) -> np.ndarray:
        return np.array([self.e, self.n, self.h])

    def perturbed(self, d_pitch: float = 0.0, d_roll: float = 0.0, d_yaw: float = 0.0,
                  d_h: float = 0.0) -> CamPose:
        """Small rotations (rad) about the horizontal right axis, the optical axis and world up."""
        R = self.R
        if d_yaw:
            R = _rot(np.array([0.0, 0.0, 1.0]), -d_yaw) @ R  # yaw is clockwise from north
        if d_pitch:
            right = R[:, 0].copy()
            right[2] = 0.0
            if np.linalg.norm(right) > 1e-9:
                R = _rot(right, d_pitch) @ R
        if d_roll:
            R = _rot(R[:, 2], d_roll) @ R
        return CamPose(self.e, self.n, self.h + d_h, R)


def pixel_to_ground(pose: CamPose, K: Intrinsics, u: float, v: float) -> np.ndarray | None:
    """Ground point (e, n) for pixel (u, v), or None if the ray is above −5°."""
    ray = pose.R @ np.array([(u - K.cx) / K.fx, (v - K.cy) / K.fy, 1.0])
    ray /= np.linalg.norm(ray)
    if ray[2] > -math.sin(math.radians(MIN_DEPRESSION_DEG)):
        return None
    t = -pose.h / ray[2]
    return np.array([pose.e + t * ray[0], pose.n + t * ray[1]])


def ground_to_pixel(pose: CamPose, K: Intrinsics, e: float, n: float,
                    z: float = 0.0) -> tuple[float, float] | None:
    p = pose.R.T @ (np.array([e, n, z]) - pose.centre)
    if p[2] <= 1e-6:
        return None
    return float(K.fx * p[0] / p[2] + K.cx), float(K.fy * p[1] / p[2] + K.cy)


def in_frame(pose: CamPose, K: Intrinsics, e: float, n: float, margin_px: float = 0.0) -> bool:
    px = ground_to_pixel(pose, K, e, n)
    if px is None:
        return False
    u, v = px
    if not (-margin_px <= u <= K.w + margin_px and -margin_px <= v <= K.h + margin_px):
        return False
    return pixel_to_ground(pose, K, min(max(u, 0), K.w), min(max(v, 0), K.h)) is not None


# ---------------------------------------------------------------- CE90 ---------------------

def _erf(x: np.ndarray) -> np.ndarray:  # Abramowitz–Stegun 7.1.26 (|err| < 1.5e-7)
    s = np.sign(x)
    x = np.abs(x)
    t = 1.0 / (1.0 + 0.3275911 * x)
    y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t
             + 0.254829592) * t * np.exp(-x * x)
    return s * y


def _p_inside(r: float, k: float) -> float:
    """P(x²+y² ≤ r²) for x ~ N(0,1), y ~ N(0,k²)."""
    x = np.linspace(-r, r, 2001)
    if k < 1e-9:
        inner = np.ones_like(x)
    else:
        inner = _erf(np.sqrt(np.maximum(r * r - x * x, 0.0)) / (math.sqrt(2) * k))
    pdf = np.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)
    return float(np.trapezoid(pdf * inner, x))


@lru_cache(maxsize=1)
def _ce90_table() -> tuple[np.ndarray, np.ndarray]:
    ks = np.linspace(0.0, 1.0, 51)
    out = []
    for k in ks:
        lo, hi = 1.0, 3.0
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            lo, hi = (mid, hi) if _p_inside(mid, k) < 0.9 else (lo, mid)
        out.append(0.5 * (lo + hi))
    return ks, np.array(out)


def ce90_from_cov(cov: np.ndarray) -> float:
    """Exact CE90 radius (m) of a zero-mean 2-D Gaussian with covariance ``cov``."""
    lam = np.linalg.eigvalsh(np.asarray(cov, float)[:2, :2])
    l1, l2 = max(lam[1], 1e-12), max(lam[0], 0.0)
    ks, fs = _ce90_table()
    return float(math.sqrt(l1) * np.interp(math.sqrt(l2 / l1), ks, fs))


@dataclass(frozen=True)
class GeoNoise:
    """1σ error budget; defaults = the sim nav_noise (sim spec §4, C57, C96)."""

    sigma_rp_deg: float = 1.0
    sigma_yaw_deg: float = 3.0
    sigma_alt_m: float = 1.5
    sigma_px: float = 2.0          # detector/bbox noise at frame resolution
    box_frac: float = 0.05         # box term: extra σ = box_frac · box height (px)
    sigma_skew_m: float = 0.0      # optional horizontal term from timestamp skew × speed


@dataclass(frozen=True)
class GeoFix:
    e: float
    n: float
    cov: np.ndarray       # 2×2 ENU covariance (m²)
    ce_m: float           # CE90
    range_m: float        # slant range


def locate(pose: CamPose, K: Intrinsics, u: float, v: float, box_h_px: float = 0.0,
           noise: GeoNoise = GeoNoise()) -> GeoFix | None:
    """Geolocate pixel (u, v) (box bottom-centre) with a CE90 from the error budget."""
    g0 = pixel_to_ground(pose, K, u, v)
    if g0 is None:
        return None
    sig_px = math.hypot(noise.sigma_px, noise.box_frac * box_h_px)
    rp, yw = math.radians(noise.sigma_rp_deg), math.radians(noise.sigma_yaw_deg)
    cols = []
    sig = []
    for kw, s, step in (("d_pitch", rp, 1e-4), ("d_roll", rp, 1e-4), ("d_yaw", yw, 1e-4),
                        ("d_h", noise.sigma_alt_m, 1e-2)):
        g = pixel_to_ground(pose.perturbed(**{kw: step}), K, u, v)
        cols.append(np.zeros(2) if g is None else (g - g0) / step)
        sig.append(s)
    for du, dv in ((1.0, 0.0), (0.0, 1.0)):
        g = pixel_to_ground(pose, K, u + du * 0.1, v + dv * 0.1)
        cols.append(np.zeros(2) if g is None else (g - g0) / 0.1)
        sig.append(sig_px)
    J = np.column_stack(cols)
    cov = J @ np.diag(np.square(sig)) @ J.T + np.eye(2) * noise.sigma_skew_m ** 2
    slant = float(np.linalg.norm(np.array([g0[0], g0[1], 0.0]) - pose.centre))
    return GeoFix(float(g0[0]), float(g0[1]), cov, ce90_from_cov(cov), slant)


# ------------------------------------------------------- FrameMeta adapters ----------------

def intrinsics_from_meta(meta: dict) -> Intrinsics:
    k = meta["K"]
    return Intrinsics(float(k["fx"]), float(k["fy"]), float(k["cx"]), float(k["cy"]),
                      int(meta["w"]), int(meta["h"]))


def pose_from_meta(meta: dict, origin: Origin) -> CamPose:
    """Camera pose from a FrameMeta dict (pose_est + rel_alt_m + gimbal)."""
    pe = meta["pose_est"]
    e, n, _ = lla_to_enu(pe["lat"], pe["lon"], pe.get("alt_msl_m", origin.alt_msl_m), origin)
    h = float(meta.get("rel_alt_m", pe.get("alt_agl_m", 0.0)))
    g = meta.get("gimbal") or {}
    gp, gy = float(g.get("pitch_deg", -60.0)), float(g.get("yaw_deg", 0.0))
    if g.get("mode", "stabilized") == "body_fixed":
        return CamPose.body_fixed(e, n, h, pe["yaw_deg"], pe.get("pitch_deg", 0.0),
                                  pe.get("roll_deg", 0.0), gp, gy)
    return CamPose.stabilized(e, n, h, float(pe["yaw_deg"]) + gy, gp)


def enu_to_latlon(e: float, n: float, origin: Origin) -> tuple[float, float]:
    lat, lon, _ = enu_to_lla(e, n, 0.0, origin)
    return lat, lon


def latlon_to_enu(lat: float, lon: float, origin: Origin) -> tuple[float, float]:
    e, n, _ = lla_to_enu(lat, lon, origin.alt_msl_m, origin)
    return e, n
