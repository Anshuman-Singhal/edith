"""D8 fusion acceptance: two drones with overlapping footprints and independent nav noise →
duplicate rate (confirmed fused tracks per GT entity) < 1.2."""

import random

from _e_synth import ORIGIN, Target, detections, majority_entity, meta_for
from edith_bench.goal2.metrics import duplicate_rate
from edith_companion.perception.pipeline import FeedConfig, Perception


def test_two_drone_overlap_duplicate_rate():
    rng = random.Random(21)
    targets = [Target("a", "person", -10, 70), Target("b", "person", 12, 85),
               Target("c", "vehicle", 0, 60, ve=3.0), Target("d", "vehicle", 25, 100),
               Target("e", "person", -25, 95)]
    p = Perception(ORIGIN)
    for a in ("D1", "D2"):
        p.add_feed(FeedConfig(a))
    seen_by: dict[str, set] = {}
    for k in range(120):
        t_s = k * 0.5
        t_ms = 3_000_000 + k * 500
        for a, (e0, yaw) in {"D1": (-30.0, 10.0), "D2": (30.0, -10.0)}.items():
            pose, meta = meta_for(a, k, t_ms + (0 if a == "D1" else 120), e0, 2.0 * t_s, 60.0,
                                  yaw, -60.0, rng=rng)
            dets, inview = detections(a, k, t_ms, pose, [t for t in targets], t_s, rng)
            for ent in inview:
                seen_by.setdefault(ent, set()).add(a)
            p.process(a, meta, dets, t_ms=t_ms + (0 if a == "D1" else 120))
    assert all(len(v) == 2 for v in seen_by.values()), seen_by   # real overlap
    conf = {d["track_id"]: majority_entity(d["det_ids"]) for d in p.tracks(include_lost=True)
            if d["_confirmed_ms"] is not None}
    rate = duplicate_rate(conf)
    print("duplicate rate", rate, conf)
    assert set(conf.values()) == {t.id for t in targets}
    assert rate < 1.2
    assert any(len(d["source_assets"]) == 2 for d in p.tracks(include_lost=True))
