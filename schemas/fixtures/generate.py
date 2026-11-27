"""Regenerate the v1 contract fixtures:  uv run python schemas/fixtures/generate.py

valid/<type>/*.json   realistic demo values (Piatt County site, origin MGRS 16TCK6100236799,
                      DRONE 1/2 = D1/D2, teammate VIKING 1-2), each valid against the schema
                      AND the pydantic model.
invalid/<type>/*.json each breaks exactly one rule, named in the file name and in `_why`.
                      `_schema_only: true` marks a rule only the JSON Schema enforces.
Edit this script, not the JSON, then re-run it (it rewrites both trees).
"""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

from edith_common.geo import SCENARIO_ORIGIN as O
from edith_common.geo import enu_to_lla, to_mgrs

HERE = Path(__file__).resolve().parent
T = 1795000000000  # ScaledClock epoch ms (interfaces §2 example)


def ll(e: float, n: float, u: float = 0.0) -> tuple[float, float, float]:
    lat, lon, alt = enu_to_lla(e, n, u, O)
    return round(lat, 7), round(lon, 7), round(alt, 2)


def pos(e, n, agl):
    lat, lon, alt = ll(e, n, agl)
    return {"lat": lat, "lon": lon, "alt_msl_m": alt, "alt_agl_m": float(agl)}


OP_LAT, OP_LON, _ = ll(-20, -15)
NAI1 = ll(0, 250)
VEH7 = ll(60, 300)
DEER = ll(-70, 220)
VK12 = ll(-120, 40)

UUIDS = [
    "3f6c1a52-8e0b-4d2a-9c41-7b1e2f9a0c11",
    "a0b1c2d3-e4f5-4a6b-8c7d-9e0f1a2b3c4d",
    "5d2e7f10-3a4b-4c5d-8e6f-0a1b2c3d4e5f",
]

valid: dict[str, dict[str, object]] = {}
invalid: dict[str, dict[str, object]] = {}


def V(type_: str, name: str, obj: object) -> object:
    valid.setdefault(type_, {})[name] = obj
    return obj


def _walk(obj, path):
    keys = path.split(".")
    for k in keys[:-1]:
        obj = obj[int(k)] if isinstance(obj, list) else obj[k]
    last = keys[-1]
    return obj, (int(last) if isinstance(obj, list) else last)


def X(type_: str, name: str, base: object, why: str, *, set=None, delete=(), schema_only=False):
    o = copy.deepcopy(base)
    for path in delete:
        parent, k = _walk(o, path)
        del parent[k]
    for path, val in (set or {}).items():
        parent, k = _walk(o, path)
        parent[k] = val
    if isinstance(o, dict):
        o = {"_why": why, **({"_schema_only": True} if schema_only else {}), **o}
    invalid.setdefault(type_, {})[name] = o


# ============================================================== envelope / binary header
def env(type_, body, src="companion-01", seq=4182, i=0):
    return {"v": 1, "type": type_, "id": UUIDS[i], "ts_ms": T + 1200, "src": src, "seq": seq,
            "body": body}


# ============================================================== messages
hello = V("sys.hello", "glasses_rayneo", {
    "role": "glasses", "proto": [1], "token": "tok-7f3a9c",
    "device": {"model": "RayNeo X3 Pro", "fingerprint": "rayneo/x3pro/x3pro:14/UKQ1.240101/1:user/release-keys", "sdk_int": 34},
    "display": {"win_w": 1280, "win_h": 480, "eye_w": 640, "eye_h": 480, "eyes": "sbs"},
    "input": {"ptt": "hold", "temple_confirm": False},
    "caps": {"inference": ["tflite"], "camera": True, "tts": False},
})
V("sys.hello", "fake", {**copy.deepcopy(hello), "role": "fake",
                        "device": {"model": "FakeGlasses", "fingerprint": "fake", "sdk_int": 0},
                        "caps": {"inference": [], "camera": False, "tts": False}})
V("sys.hello", "companion_reply", {"role": "companion", "proto": [1]})
X("sys.hello", "bad_role_enum", hello, "role not in enum", set={"role": "phone"})
X("sys.hello", "glasses_missing_token", hello, "client role without token", delete=["token"])
X("sys.hello", "bad_eyes_enum", hello, "display.eyes not in enum", set={"display.eyes": "stereo"})
X("sys.hello", "proto_empty", hello, "proto must have >=1 entry", set={"proto": []})

