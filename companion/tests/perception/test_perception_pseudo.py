"""D8 pseudo-mode acceptance (C95; r4 ml nb2/nb3): textured synthetic frames, true camera
panning 20°/s while pose_est stays frozen → stationary targets confirmed ≤2.5 s and IDF1 ≥ 0.8
in the motion-compensated image plane; the ECC fallback is hit at least once."""

import math
import random

import cv2
import numpy as np
from _e_synth import ORIGIN, Target, meta_for
from edith_bench.goal2.metrics import idf1
from edith_companion.perception.geo import CamPose, Intrinsics, ground_to_pixel
from edith_companion.perception.pipeline import FeedConfig, Perception, alert_eligible, to_wire

TEX_M, TEX_PX = 400.0, 1000          # texture covers ±200 m at 0.4 m/px
RW, RH = 640, 360                    # render size (pipeline resizes to 1280×720)
K_R = Intrinsics.from_hfov(RW, RH, 60.0)
K_720 = K_R.scaled(1280, 720)


def basemap(seed: int = 5) -> np.ndarray:
    """Procedural multi-scale texture (stand-in for the C93 procedural basemap)."""
    rng = np.random.default_rng(seed)
    img = np.zeros((TEX_PX, TEX_PX), np.float32)
    for sigma, amp in ((40, 70), (12, 45), (3, 35), (1, 25)):
        img += amp * cv2.GaussianBlur(rng.standard_normal((TEX_PX, TEX_PX)).astype(np.float32),
                                      (0, 0), sigma) * sigma ** 0.5
    for _ in range(120):  # fields / buildings
        x, y = rng.integers(0, TEX_PX, 2)
        w, h = rng.integers(8, 60, 2)
        cv2.rectangle(img, (int(x), int(y)), (int(x + w), int(y + h)), float(rng.uniform(-90, 90)),
                      -1)
    img = cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX)
    return cv2.cvtColor(img.astype(np.uint8), cv2.COLOR_GRAY2BGR)


def render(tex: np.ndarray, pose: CamPose, contrast: float = 1.0) -> np.ndarray:
    Rt = pose.R.T
    C = pose.centre
    Hg = np.diag([K_R.fx, K_R.fy, 1.0])
    Hg[0, 2], Hg[1, 2] = K_R.cx, K_R.cy
    Hg = Hg @ np.column_stack([Rt[:, 0], Rt[:, 1], -Rt @ C])
    s = TEX_M / TEX_PX
    A = np.array([[s, 0, -TEX_M / 2], [0, -s, TEX_M / 2], [0, 0, 1.0]])
    img = cv2.warpPerspective(tex, Hg @ A, (RW, RH), flags=cv2.INTER_LINEAR)
    if contrast != 1.0:
        img = np.clip((img.astype(np.float32) - 128) * contrast + 128, 0, 255).astype(np.uint8)
    return img


def yaw_at(t_s: float) -> float:
    """Triangle sweep 0° → 80° → 0° at 20°/s."""
    ph = (t_s * 20.0) % 160.0
    return ph if ph <= 80.0 else 160.0 - ph


