# Simulation spec (PLAN v2)

This file holds the normative detail behind [PLAN.md §3.6](../PLAN.md#36-simulation). WS-D (Simon) owns it. The exception is `gt_detector`, which WS-E owns, and the teammate CoT publisher, which WS-F owns.

## 1. Shared vehicle profile (L15, C62)

`sim/profiles/quad_sim.yaml` is the **single source** for vehicle behaviour:

- MockVehicle reads it.
- The PX4 launcher applies it as parameters **after boot**, reads every value back, and aborts on any mismatch. This step is needed because `PX4_SIM_SPEED_FACTOR` rewrites `COM_DL_LOSS_T` in rcS [probed].
- `edith scenario lint` uses it for kinematic bounds.
- A scenario can override keys only through `profile_overrides`, which must be disclosed in the scenario header.

```yaml
# sim/profiles/quad_sim.yaml  — sim-tuned, disclosed (faster than PX4 defaults 1.5 / 5 m/s)
MPC_TKO_SPEED: 3.0        # m/s climb
MPC_XY_CRUISE: 10.0       # m/s
MIS_TAKEOFF_ALT: 60
RTL_RETURN_ALT: 60
MPC_LAND_SPEED: 0.7
NAV_DLL_ACT: 2            # Return (C12); enum value UNVERIFIED vs v1.18 param reference
COM_DL_LOSS_T: 20         # s; demo_jam.yaml overrides to 8 (C78, disclosed)
COM_DISARM_PRFLT: 10      # s auto-disarm if armed and not flying [probed]
COM_LOW_BAT_ACT: 0        # warn only (SITL default 3 [probed])
SIM_BAT_DRAIN: 1800       # s; SITL otherwise floors at 50% within 30 s [probed]
SIM_BAT_MIN_PCT: 10
GF_ACTION: 1
GF_MAX_VER_DIST: 120
orbit_vel_mps: 5          # companion-side DO_ORBIT velocity (not a PX4 param)
```

## 2. `edith_common.px4` (shared by Mock and the adapter, C62)

This module is owned by WS-D even though it sits under `common/`; that ownership is recorded in `docs/OWNERS.yaml`. It covers:

- **Identity:** heartbeat `autopilot=12`, `type=2`, sysid = instance + 1. The companion uses sysid 245.
- **Mode encoding:** `custom_mode = main<<16 | sub<<24`. The modes used are AUTO.TAKEOFF, AUTO.LOITER (4/3), AUTO.MISSION, AUTO.RTL, AUTO.LAND and **POSCTL.ORBIT (3/1)**.
- **Acknowledgements:** one `COMMAND_ACK` per command.
- **Mode transitions:**
  - `DO_REPOSITION` → LOITER.
  - Mission end → LOITER.
  - RTL → LAND → disarm.
- **Failsafe:** the data-link-loss action runs only while armed and in air.
- **Mission protocol:** the `MISSION_COUNT` / `MISSION_REQUEST_INT` / `MISSION_ITEM_INT` / `MISSION_ACK` handshake. Fence items use type 5001.
- **Parameters:** byte-wise int32 `PARAM_SET` encoding.
- **`completed` definitions** for each verb, as listed in [interfaces.md §6](interfaces.md#6-asset-primitives-and-outbound-classifier).

**Contract suite:** `companion/tests/assets/contract/`, owned by WS-B.

- It is parametrized `--assets mock|px4`.
- It runs arm → takeoff → goto → orbit → search mission → hold → rtl → land, plus the composed landed + search case and the landed + orbit case.
- `edith sim record-px4` captures a golden PX4 trace on any laptop: the mode sequence, the ACKs and the mission handshake, saved to `sim/traces/px4_1.18.json`. CI diffs Mock's trace against it.

## 3. Process wiring

```
PX4/Mock i ──(sends 14540+i)──► linkshaper ──► companion udpin 14740+i     (sysid 245)
           ◄──(binds 14580+i)── linkshaper ◄── companion replies
                                   └─ unimpaired copy ──► simd :14640+i (cameras, gt_detector)
companion :16968 ⇄ linkshaper tak :16969 ⇄ fake CoT router :18088 (UDP fan-out) ⇄ teammate sim
```

- **Wire log:** linkshaper writes every MAVLink message in both directions to `runs/<ts>/mavlink_wire.jsonl` (`t_sim_ms`, dir, asset, msgid, class, `dropped`). This log is the independent witness for `wire:` expects and for invariants I1, I2 and I7 (C50).
- **Jam windows:** linkshaper applies drop, latency, partition and bandwidth windows to `mavlink:<asset>`, `tak:*` and `video:<asset>`. Cameras honour `video:` windows.
- **Truth tap:** the truth tap is never impaired.
- **Process clock:** every process runs on ScaledClock (`EDITH_T0_NS`, `EDITH_SPEED`).

## 4. Cameras, video policy and frame sync (C59, C60)

- **Camera model:** `simd` renders a synthetic view (NAIP orthophoto homography plus metric sprites; teammates are drawn as person sprites, C52), or plays back replay clips.
  - **Gimbal:** `gimbal.mode: stabilized` is the default. Pitch is relative to the horizon, yaw is relative to the body, and body roll and pitch are ignored. The optical frame is x-right, y-down, z-forward. The projector in `perception/geo.py` uses the same convention, tested in D8.
- **Virtual frames:** these run on sim time at the scenario's `fps`. Each one produces:
  - a `FrameMeta` sidecar on 5700+i, carrying `pose_est` = true pose + `nav_noise` {σ_rp 1°, σ_yaw 3°, σ_alt 1.5 m, timestamp skew U(0, 50 ms)}.
  - a `FrameTruth` record in `runs/<ts>/frame_truth_<i>.jsonl`.
- **Encoded video:** this is `video: on|off|auto`. `auto` means off for `--headless --detector gt` and on otherwise.
  - When on, the encoder uses libx264 `tune=zerolatency` with no B-frames, and its rate is **capped at 15 fps of wall-clock time** (frames are decimated at `--speed` >1).
  - Each access unit is preceded by an SEI `user_data_unregistered` NAL carrying `frame_id`. The companion parses it from the packet bytes before decoding.
  - Fallback: `pts = frame_id·90000/fps`, anchored on the first sidecar pair.
  - The supervisor writes `runs/<ts>/sdp/drone<i>.sdp`.
- **Tier B:** there is no sidecar. Pose comes from interpolating ATTITUDE and GLOBAL_POSITION_INT (`pose_source: telemetry_interp`).
- **gt_detector** (WS-E, `sim/edith_sim/gt_detector.py`):
  - It reads FrameTruth in-process.
  - It applies `pd`, `fa_per_h`, latency, bbox noise, scripted `confusions` (the planted false positive) and persistent `clutter` objects.
  - It emits `[Detection]` (`placement=offload, model=gt`) on UDP 5800+i at the camera's virtual rate, capped at 4 Hz. The companion scheduler subsamples according to its rate policy.
  - The companion never imports `edith_sim`. A lint test enforces this.

## 5. Scenario YAML v2

| Key | Meaning |
|---|---|
| `version: 2`, `seed` | Format version; one seed for mover, noise, gt |
| `origin{lat, lon, alt_msl, geoid_n_m}` | ENU origin; geoid N for `hae` |
| `vehicle_profile`, `profile_overrides` | §1 |
| `basemap`, `ao`, `safety` | NAIP item; AO polygon (= geofence, ENU m); safety limits (C38) |
| `video` | `on|off|auto` |
| `operator`, `teammates[]` | Paths `{t, e, n, heading?}`; teammates have `sprite` (rendered as persons) |
| `assets[]` | `id, callsign, instance, spawn{e,n}, camera{mode: synth|replay, w, h, hfov, pitch, gimbal, fps, clip?}` |
| `gazetteer[]` | `name, e, n, area_m?, aliases[]` (C66) |
| `entities[]` | `id, cls (vehicle|person|animal), sprite, path[] or loiter_radius_m` |
| `gt_detector` | `pd, fa_per_h, latency_ms, bbox_noise_px, rate_hz, confusions{entity: cls}, clutter[]` |
| `events[]` | `id` plus `t:` (absolute sim s) **or** `on:` (`card_shown: <event>`, `alert_shown: {gt_entity}`, `event: <id>`) with `after_s`; action `say`, `touch`, `jam{duration_s, links}`, `assert_hold` |
| `expect[]` | Anchored assertions (§6); a headless run exits non-zero if any fails |

## 6. Anchored expects and scenario lint (L15, C63)

Every expectation is relative to an anchor:
- `after: <event id>`
- `after: {gt: entity_in_fov, asset, entity, min_dwell_s}`
- `during: {from, to}`
- `global`

with `within_s`. Absolute `by_t` is not allowed. The predicates are:
- `proposal{steps, state}`
- `gt{asset, mode, alt_agl_min}` (vehicle-side truth)
- `asset{id, link, mode}` (the companion's view)
- `alert{kind, cls, tier, shown}`
- `alerts{tier|gt_entity, count}`
- `cot{type|gt_entity, how, live, near_friend_m, count}`
- `tak{link}`
- `router_log{queued_min, flushed, order_preserved, original_time}`
- `wire{asset?, class, count, window_s}`
- `intent{result}`
- `assoc_friend{min}`
- `invariant_violations`

`./edith scenario lint <file>` fails when:

1. Any `within_s` is less than its lower bound plus 2 s. Lower bounds come from the profile and scripted timing:
   - card latency + lockout + the scripted confirm delay;
   - arm 1 s + climb (alt / `MPC_TKO_SPEED`) + path length / `MPC_XY_CRUISE`;
   - `COM_DL_LOSS_T` for link loss;
   - the 3 s TAK lost threshold.
2. A GT anchor never occurs in a **deterministic pre-run**. The pre-run steps the mover and an in-process Mock (dt 20 ms) with the scripted commands at 50× and computes `entity_in_fov` analytically.
3. An event references an unknown id, or an `expect` uses `by_t`.

A lint test commits a deliberately infeasible copy of the vignette and asserts that lint rejects it.

## 7. `scenarios/demo_vignette.yaml` (authored in D2)

Geometry (ENU m):

| Item | Position |
|---|---|
| Launch / CP 3 | (0, 0) |
| D1 | (0, 0) |
| D2 | (8, 0) |
| Operator VIKING 1-1 | (−20, −15) |
| VIKING 1-2 | walks (−120, 40) → (−60, 100) |
| VIKING 1-3 | (90, −60) |
| NAI 1 | (0, 250); 300 m square; 5 lawnmower legs |
| NAI 2 | (380, −120) |
| Vehicle veh-7 | Parked at (60, 300) until t260, then drives to (400, 600) |
| deer-1 | Animal at (−70, 220), loitering within 10 m; gt confuses it as a person |
| Sub-threshold clutter | (120, 380), conf 0.3 |

The teammates sit 100–125 m from the operator, inside the ground footprint of D2's 150 m overwatch orbit (75–141 m radius), so friendly association is exercised. The deer and the vehicle are more than 150 m from the operator, so they raise CAUTION, never WARNING.

```yaml
events:
  - {id: scout,    t: 30,  say: "drone one scout nai one"}
  - {id: scout_ok, on: {card_shown: scout}, after_s: 2, say: "confirm"}
  - {id: ovw,      t: 40,  say: "drone two overwatch my position radius one five zero"}
  - {id: ovw_ok,   on: {card_shown: ovw}, after_s: 2, say: "confirm"}
  - {id: orb2,     t: 60,  say: "drone one orbit nai two"}            # never confirmed → timeout case
  - {id: dism,     on: {alert_shown: {gt_entity: deer-1}}, after_s: 3, say: "dismiss"}
  - {id: watch,    on: {alert_shown: {gt_entity: veh-7}},  after_s: 3, say: "watch"}
  - {id: mark,     on: {event: watch}, after_s: 3, say: "mark"}
  - {id: jam,      t: 300, jam: {duration_s: 25, links: ["mavlink:drone2", "tak:*"]}}
  - {id: atk,      t: 340, say: "drone one attack the vehicle"}
  - {id: stop,     t: 350, touch: triple_tap}
expect:
  - {after: scout, within_s: 5,  proposal: {steps: [takeoff, search], state: dispatched}}
  - {after: scout, within_s: 60, gt: {asset: drone1, mode: AUTO.MISSION, alt_agl_min: 54}}
  - {after: ovw,   within_s: 35, gt: {asset: drone2, mode: POSCTL.ORBIT}}
  - {after: orb2,  within_s: 13, proposal: {state: expired}, wire: {asset: drone1, class: MOTION, count: 0, window_s: 13}}
  - {during: {from: {event: ovw_ok, plus_s: 35}, to: {event: jam}},
     alerts: {tier: warning, count: 0}, cot: {near_friend_m: 15, count: 0}, assoc_friend: {min: 1}}
  - {after: {gt: entity_in_fov, asset: drone1, entity: deer-1, min_dwell_s: 3}, within_s: 5,
     alert: {kind: new_contact, cls: person, tier: caution}, cot: {type: a-u-G}}
  - {after: dism,  within_s: 1, cot: {gt_entity: deer-1, live: false}}
  - {during: {from: {event: dism}, to: end}, alerts: {gt_entity: deer-1, count: 0}}
  - {after: {gt: entity_in_fov, asset: drone1, entity: veh-7, min_dwell_s: 3}, within_s: 5,
     alert: {kind: new_contact, cls: vehicle, tier: caution, shown: true}, cot: {type: a-u-G-E-V}}
  - {after: mark,  within_s: 2,  cot: {gt_entity: veh-7, how: h-e}}
  - {after: jam,   within_s: 5,  tak: {link: lost}}
  - {after: jam,   within_s: 22, asset: {id: drone2, link: lost}, gt: {asset: drone2, mode: AUTO.RTL}}
  - {after: {event: jam, plus_s: 25}, within_s: 5, tak: {link: ok},
     router_log: {queued_min: 5, flushed: true, order_preserved: true, original_time: true}}
  - {after: atk,   within_s: 2,  intent: {result: rejected}, wire: {class: MOTION, count: 0, window_s: 10}}
  - {after: stop,  within_s: 2,  gt: {asset: [drone1, drone2], mode: AUTO.LOITER}}
  - {global: {invariant_violations: 0}, cot: {type_prefix: a-h, count: 0}}
```

Kinematic sanity checks (all sim time):
- **D1:** confirm ≈ t33; climb 20 s; transit to the first leg (≈170 m) 17 s; 5 legs plus turns ≈1,770 m at 10 m/s ≈ 177 s. D1 passes deer-1 on leg 2 (≈ t120) and veh-7 on leg 4 (≈ t190), and finishes ≈ t250 in LOITER.
- **D2:** reaches POSCTL.ORBIT ≈ t63.
- **Jam:** D2 is `lost` at t320 and RTL begins. D2 is still airborne (descending) at t350, so the stop holds both drones.
- **Wall clock:** at `--speed 4` the 360 s scenario takes 90 s of wall time.

`demo_scout.yaml`, `demo_jam.yaml` (`COM_DL_LOSS_T: 8`) and the live `demo_live.yaml` (speed 1, real detector, video on) reuse this geometry. Replay appears only in `goal2_*.yaml` (C59), so CI never needs `data/`.

## 8. Ground-truth events and determinism

- `gt_events.jsonl` records:
  - `entity_spawn` / `entity_despawn`
  - `entity_in_fov{asset, entity, t_enter, t_exit, min_range, px_h_src, px_h_det}`
  - `jam_start` / `jam_end`
  - `asset_mode`
  - `battery`
- Truth is published on `sim.truth.*`. Only `bench/`, `tests/`, the scenario runner and `gt_detector` may import it, and a lint test enforces this.
- Determinism (C62): hash the mover output and the jam schedule, plus the in-process Mock stepped at dt 20 ms with scripted commands. Two runs with the same seed must give identical sha256. Socket runs use tolerances.