ping = V("sys.ping", "basic", {"t0_ms": 81234})
X("sys.ping", "missing_t0", ping, "t0_ms required", delete=["t0_ms"])
X("sys.ping", "t0_string", ping, "t0_ms must be integer", set={"t0_ms": "81234"})
pong = V("sys.pong", "basic", {"t0_ms": 81234, "t1_ms": T + 5, "t2_ms": T + 6})
X("sys.pong", "missing_t2", pong, "pong requires t2_ms", delete=["t2_ms"])

pose = V("head.pose", "rv", {"yaw_deg": 41.5, "pitch_deg": -3.2, "roll_deg": 0.8,
                             "heading_deg": 41.5, "heading_unc_deg": 6.0, "source": "rv"})
V("head.pose", "scripted_north", {**pose, "yaw_deg": 0.0, "heading_deg": 0.0, "source": "scripted"})
X("head.pose", "heading_360", pose, "heading_deg must be < 360", set={"heading_deg": 360.0})
X("head.pose", "bad_source", pose, "source not in enum", set={"source": "gps"})

ptt_down = V("input.event", "ptt_down", {"kind": "ptt_down", "gesture_seq": 17, "pointer_count": 1,
                                         "held_ms": 300, "ctx": {"proposal_id": "prop-0007"}})
V("input.event", "triple_tap", {"kind": "triple_tap", "gesture_seq": 18, "pointer_count": 1})
V("input.event", "two_finger_hold", {"kind": "two_finger_hold", "gesture_seq": 19,
                                     "pointer_count": 2, "duration_ms": 1140,
                                     "ctx": {"proposal_id": "prop-0007"}})
V("input.event", "bt_ptt_down_no_card", {"kind": "bt_ptt_down", "gesture_seq": 20,
                                         "pointer_count": 0, "held_ms": 40, "ctx": {}})
X("input.event", "ptt_down_without_ctx", ptt_down, "ctx required on ptt_down (C101)", delete=["ctx"])
X("input.event", "ptt_down_without_held", ptt_down, "held_ms required on ptt_down", delete=["held_ms"])
X("input.event", "unknown_kind", ptt_down, "kind not in enum", set={"kind": "long_press"})
X("input.event", "missing_gesture_seq", ptt_down, "gesture_seq required", delete=["gesture_seq"])

vss = V("voice.session.start", "ptt", {"session_id": "vs-0042", "trigger": "ptt"})
V("voice.session.start", "text", {"session_id": "vs-0043", "trigger": "text"})
X("voice.session.start", "trigger_bt", vss, "trigger is bt_ptt, not bt (r4 voice n1)", set={"trigger": "bt"})
vse = V("voice.session.stop", "ptt_up", {"session_id": "vs-0042", "trigger": "ptt", "reason": "ptt_up"})
X("voice.session.stop", "missing_session", vse, "session_id required", delete=["session_id"])

vtx = V("voice.text", "confirm", {"session_id": "vs-0043", "text": "confirm"})
X("voice.text", "text_number", vtx, "text must be a string", set={"text": 7})

vp = V("voice.partial", "partial", {"session_id": "vs-0042", "text": "drone one scout", "conf": None})
X("voice.partial", "missing_conf", vp, "conf is required (nullable)", delete=["conf"])
vf = V("voice.final", "final", {"session_id": "vs-0042", "text": "drone one scout nai one", "conf": 0.91})
X("voice.final", "conf_over_one", vf, "conf must be <= 1", set={"conf": 1.4})

he = V("hud.event", "card_shown", {"kind": "card_shown", "ref": "prop-0007", "ts_ms": 501234})
V("hud.event", "alert_cleared", {"kind": "alert_cleared", "ref": "al-0012", "ts_ms": 501260})
X("hud.event", "bad_kind", he, "kind not in enum", set={"kind": "card_seen"})
X("hud.event", "missing_ref", he, "ref required", delete=["ref"])

