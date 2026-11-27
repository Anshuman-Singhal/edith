"""D8 tracker acceptance on synthetic GT (L19, C56): lawnmower at 8 m/s, 60 m AGL, 2 Hz; a
stationary person and a 10 m/s vehicle are each confirmed ≤2.5 s after entering view and
IDF1 ≥ 0.8. Machine tracks are always affiliation unknown (I6)."""

import random

from _e_synth import K720, ORIGIN, Target, detections, lawnmower, majority_entity, meta_for

from edith_bench.goal2.metrics import idf1
from edith_companion.perception.pipeline import FeedConfig, Perception
from edith_companion.perception.tracker import Meas, Tracker


def run_lawnmower(seed: int):
    rng = random.Random(seed)
    targets = [Target("stat", "person", 5.0, 150.0),
               Target("mover", "vehicle", -80.0, 110.0, ve=10.0)]
    p = Perception(ORIGIN)
    p.add_feed(FeedConfig("D1"))
    first_in: dict[str, int] = {}
    frames = []
    for k in range(int(60 * 2)):
        t_s = k * 0.5
        t_ms = 1_000_000 + int(t_s * 1000)
        e, n, yaw = lawnmower(t_s)
        pose, meta = meta_for("D1", k, t_ms, e, n, 60.0, yaw, -60.0, rng=rng)
        dets, inview = detections("D1", k, t_ms, pose, targets, t_s, rng)
        # low-confidence clutter below track start (exercise the second pass only)
        for j in range(2):
            dets.append({"det_id": f"D1-{k}-fa{j}", "frame_id": k, "frame_ts_ms": t_ms,
                         "cls": "person", "conf": rng.uniform(0.11, 0.24),
                         "bbox_norm": [rng.uniform(0, .97), rng.uniform(0.3, .95), .01, .03]})
        for ent in inview:
            first_in.setdefault(ent, t_ms)
        p.process("D1", meta, dets)
        hyp = {d["track_id"]: d["_enu"] for d in p.tracks()
               if d["status"] == "confirmed" and d["last_seen_ms"] >= t_ms - 1000}
        frames.append((inview, hyp))
    return p, first_in, frames


def test_lawnmower_confirm_and_idf1():
    p, first_in, frames = run_lawnmower(3)
    assert set(first_in) == {"stat", "mover"}
    conf_lat = {}
    for d in p.tracks(include_lost=True):
        ent = majority_entity(d["det_ids"])
        assert d["affiliation"] == "unknown" and d["affiliation_src"] == "machine"
        if ent in first_in and d["_confirmed_ms"] is not None:
            lat = d["_confirmed_ms"] - first_in[ent]
            conf_lat[ent] = min(conf_lat.get(ent, 1e9), lat)
    print("confirm latency ms", conf_lat)
    assert conf_lat["stat"] <= 2500
    assert conf_lat["mover"] <= 2500
    score = idf1(frames, thr=10.0)
    print("IDF1", round(score, 3))
    assert score >= 0.8
    # the low-confidence clutter never starts a track
    assert all(majority_entity(d["det_ids"]) in ("stat", "mover")
               for d in p.tracks(include_lost=True))


def test_second_pass_extends_but_never_starts():
    import numpy as np

    tr = Tracker()
    R = np.eye(2) * 4.0
    tr.step(0, [Meas("a", "person", 0.6, np.array([0.0, 0.0]), R, 0)])
    assert len(tr.tracks) == 1
    tr.step(500, [Meas("b", "person", 0.15, np.array([0.3, 0.0]), R, 500),
                  Meas("c", "person", 0.15, np.array([80.0, 0.0]), R, 500)])
    assert len(tr.tracks) == 1 and tr.tracks[0].hits == 2
    tr.step(1000, [Meas("d", "vehicle", 0.9, np.array([0.0, 0.0]), R, 1000)])
    assert {t.cls for t in tr.tracks} == {"person", "vehicle"}   # same-class gating only


def test_confirm_needs_mean_conf_above_tau_c():
    import numpy as np

    tr = Tracker()
    R = np.eye(2)
    for i in range(5):
        tr.step(i * 500, [Meas(str(i), "vehicle", 0.27, np.array([0.0, 0.0]), R, i * 500)])
    assert not tr.tracks[0].confirmed          # 0.27 < τ_c(vehicle) 0.35
    tr2 = Tracker()
    for i in range(3):
        tr2.step(i * 500, [Meas(str(i), "person", 0.31, np.array([0.0, 0.0]), R, i * 500)])
    assert tr2.tracks[0].confirmed and tr2.tracks[0].confirmed_ms == 1000


_ = K720
