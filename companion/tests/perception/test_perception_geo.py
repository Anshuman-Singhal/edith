"""D8 geo acceptance: round trip <0.1 px at a 20° bank (stabilized gimbal); Monte-Carlo with
nav noise → 90% ±3% inside ce_m (C57, C96)."""

import math
import random

import numpy as np
import pytest
from _e_synth import K720, ORIGIN, meta_for

from edith_companion.perception import geo


@pytest.mark.parametrize("mode", ["stabilized", "body_fixed"])
def test_round_trip_at_20deg_bank(mode):
    K = K720
    if mode == "stabilized":
        # body bank is ignored by the stabilized gimbal: build the pose from a FrameMeta
        _, meta = meta_for("D1", 1, 0, 30.0, -40.0, 60.0, 37.0, -55.0, nav={"rp": 0, "yaw": 0,
                                                                        "alt": 0},
                           body_roll=20.0)
        pose = geo.pose_from_meta(meta, ORIGIN)
        ref = geo.CamPose.stabilized(30.0, -40.0, 60.0, 37.0, -55.0)
        assert np.allclose(pose.R, ref.R, atol=1e-6)
        assert abs(pose.e - 30.0) < 1e-3 and abs(pose.n + 40.0) < 1e-3
    else:
        pose = geo.CamPose.body_fixed(30.0, -40.0, 60.0, 37.0, 3.0, 20.0, -55.0, 5.0)
    worst = 0.0
    n_ok = 0
    for u in np.linspace(0, K.w, 17):
        for v in np.linspace(0, K.h, 11):
            g = geo.pixel_to_ground(pose, K, u, v)
            if g is None:
                continue
            uu, vv = geo.ground_to_pixel(pose, K, *g)
            worst = max(worst, math.hypot(uu - u, vv - v))
            n_ok += 1
    assert n_ok > 100
    assert worst < 0.1


def test_bank_changes_body_fixed_but_not_stabilized():
    a = geo.CamPose.body_fixed(0, 0, 60, 0, 0, 0, -60)
    b = geo.CamPose.body_fixed(0, 0, 60, 0, 0, 20, -60)
    s = geo.CamPose.stabilized(0, 0, 60, 0, -60)
    assert np.allclose(a.R, s.R, atol=1e-9)
    assert not np.allclose(a.R, b.R, atol=1e-3)


def test_rejects_rays_above_minus_5_deg():
    K = K720
    pose = geo.CamPose.stabilized(0, 0, 60, 0, -2.0)
    assert geo.pixel_to_ground(pose, K, K.cx, K.cy) is None          # -2° ray
    assert geo.pixel_to_ground(pose, K, K.cx, K.h) is not None         # bottom row, well below


def test_ce90_table():
    assert abs(geo.ce90_from_cov(np.eye(2)) - 2.146) < 0.005
    assert abs(geo.ce90_from_cov(np.diag([1.0, 1e-12])) - 1.645) < 0.005
    # PLAN's circular formula when σ_r = σ_x
    s = 3.0
    assert abs(geo.ce90_from_cov(np.eye(2) * s * s) - 2.146 * s) < 0.02


def test_monte_carlo_ce90_calibration():
    """True pose + target → noisy pose_est (σ_rp 1°, σ_yaw 3°, σ_alt 1.5 m, horizon-ref roll)
    and noisy pixel → geo fix; |error| ≤ ce_m in 90% ±3% of samples."""
    rng = random.Random(7)
    K = K720
    noise = geo.GeoNoise()
    inside = total = 0
    while total < 3000:
        h = rng.uniform(40, 120)
        pitch = rng.uniform(-80, -35)
        yaw = rng.uniform(0, 360)
        true_pose, meta = meta_for("D1", total, 0, rng.uniform(-50, 50), rng.uniform(-50, 50),
                                   h, yaw, pitch, rng=rng)
        u, v = rng.uniform(0, K.w), rng.uniform(0, K.h)
        truth = geo.pixel_to_ground(true_pose, K, u, v)
        if truth is None:
            continue
        box_h = rng.uniform(8, 60)
        sp = math.hypot(noise.sigma_px, noise.box_frac * box_h)
        mu, mv = u + rng.gauss(0, sp), v + rng.gauss(0, sp)
        est_pose = geo.pose_from_meta(meta, ORIGIN)
        fix = geo.locate(est_pose, K, mu, mv, box_h, noise)
        if fix is None:
            continue
        total += 1
        inside += math.hypot(fix.e - truth[0], fix.n - truth[1]) <= fix.ce_m
    frac = inside / total
    print(f"MC CE90 coverage {frac:.3f} over {total}")
    assert 0.87 <= frac <= 0.93