tel = V("glasses.telemetry", "x3pro", {
    "battery_pct": 76.0, "current_ua": -412000, "voltage_mv": 3912, "temp_c": 38.5,
    "thermal_status": 1, "thermal_headroom": 0.42, "fps": 30.0, "decode_ms_p95": 7.8,
    "rtt_ms": 11.0, "usb_connected": False})
V("glasses.telemetry", "headroom_unknown", {**tel, "thermal_headroom": None, "usb_connected": True})
X("glasses.telemetry", "usb_string", tel, "usb_connected must be boolean", set={"usb_connected": "false"})
X("glasses.telemetry", "battery_over_100", tel, "battery_pct must be <= 100", set={"battery_pct": 101})

# ============================================================== core
SENSOR = {"sensor_id": "eo0", "kind": "eo", "hfov_deg": 70.0, "w": 1280, "h": 720,
          "stream": "video.down/drone1"}
d1 = V("AssetState", "drone1_mission", {
    "asset_id": "drone1", "callsign": "DRONE 1", "chip": "D1", "kind": "quad",
    "link": {"state": "ok", "last_heard_ms": T + 1150},
    "pos": pos(0, 180, 60), "att": {"roll_deg": 1.2, "pitch_deg": -4.0, "yaw_deg": 2.0},
    "vel_ned": {"n_mps": 9.8, "e_mps": 0.3, "d_mps": 0.0},
    "battery_pct": 81.0, "mode": "AUTO.MISSION", "armed": True, "landed": False,
    "failsafe": {"dll_action": "return"},
    "task": {"proposal_id": "prop-0007", "steps": ["takeoff", "search"], "step_idx": 1,
             "status": "in_progress"},
    "sensors": [SENSOR],
})
V("AssetState", "drone2_link_lost", {
    **copy.deepcopy(d1), "asset_id": "drone2", "callsign": "DRONE 2", "chip": "D2",
    "link": {"state": "lost", "last_heard_ms": T - 20000}, "pos": pos(8, 0, 150),
    "mode": "AUTO.LOITER", "failsafe": {"dll_action": "return", "dll_countdown_s": 4.0},
    "task": {}, "sensors": [{**SENSOR, "stream": "video.down/drone2"}],
})
X("AssetState", "bad_link_state", d1, "link.state not in enum", set={"link.state": "down"})
X("AssetState", "bad_chip", d1, "chip must match D<n>", set={"chip": "DRONE1"})
X("AssetState", "unknown_task_verb", d1, "task.steps verbs are the structural allowlist", set={"task.steps": ["takeoff", "strike"]})
X("AssetState", "missing_pos", d1, "pos required", delete=["pos"])
X("AssetState", "optional_null", d1, "optional failsafe.dll_countdown_s present as null",
  set={"failsafe.dll_countdown_s": None}, schema_only=True)

lat, lon, alt = ll(0, 180, 60)
fm = V("FrameMeta", "drone1", {
    "frame_id": 18342, "t_capture_ms": T + 1100, "t_sim_ms": 131250, "asset_id": "drone1",
    "pose_est": {"lat": lat, "lon": lon, "alt_msl_m": alt, "alt_agl_m": 60.0, "roll_deg": 1.2,
                 "pitch_deg": -4.0, "yaw_deg": 2.0},
    "rel_alt_m": 60.1, "gimbal": {"mode": "stabilized", "pitch_deg": -60.0, "yaw_deg": 0.0},
    "K": {"fx": 914.0, "fy": 914.0, "cx": 640.0, "cy": 360.0}, "w": 1280, "h": 720,
    "pose_source": "sidecar", "video": "on"})
X("FrameMeta", "bad_gimbal_mode", fm, "gimbal.mode not in enum", set={"gimbal.mode": "locked"})
X("FrameMeta", "fx_zero", fm, "K.fx must be > 0", set={"K.fx": 0})

ft = V("FrameTruth", "deer_in_view", {
    "frame_id": 18342, "t_sim_ms": 131250, "asset_id": "drone1",
    "objects": [{"entity_id": "deer-1", "cls": "animal", "bbox_norm": [0.41, 0.52, 0.03, 0.04],
                 "visible_frac": 1.0, "range_m": 112.4, "lat": DEER[0], "lon": DEER[1]}]})
X("FrameTruth", "bbox_three", ft, "bbox_norm needs 4 numbers", set={"objects.0.bbox_norm": [0.4, 0.5, 0.1]})