def test_pan_20dps_frozen_pose():
    rng = random.Random(11)
    tex = basemap()
    targets = [Target(f"p{i}", "person", 70 * math.sin(math.radians(a)),
                      70 * math.cos(math.radians(a)), h_m=1.8)
               for i, a in enumerate((10, 35, 60, 80))]
    p = Perception(ORIGIN)
    p.add_feed(FeedConfig("R1", geo_quality="pseudo"))
    frozen = None
    first_in: dict[str, int] = {}
    frames = []
    dim_ticks = {5, 21}                        # mid-sweep low-contrast (dusk) frames
    for k in range(40):                         # 20 s at 2 Hz
        t_s = k * 0.5
        t_ms = 2_000_000 + k * 500
        pose = CamPose.stabilized(0.0, 0.0, 60.0, yaw_at(t_s), -40.0)
        _, meta = meta_for("R1", k, t_ms, 0.0, 0.0, 60.0, 0.0, -40.0, K=K_R)
        frozen = frozen or meta["pose_est"]
        meta["pose_est"] = dict(frozen)          # pose_est frozen (replay)
        img = render(tex, pose, 0.1 if k in dim_ticks else 1.0)
        dets, gt = [], {}
        for tg in targets:
            foot = ground_to_pixel(pose, K_720, tg.e, tg.n, 0.0)
            head = ground_to_pixel(pose, K_720, tg.e, tg.n, tg.h_m)
            if foot is None or head is None or not (0 <= foot[0] < 1280 and 0 <= foot[1] < 720):
                continue
            gt[tg.id] = foot
            first_in.setdefault(tg.id, t_ms)
            if rng.random() > 0.95:
                continue
            u, v = foot[0] + rng.gauss(0, 2), foot[1] + rng.gauss(0, 2)
            bh = max(6.0, foot[1] - head[1])
            bw = 0.4 * bh
            dets.append({"det_id": f"R1-{k}-{tg.id}", "frame_id": k, "frame_ts_ms": t_ms,
                         "cls": "person", "conf": rng.uniform(0.5, 0.9),
                         "bbox_norm": [(u - bw / 2) / 1280, (v - bh) / 720, bw / 1280, bh / 720]})
        p.process("R1", meta, dets, frame=img)
        hyp = {d["track_id"]: d["_px"] for d in p.tracks()
               if d["status"] == "confirmed" and d["last_seen_ms"] == t_ms}
        frames.append((gt, hyp))
    stats = p.feeds["R1"].motion.stats
    print("motion", stats)
    assert stats["ecc"] >= 1 and stats["fail"] == 0
    lat = {}
    for d in p.tracks(include_lost=True):
        assert d["geo_quality"] == "pseudo" and d["affiliation"] == "unknown"
        assert "assoc_friend_uid" not in d          # pseudo tracks skip friendly assoc (nb3)
        ents = [x.rsplit("-", 1)[-1] for x in d["det_ids"]]
        ent = max(set(ents), key=ents.count)
        if d["_confirmed_ms"] is not None:
            lat[ent] = min(lat.get(ent, 1e9), d["_confirmed_ms"] - first_in[ent])
    print("confirm latency ms", lat)
    assert set(lat) == set(first_in)
    assert max(lat.values()) <= 2500
    score = idf1(frames, thr=40.0)
    print("IDF1", round(score, 3))
    assert score >= 0.8
    from edith_common import schema
    for d in p.tracks(include_lost=True):
        schema.validate("Track", to_wire(d))
    assert any(alert_eligible(d) for d in p.tracks(include_lost=True))


def test_orb_fails_on_dim_frame_and_ecc_recovers():
    from edith_companion.perception.motion import MotionEstimator

    tex = basemap()
    me = MotionEstimator((1280, 720))
    z = cv2.resize(render(tex, CamPose.stabilized(0, 0, 60, 10, -40)), (1280, 720))
    a = cv2.resize(render(tex, CamPose.stabilized(0, 0, 60, 20, -40)), (1280, 720))
    b = cv2.resize(render(tex, CamPose.stabilized(0, 0, 60, 30, -40), 0.1), (1280, 720))
    me.update(z)
    assert me.update(a)[1] == "orb"
    H, method = me.update(b)                    # ORB finds no keypoints; ECC from last H
    assert method == "ecc" and H is not None
    # check against the analytic rotation homography K R_b^T R_a K^-1 (optical frames)
    pa, pb = CamPose.stabilized(0, 0, 60, 20, -40), CamPose.stabilized(0, 0, 60, 30, -40)
    Km = np.array([[K_720.fx, 0, K_720.cx], [0, K_720.fy, K_720.cy], [0, 0, 1]])
    Ht = Km @ pb.R.T @ pa.R @ np.linalg.inv(Km)
    for x, y in ((640, 360), (300, 500), (1000, 600)):
        q1 = H @ [x, y, 1]
        q2 = Ht @ [x, y, 1]
        assert math.dist(q1[:2] / q1[2], q2[:2] / q2[2]) < 6.0
