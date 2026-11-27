"""D8 friendly association (C52, C98; r4 defense nit 1, ml nb1).

- A teammate walking 1.5 m/s with 10 s PLI and nav noise → 0 alert-eligible and 0
  CoT-eligible tracks over 120 s in view, while a stranger 30 m away is alert-eligible.
- A 25 s TAK partition with a (walking) teammate entering the FOV during the outage, whose
  last PLI is >30 s old at first association → still 0 / 0 (freshness measured from link loss;
  dead-reckoning with the true PLI age capped at 30 s).
"""

import math
import random

from _e_synth import ORIGIN, Target, detections, majority_entity, meta_for
from edith_companion.perception.friendly import FriendlyAssociator, Pli
from edith_companion.perception.geo import enu_to_latlon
from edith_companion.perception.pipeline import (
    FeedConfig,
    Perception,
    alert_eligible,
    cot_eligible,
)


def pli(uid, e, n, course, speed, ts_ms, rng):
    lat, lon = enu_to_latlon(e + rng.gauss(0, 2.0), n + rng.gauss(0, 2.0), ORIGIN)
    return {"uid": uid, "callsign": "VIKING 1-2", "team": "Cyan", "role": "Team Member",
            "pos": {"lat": lat, "lon": lon, "hae_m": 177.0},
            "course_deg": (course + rng.gauss(0, 5)) % 360,
            "speed_mps": max(0.0, speed + rng.gauss(0, 0.2)), "ts_ms": ts_ms,
            "stale_ms": ts_ms + 120_000, "source": "sim"}


def walker_pos(t_s, e0, n0, speed=1.5, leg=60.0):
    """Back-and-forth along east: returns (e, n, course)."""
    d = speed * t_s
    k, r = divmod(d, leg)
    if int(k) % 2 == 0:
        return e0 + r, n0, 90.0
    return e0 + leg - r, n0, 270.0


def run(duration_s, teammate_fn, stranger_fn, pli_ok, tak_events, seed, occlusion=()):
    rng = random.Random(seed)
    p = Perception(ORIGIN)
    p.add_feed(FeedConfig("D2"))
    tak = dict(tak_events)
    bad, stranger_alert, assoc_seen, first_assoc_age = [], False, 0, []
    for k in range(int(duration_s * 2)):
        t_s = k * 0.5
        t_ms = 5_000_000 + k * 500
        if t_s in tak:
            p.on_tak_status(tak[t_s], t_ms)
        te, tn, course = teammate_fn(t_s)
        if abs(t_s % 10.0) < 1e-9 and pli_ok(t_s):
            p.on_teammate(pli("tm-2", te, tn, course, 1.5, t_ms, rng))
        tgts = [] if any(a <= t_s < b for a, b in occlusion) else [Target("tm", "person", te, tn)]
        if stranger_fn:
            se, sn = stranger_fn(t_s)
            tgts.append(Target("st", "person", se, sn))
        pose, meta = meta_for("D2", k, t_ms, 0.0, -40.0, 60.0, 0.0, -50.0, rng=rng)
        dets, _ = detections("D2", k, t_ms, pose, tgts, t_s, rng)
        before = {d["track_id"] for d in p.tracks() if "assoc_friend_uid" in d}
        for d in p.process("D2", meta, dets):
            ent = majority_entity(d["det_ids"])
            if ent == "tm":
                if alert_eligible(d) or cot_eligible(d):
                    bad.append((t_s, d["track_id"]))
                if d.get("assoc_friend_uid"):
                    assoc_seen += 1
                    if d["track_id"] not in before:
                        pl = p.friendly.pli["tm-2"]
                        first_assoc_age.append(FriendlyAssociator.age_true_s(pl, t_ms))
            if ent == "st" and alert_eligible(d) and cot_eligible(d):
                stranger_alert = True
    return bad, stranger_alert, assoc_seen, first_assoc_age


def test_walking_teammate_never_alerts_stranger_does():
    bad, stranger_alert, assoc_seen, _ = run(
        120, lambda t: walker_pos(t, -30.0, 30.0),
        lambda t: (walker_pos(t, -30.0, 30.0)[0], 60.0), lambda t: True, {}, seed=4)
    assert bad == []
    assert assoc_seen > 100
    assert stranger_alert


def test_tak_partition_teammate_enters_fov_during_outage():
    # PLI at t=0 only before the partition (9 s → 34 s, LinkMonitor `lost` 3 s in, `ok` at
    # the end); the teammate walks east from off-screen and enters the FOV at ≈31 s.
    bad, _, assoc_seen, ages = run(
        60, lambda t: (-112.0 + 1.5 * t, 30.0, 90.0), None,
        lambda t: not (9.0 <= t < 34.0), {12.0: "lost", 34.5: "ok"}, seed=8)
    assert bad == []
    assert assoc_seen > 10
    assert ages and max(ages) > 30.0      # the link-loss freshness rule was what admitted it


def test_freshness_rule_and_sticky_release():
    fa = FriendlyAssociator()
    fa.on_pli(Pli("f1", 0.0, 0.0, 90.0, 1.5, 0))
    # 31 s old, TAK ok → not fresh for a first association
    assert fa.evaluate(1, "person", 46.5, 0.0, 5.0, 31_000) is None
    # TAK lost at 10 s → freshness age 21 s → associates; DR capped at 30 s → (45, 0)
    fa.on_tak_status("lost", 10_000)
    de, dn = fa.dead_reckon(fa.pli["f1"], 31_000)
    assert math.isclose(de, 45.0) and abs(dn) < 1e-9
    assert math.isclose(fa.radius_m(fa.pli["f1"], 31_000, 5.0), 30.0)
    assert fa.evaluate(1, "person", 46.5, 0.0, 5.0, 31_000) == "f1"
    assert fa.evaluate(2, "vehicle", 46.5, 0.0, 5.0, 31_000) is None   # persons only
    # sticky: two far updates keep it, the third releases
    assert fa.evaluate(1, "person", 200.0, 0.0, 5.0, 31_500) == "f1"
    assert fa.evaluate(1, "person", 200.0, 0.0, 5.0, 32_000) == "f1"
    assert fa.evaluate(1, "person", 200.0, 0.0, 5.0, 32_500) is None