det = V("Detection", "deer_as_person", {
    "det_id": "gt0-000913", "frame_id": 18342, "frame_ts_ms": T + 1100,
    "source": {"asset_id": "drone1", "sensor_id": "eo0"}, "cls": "person", "conf": 0.62,
    "bbox_norm": [0.41, 0.52, 0.03, 0.04], "det_px_h": 29.0,
    "infer": {"placement": "offload", "model": "gt", "model_sha": "", "t_capture_ms": T + 1100,
              "t_start_ms": T + 1180, "t_end_ms": T + 1180}})
det2 = V("Detection", "vehicle_tiled", {
    **copy.deepcopy(det), "det_id": "c-002201", "cls": "vehicle", "conf": 0.81, "tile": 2,
    "bbox_norm": [0.62, 0.30, 0.06, 0.04], "det_px_h": 31.5,
    "infer": {"placement": "companion", "model": "yolox_tiny_416", "model_sha": "9f2c1e",
              "t_capture_ms": T + 1100, "t_start_ms": T + 1130, "t_end_ms": T + 1192}})
X("Detection", "cls_face", det, "cls is person|vehicle|other only (no biometrics)", set={"cls": "face"})
X("Detection", "bbox_over_one", det, "bbox_norm values must be <= 1", set={"bbox_norm": [0.41, 0.52, 1.3, 0.04]})
X("Detection", "bad_placement", det, "infer.placement not in enum", set={"infer.placement": "cloud"})

trk = V("Track", "veh7_confirmed", {
    "track_id": "t-0031", "alias": "contact 3", "cls": "vehicle", "conf": 0.78, "hits": 4,
    "window": 5, "geo": {"lat": VEH7[0], "lon": VEH7[1], "ce_m": 14.0},
    "vel": {"e_mps": 0.0, "n_mps": 0.0}, "geo_quality": "metric",
    "first_seen_ms": T - 4000, "last_seen_ms": T + 1100, "source_assets": ["drone1"],
    "status": "confirmed", "novelty": 0.9, "affiliation": "unknown", "affiliation_src": "machine",
    "cot_uid": "EDITH-companion-01-trk-t-0031", "det_ids": ["c-002190", "c-002195", "c-002201"]})
V("Track", "teammate_associated", {
    **copy.deepcopy(trk), "track_id": "t-0032", "alias": "contact 4", "cls": "person",
    "geo": {"lat": VK12[0], "lon": VK12[1], "ce_m": 9.0}, "assoc_friend_uid": "EDITH-SIM-tm-2",
    "cot_uid": "EDITH-companion-01-trk-t-0032", "det_ids": []})
V("Track", "human_reclassified", {**copy.deepcopy(trk), "status": "marked",
                                  "affiliation": "neutral", "affiliation_src": "human"})
X("Track", "machine_hostile", trk, "machine detections are always unknown (I6)", set={"affiliation": "hostile"})
X("Track", "too_many_det_ids", trk, "det_ids keeps the last 8", set={"det_ids": [f"c-{i}" for i in range(9)]})
X("Track", "bad_geo_quality", trk, "geo_quality not in enum", set={"geo_quality": "approx"})
X("Track", "negative_ce", trk, "ce_m must be >= 0", set={"geo.ce_m": -1.0})

SIG = {"conf": 0.78, "novelty": 0.9, "proximity": 0.35, "closing": 0.0, "recency": 1.0,
       "class_w": 1.0, "aoi": 1.0}
al = V("Alert", "vehicle_caution", {
    "alert_id": "al-0012", "tier": "caution", "score": 0.71, "kind": "new_contact",
    "label": "VEHICLE", "ref": {"track_id": "t-0031"}, "bearing_deg": 12.4, "range_m": 318.0,
    "ce_m": 14.0, "row2": "DRONE 1 · UNKNOWN · 3 s", "actions": ["watch", "mark", "dismiss"],
    "gesture_dismiss": True, "signals": SIG, "created_ms": T, "expires_ms": T + 60000})
