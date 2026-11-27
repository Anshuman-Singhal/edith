"""gt_detector (WS-E; sim spec §4, C59, C84, C96): pd, confusions, clutter, rate cap, the
gt_dets_<i>.jsonl join log, UDP 5800+i — and persistent clutter above τ_c becoming a confirmed
companion track through the OffloadDetector (the FA path)."""

import json
import time

from edith_common.geo import SCENARIO_ORIGIN as ORIGIN
from edith_companion.perception.geo import CamPose, Intrinsics, enu_to_latlon, ground_to_pixel
from edith_companion.perception.offload import OffloadDetector
from edith_companion.perception.pipeline import FeedConfig, Perception, alert_eligible
from edith_sim.gt_detector import GtConfig, GtDetector

K = Intrinsics.from_hfov(1280, 720, 70.0)


def true_meta(fid, t_ms, e=0.0, n=0.0, h=60.0, yaw=0.0, pitch=-60.0):
    lat, lon = enu_to_latlon(e, n, ORIGIN)
    return {"frame_id": fid, "t_capture_ms": t_ms, "t_sim_ms": t_ms, "asset_id": "D1",
            "pose_est": {"lat": lat, "lon": lon, "alt_msl_m": ORIGIN.alt_msl_m + h,
                         "alt_agl_m": h, "roll_deg": 0.0, "pitch_deg": 0.0, "yaw_deg": yaw},
            "rel_alt_m": h, "gimbal": {"mode": "stabilized", "pitch_deg": pitch, "yaw_deg": 0.0},
            "K": {"fx": K.fx, "fy": K.fy, "cx": K.cx, "cy": K.cy}, "w": 1280, "h": 720,
            "pose_source": "sidecar", "video": "off"}


def truth(fid, t_ms, objs, e=0.0, n=0.0):
    pose = CamPose.stabilized(e, n, 60.0, 0.0, -60.0)
    out = []
    for ent, cls, oe, on in objs:
        foot, head = ground_to_pixel(pose, K, oe, on), ground_to_pixel(pose, K, oe, on, 1.7)
        bh = foot[1] - head[1]
        out.append({"entity_id": ent, "cls": cls, "visible_frac": 1.0, "range_m": 70.0,
                    "bbox_norm": [(foot[0] - bh * .2) / 1280, (foot[1] - bh) / 720,
                                  bh * .4 / 1280, bh / 720]})
    return {"frame_id": fid, "t_sim_ms": t_ms, "asset_id": "D1", "objects": out}


def test_pd_confusion_rate_cap_and_log(tmp_path):
    log = tmp_path / "gt_dets_1.jsonl"
    g = GtDetector(GtConfig(pd=0.8, rate_hz=10, confusions={"deer-1": "person"}), "D1",
                   seed=1, origin=ORIGIN, log_path=log)
    objs = [("veh-7", "vehicle", 5, 60), ("deer-1", "animal", -10, 70), ("cow", "animal", 12, 50)]
    emitted = n = 0
    for k in range(400):                       # 15 fps camera → capped at 4 Hz
        dets = g.detect(truth(k, k * 66, objs), true_meta(k, k * 66))
        if dets is None:
            continue
        emitted += 1
        n += len(dets)
        for d in dets:
            assert d["infer"]["placement"] == "offload" and d["infer"]["model"] == "gt"
    g.close()
    dur_s = 400 * 66 / 1000
    assert dur_s * 3.5 <= emitted <= dur_s * 4 + 1          # ≤4 Hz cap
    rows = [json.loads(x) for x in log.read_text().splitlines()]
    assert len(rows) == n and abs(n / (3 * emitted) - 0.8) < 0.07
    by_ent = {}
    for r in rows:
        by_ent.setdefault(r["entity_id"], set()).add(r["det_id"])
    assert set(by_ent) == {"veh-7", "deer-1", "cow"}


def test_classes_from_confusion_and_animals():
    g = GtDetector(GtConfig(pd=1.0, confusions={"deer-1": "person"}), "D1", origin=ORIGIN)
    dets = g.detect(truth(0, 0, [("deer-1", "animal", 0, 60), ("cow", "animal", 9, 60),
                                 ("veh-7", "vehicle", -9, 60)]), true_meta(0, 0))
    assert [d["cls"] for d in dets] == ["person", "other", "vehicle"]


def test_persistent_clutter_above_tau_c_becomes_confirmed_track(tmp_path):
    cfg = GtConfig(pd=1.0, latency_ms=0, clutter=[{"id": "clutter-1", "e": 4.0, "n": 70.0,
                                                   "conf": 0.40, "cls": "person"}])
    g = GtDetector(cfg, "D1", instance=4, origin=ORIGIN, send_host="127.0.0.1",
                   log_path=tmp_path / "gt_dets_4.jsonl")
    rx = OffloadDetector(instance=4)
    p = Perception(ORIGIN)
    p.add_feed(FeedConfig("D1", instance=4))
    metas = {}
    try:
        for k in range(8):                     # 4 Hz camera
            t = 10_000 + k * 250
            m = true_meta(k, t)
            metas[k] = m
            g.on_frame(truth(k, t, []), m, now_ms=t)
            time.sleep(0.01)
            for fid, dets in rx.poll():
                fid = k if fid is None else fid
                if p.scheduler.due("D1", metas[fid]["t_capture_ms"]):
                    p.process("D1", metas[fid], dets)
        tracks = p.tracks()
        assert len(tracks) == 1 and tracks[0]["status"] == "confirmed"
        assert alert_eligible(tracks[0]) and tracks[0]["affiliation"] == "unknown"
        rows = [json.loads(x) for x in (tmp_path / "gt_dets_4.jsonl").read_text().splitlines()]
        assert rows and all(r["entity_id"] is None for r in rows)
    finally:
        g.close()
        rx.close()


def test_sub_threshold_clutter_never_starts_a_track():
    cfg = GtConfig(pd=1.0, clutter=[{"id": "c", "e": 4.0, "n": 70.0, "conf": 0.20}])
    g = GtDetector(cfg, "D1", origin=ORIGIN)
    p = Perception(ORIGIN)
    for k in range(20):
        m = true_meta(k, k * 500)
        p.process("D1", m, g.detect(truth(k, k * 500, []), m))
    assert p.tracks() == []