V("Alert", "d2_link_warning", {
    "alert_id": "al-0013", "tier": "warning", "score": 0.95, "kind": "link_lost",
    "label": "D2 LINK", "ref": {"asset_id": "drone2"}, "bearing_deg": None, "range_m": None,
    "row2": "RTL IN 4 s", "actions": ["details"], "gesture_dismiss": False,
    "signals": {**SIG, "novelty": 0.0}, "created_ms": T, "expires_ms": T + 30000})
V("Alert", "flood", {**copy.deepcopy(al), "alert_id": "al-0014", "label": "3 NEW",
                     "tier": "advisory"})
X("Alert", "warning_gesture_dismiss", al, "gesture_dismiss must be false on WARNING",
  set={"tier": "warning"})
X("Alert", "label_free_text", al, "label is an enum (C102)", set={"label": "TRUCK"})
X("Alert", "ref_two_keys", al, "ref holds exactly one of track_id|asset_id|uid",
  set={"ref": {"track_id": "t-0031", "asset_id": "drone1"}})
X("Alert", "bad_action", al, "actions not in enum", set={"actions": ["watch", "engage"]})
X("Alert", "missing_bearing", al, "bearing_deg required (nullable)", delete=["bearing_deg"])

ci = V("CommandIntent", "scout_nai1", {
    "intent_id": "in-0007", "session_id": "vs-0042",
    "utterance": {"text": "drone one scout nai one", "asr_conf": None,
                  "nbest": ["drone one scout nai one"], "engine": "moonshine",
                  "model_sha": "small-streaming-en", "norm_profile": "spoken"},
    "heading_snapshot_deg": 41.5, "operator_pos": {"lat": OP_LAT, "lon": OP_LON},
    "parsed": {"kind": "command", "verb": "search", "asset_ref": "drone1",
               "target": {"kind": "named", "name": "NAI 1"}, "params": {}},
    "slots": [{"name": "asset", "raw_tokens": ["drone", "one"], "value": "drone1", "conf": 1.0},
              {"name": "target", "raw_tokens": ["nai", "one"], "value": "NAI 1", "conf": 1.0}],
    "parser": {"method": "grammar", "conf": 1.0}, "result": "ok"})
V("CommandIntent", "stop_all", {
    **copy.deepcopy(ci), "intent_id": "in-0010",
    "utterance": {**ci["utterance"], "text": "all stop", "nbest": ["all stop"]},
    "parsed": {"kind": "safety_stop", "asset_ref": "all", "stop_via": "grammar", "params": {}},
    "slots": []})
V("CommandIntent", "attack_rejected", {
    **copy.deepcopy(ci), "intent_id": "in-0009",
    "utterance": {**ci["utterance"], "text": "drone one attack the vehicle",
                  "nbest": ["drone one attack the vehicle"]},
    "parsed": {"kind": "command", "asset_ref": "drone1", "params": {}}, "slots": [],
    "result": "rejected", "reject_reason": "out_of_scope"})
V("CommandIntent", "overwatch_self", {
    **copy.deepcopy(ci), "intent_id": "in-0008",
    "parsed": {"kind": "command", "verb": "observe", "asset_ref": "drone2",
               "target": {"kind": "self"}, "params": {"radius_m": 150.0}}})
X("CommandIntent", "bad_result", ci, "result not in enum", set={"result": "maybe"})
X("CommandIntent", "bad_target_kind", ci, "target.kind not in enum", set={"parsed.target.kind": "enemy"})
X("CommandIntent", "missing_params", ci, "parsed.params required", delete=["parsed.params"])

cp = V("CommandProposal", "scout_await", {
    "proposal_id": "prop-0007", "intent_id": "in-0007", "asset_id": "drone1",
    "steps": [{"verb": "takeoff", "params": {"alt_agl_m": 60.0}},
              {"verb": "search", "params": {"size_m": 300.0, "alt_agl_m": 60.0}}],
    "resolved_target": {"lat": NAI1[0], "lon": NAI1[1], "alt_agl_m": 60.0,
                        "mgrs": to_mgrs(NAI1[0], NAI1[1]), "label": "NAI 1"},
    "readback": {"rows": ["D1 TAKEOFF · SEARCH", "NAI 1 · 300 m · 60 m AGL"],
                 "spoken": "drone one, take off and search NAI one"},
    "checks": [{"name": "geofence", "pass": True, "msg": ""},
               {"name": "battery", "pass": True, "msg": "81%"}],
    "confirm_with": ["voice", "touch_companion"], "nonce": "n-6b1f",
    "created_ms": T, "lockout_until_ms": T + 1100, "expires_ms": T + 10500,
    "card_shown_ms": T + 500, "state": "await_confirm"})
X("CommandProposal", "weapon_verb", cp, "steps[].verb is the structural allowlist", set={"steps.1.verb": "release"})
X("CommandProposal", "no_steps", cp, "steps needs >= 1 entry", set={"steps": []})
X("CommandProposal", "bad_mgrs", cp, "resolved_target.mgrs must be MGRS without spaces",
  set={"resolved_target.mgrs": "16T CK 61002 37049"})
X("CommandProposal", "bad_state", cp, "state not in enum (ends at dispatched, C64)", set={"state": "completed"})
X("CommandProposal", "readback_three_rows", cp, "readback.rows has exactly 2", set={"readback.rows": ["a", "b", "c"]})

cf = V("Confirmation", "voice", {
    "proposal_id": "prop-0007", "nonce": "n-6b1f", "method": "voice", "operator_id": "VIKING 1-1",
    "ts_ms": T + 2900,
    "press": {"ptt_down_recv_ms": T + 2500, "held_ms": 300, "est_start_ms": T + 2195},
    "asr": {"text_norm": "confirm", "conf": None, "closed_grammar": None}})
V("Confirmation", "temple", {"proposal_id": "prop-0008", "nonce": "n-77aa", "method": "touch_temple",
                             "operator_id": "VIKING 1-1", "ts_ms": T + 3100, "duration_ms": 1140})
X("Confirmation", "missing_nonce", cf, "nonce required", delete=["nonce"])
X("Confirmation", "held_negative", cf, "press.held_ms must be >= 0", set={"press.held_ms": -5})

ss = V("SafetyStop", "all_hold_d2_lost", {
    "stop_id": "stop-0001", "scope": "all", "source": "temple", "ts_ms": T + 50000,
    "asset_ids": ["drone1", "drone2"], "not_sent": [{"asset_id": "drone2", "reason": "link_lost"}],
    "cancelled_tasks": ["prop-0007"]})
X("SafetyStop", "bad_source", ss, "source not in enum", set={"source": "gesture"})
X("SafetyStop", "bad_not_sent_reason", ss, "not_sent.reason not in enum", set={"not_sent.0.reason": "busy"})

ex = V("Execution", "takeoff_completed", {
    "exec_id": "ex-0021", "proposal_id": "prop-0007", "asset_id": "drone1", "step_idx": 0,
    "verb": "takeoff", "status": "completed", "mav_result": 0, "detail": "alt 59.4 m",
    "ts_ms": T + 23000})
V("Execution", "stop_hold", {"exec_id": "ex-0030", "proposal_id": None, "stop_id": "stop-0001",
                             "asset_id": "drone1", "step_idx": 0, "verb": "hold",
                             "status": "sent", "detail": "DO_SET_MODE AUTO.LOITER",
                             "ts_ms": T + 50010})
V("Execution", "arm_accepted", {**copy.deepcopy(ex), "exec_id": "ex-0020", "verb": "arm",
                                "status": "accepted", "detail": ""})
X("Execution", "null_proposal_no_stop", ex, "proposal_id null requires stop_id", set={"proposal_id": None})
X("Execution", "missing_proposal_id", ex, "proposal_id required (nullable)", delete=["proposal_id"])
X("Execution", "bad_status", ex, "status not in enum", set={"status": "done"})

fb = V("Feedback", "dismiss", {"track_id": "t-0029", "verb": "dismiss", "operator_id": "VIKING 1-1",
                               "method": "voice", "alert_id": "al-0011", "ts_ms": T + 9000})
V("Feedback", "reclassify_neutral", {**fb, "track_id": "t-0031", "verb": "reclassify",
                                     "affiliation": "neutral", "method": "touch_companion",
                                     "alert_id": "al-0012"})
X("Feedback", "reclassify_no_affiliation", fb, "reclassify requires affiliation", set={"verb": "reclassify"})
X("Feedback", "bad_verb", fb, "verb not in enum", set={"verb": "engage"})

tp = V("TeammatePosition", "viking_1_2", {
    "uid": "EDITH-SIM-tm-2", "callsign": "VIKING 1-2", "team": "Cyan", "role": "Team Member",
    "pos": {"lat": VK12[0], "lon": VK12[1], "hae_m": round(O.alt_msl_m + O.geoid_n_m, 2)},
    "course_deg": 45.0, "speed_mps": 0.24, "ts_ms": T, "stale_ms": T + 120000, "source": "sim"})
X("TeammatePosition", "bad_source", tp, "source not in enum", set={"source": "radio"})
X("TeammatePosition", "lat_out_of_range", tp, "pos.lat must be within ±90", set={"pos.lat": 140.07})

hud = {
    "seq": 812, "ts_ms": T + 1200, "mode": "day", "declutter": "full", "quiet": False,
    "operator": {"lat": OP_LAT, "lon": OP_LON, "heading_deg": 41.5, "heading_unc_deg": 6.0},
    "status": {"tak": "ok", "gps": "sim", "companion_battery_pct": 64.0, "data_age_ms": 0,
               "rec": True},
    "assets": [{"asset_id": "drone1", "chip": "D1", "mode_label": "SEARCH", "battery_pct": 81.0,
                "link": "ok", "task_label": "NAI 1"},
               {"asset_id": "drone2", "chip": "D2", "mode_label": "ORBIT", "battery_pct": 77.0,
                "link": "ok", "task_label": "OVW"}],
    "minimap": {"range_m": 500.0,
                "entities": [{"ref": "self", "kind": "self", "marked": False, "rel_e_m": 0.0,
                              "rel_n_m": 0.0, "heading_deg": 41.5, "age_ms": 0, "stale": False},
                             {"ref": "EDITH-SIM-tm-2", "kind": "friend", "marked": False,
                              "rel_e_m": -100.0, "rel_n_m": 55.0, "label": "1-2", "age_ms": 1800,
                              "stale": False},
                             {"ref": "drone1", "kind": "own_drone", "marked": False,
                              "rel_e_m": 20.0, "rel_n_m": 195.0, "heading_deg": 2.0,
                              "label": "D1", "age_ms": 100, "stale": False},
                             {"ref": "t-0031", "kind": "unknown", "marked": False,
                              "rel_e_m": 80.0, "rel_n_m": 315.0, "age_ms": 100, "stale": False}],
                "clusters": []},
    "tape": {"carets": [{"ref": "drone1", "bearing_deg": 5.9, "style": "own_drone"},
                        {"ref": "t-0031", "bearing_deg": 14.3, "style": "unknown"},
                        {"ref": "EDITH-SIM-tm-2", "bearing_deg": 298.8, "style": "friend"}]},
    "alert": {"alert_id": "al-0012", "tier": "caution", "label": "VEHICLE", "bearing_deg": 14.3,
              "range_m": 325.0, "ce_m": 14.0, "row2": "DRONE 1 · UNKNOWN · 3 s",
              "row3": "say WATCH · MARK · DISMISS", "gesture_dismiss": True,
              "shown_since_ms": T + 900, "flash_until_ms": T + 1900,
              "queue": {"count": 1, "warning": 0, "caution": 1, "advisory": 0}},
    "voice": {"state": "idle", "last_heard": "drone one scout nai one"},
}
hud_card = {**copy.deepcopy(hud), "seq": 640,
            "proposal": {"proposal_id": "prop-0007",
                         "rows": ["D1 TAKEOFF · SEARCH", "NAI 1 · 300 m · 60 m AGL"],
                         "expires_in_ms": 9500, "lockout_in_ms": 100,
                         "confirm_with": ["voice", "touch_companion"], "state": "lockout"},
            "voice": {"state": "await_confirm"}}
del hud_card["alert"]
hud_min = {**copy.deepcopy(hud), "seq": 913, "mode": "night", "declutter": "warn",
           "status": {"tak": "lost", "gps": "sim", "companion_battery_pct": None,
                      "data_age_ms": 45000, "rec": True},
           "toast": {"text": "D2 HOLD NOT SENT · LINK", "tier": "warning", "until_in_ms": 3000},
           "undo": {"alert_id": "al-0011", "until_in_ms": 4000},
           "inset": {"stream": "video.down/drone1", "label": "D1 EO", "frame_age_ms": 80,
                     "pinned": True,
                     "boxes": [{"alias": "contact 3", "cls": "vehicle",
                                "bbox_norm": [0.62, 0.30, 0.06, 0.04]}],
                     "crop_stream": "video.crop/al-0012"},
           "voice": {"state": "listening", "partial": "drone two"}}
for t in ("HudState", "hud.state"):
    V(t, "alert_banner", hud)
    V(t, "confirm_card", hud_card)
X("HudState", "bad_carets_style", hud, "tape.carets[].style not in enum",
  set={"tape.carets.0.style": "drone"})
X("HudState", "alert_warning_gesture", hud, "alert.gesture_dismiss false on WARNING",
  set={"alert.tier": "warning"})
X("HudState", "bad_proposal_state", hud_card, "proposal.state not in enum",
  set={"proposal.state": "dispatched"})
X("HudState", "missing_voice", hud, "voice required", delete=["voice"])
X("HudState", "rows_one", hud_card, "proposal.rows has exactly 2", set={"proposal.rows": ["x"]})
V("HudState", "night_warn_inset", hud_min)
X("hud.state", "bad_declutter", hud, "declutter not in enum", set={"declutter": "none"})

pd = V("perception.detections", "two", {"detections": [det, det2]})
X("perception.detections", "item_bad_cls", pd, "detections[] items must be Detection",
  set={"detections.0.cls": "animal"})
X("perception.detections", "missing_detections", pd, "detections required", delete=["detections"])

# udp.detections is a bare array (no _why key possible) -> reason in the file name only
V("udp.detections", "gt_batch", [det, det2])
V("udp.detections", "empty", [])
bad_batch = copy.deepcopy([det])
bad_batch[0]["conf"] = 2.0
invalid.setdefault("udp.detections", {})["conf_over_one"] = bad_batch

# ============================================================== envelopes
V("envelope", "hud_state", env("hud.state", hud, seq=4182))
V("envelope", "head_pose_up", env("head.pose", pose, src="glasses-x3pro", seq=101, i=1))
V("envelope", "card_shown_up", env("hud.event", he, src="glasses-x3pro", seq=102, i=2))
V("envelope", "unknown_future_type", env("sys.future_thing", {"x": 1}, seq=4183))
e0 = env("head.pose", pose, src="glasses-x3pro", seq=101, i=1)
X("envelope", "v2", e0, "v must be 1", set={"v": 2})
X("envelope", "id_not_uuid4", e0, "id must be a uuid4", set={"id": "msg-101"})
X("envelope", "negative_seq", e0, "seq must be >= 0", set={"seq": -1})
X("envelope", "body_array", e0, "body must be an object", set={"body": [1, 2]})
X("envelope", "missing_src", e0, "src required", delete=["src"])

bh = V("binary_header", "audio_preroll", {"stream": "audio.up", "seq": 5501, "ts_ms": T + 10,
                                          "codec": "pcm_s16le", "sr": 16000, "ch": 1,
                                          "preroll": True})
V("binary_header", "video_down", {"stream": "video.down/drone1", "seq": 9921, "ts_ms": T + 40,
                                  "codec": "jpeg", "w": 320, "h": 240, "frame_id": 18342})
V("binary_header", "crop", {"stream": "video.crop/al-0012", "seq": 12, "ts_ms": T + 900,
                            "codec": "jpeg", "w": 96, "h": 72})
X("binary_header", "bad_stream", bh, "stream not one of the §2 forms", set={"stream": "audio.sideways"})
X("binary_header", "bad_codec", bh, "codec not in enum", set={"codec": "opus"})
X("binary_header", "preroll_string", bh, "preroll must be boolean", set={"preroll": "yes"})


def write() -> int:
    n = 0
    for kind, table in (("valid", valid), ("invalid", invalid)):
        root = HERE / kind
        if root.exists():
            shutil.rmtree(root)
        for type_, items in table.items():
            d = root / type_
            d.mkdir(parents=True)
            for name, obj in items.items():
                (d / f"{name}.json").write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
                n += 1
    return n


if __name__ == "__main__":
    print(f"wrote {write()} fixtures")
