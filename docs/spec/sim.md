# Simulation spec (PLAN v3)

This file holds the normative detail behind [PLAN.md §3.6](../PLAN.md#36-simulation). WS-D (Simon) owns it. The exceptions are `gt_detector`, which WS-E owns, the teammate CoT publisher, which WS-F owns, and `FakeGlasses`, which WS-B owns.

## 1. Shared vehicle profile (L15, C62, C90)

`sim/profiles/quad_sim.yaml` is the **single source** for vehicle behaviour:

- MockVehicle reads the file directly.
- **Only the sim's PX4 launcher applies profile params** (C90). It applies them **after boot**, reads every value back, and aborts on any mismatch. This step is needed because `PX4_SIM_SPEED_FACTOR` rewrites `COM_DL_LOSS_T` in rcS [probed].
- The companion's `configure()` pushes only the fence and `GF_*` keys, and D3a's read-back abort applies to those. `SIM_*` and the sim-tuned cruise therefore never reach a Phase 1 vehicle.
- `edith scenario lint` uses the profile for kinematic bounds.
- A scenario can override keys only through `profile_overrides`, which must be disclosed in the scenario header.

```yaml
# sim/profiles/quad_sim.yaml  — sim-tuned, disclosed (faster than PX4 defaults 1.5 / 5 m/s)
MPC_TKO_SPEED: 3.0        # m/s climb
MPC_XY_CRUISE: 10.0       # m/s
MPC_ACC_HOR: 3.0          # m/s² corner deceleration (PX4 default value UNVERIFIED); Mock + pre-run use trapezoidal corners (C91)
MIS_TAKEOFF_ALT: 60
RTL_RETURN_ALT: 60
MPC_LAND_SPEED: 0.7
NAV_DLL_ACT: 2            # Return (C12) [probed: 2 = Return_mode at v1.18.0-rc2]
COM_DL_LOSS_T: 20         # s; demo_live.yaml overrides to 8 (C78, C92, disclosed)
COM_FAIL_ACT_T: 5         # s delayed-hold before the failsafe action [probed default 5] (C89)
COM_DISARM_PRFLT: 10      # s auto-disarm if armed and not flying [probed]
COM_LOW_BAT_ACT: 0        # warn only (SITL default 3 [probed])
SIM_BAT_DRAIN: 1800       # s; SITL otherwise floors at 50% within 30 s [probed]
SIM_BAT_MIN_PCT: 10
GF_ACTION: 1
GF_MAX_VER_DIST: 120
orbit_vel_mps: 5          # companion-side DO_ORBIT velocity (not a PX4 param)
```

## 2. `edith_common.px4` (shared by Mock, the adapter and the lint, C62)

This module is owned by WS-D even though it sits under `common/`; that ownership is recorded in `docs/OWNERS.yaml`. It covers:

- **Identity:** heartbeat `autopilot=12`, `type=2`, sysid = instance + 1. The companion uses sysid 245.
- **Mode encoding:** `custom_mode = main<<16 | sub<<24`. The modes used are AUTO.TAKEOFF, AUTO.LOITER (4/3), AUTO.MISSION, AUTO.RTL, AUTO.LAND and **POSCTL.ORBIT (3/1)**.
- **Acknowledgements:** one `COMMAND_ACK` per command.
- **Mode transitions:**
  - `DO_REPOSITION` → LOITER.
  - Mission end → LOITER.
  - RTL → LAND → disarm.
- **Failsafe (C89, matches PX4 framework.cpp [probed]):**
  - The data-link-loss action runs only while armed and in air.
  - On a failsafe the vehicle goes to AUTO.LOITER for `COM_FAIL_ACT_T`, then takes the action (`NAV_DLL_ACT`).
  - The action survives link recovery. It is cleared only by a mode change or a disarm.
  - A mode command (e.g. the safety-stop hold) is accepted during the delay and during the action.
  - `AssetState.failsafe.dll_countdown_s = COM_DL_LOSS_T + COM_FAIL_ACT_T − silence_s`.
- **Search planner (C87):** `plan_search(polygon, alt_agl_m, hfov_deg, pitch_deg, overlap) → [waypoints]`. `AssetAdapter.search` and the lint pre-run both call it, so they fly the same lawnmower path. Spacing = centre-line ground width × (1 − overlap).
- **Mission protocol:** the `MISSION_COUNT` / `MISSION_REQUEST_INT` / `MISSION_ITEM_INT` / `MISSION_ACK` handshake. Fence items use type 5001.
- **Parameters:** byte-wise int32 `PARAM_SET` encoding.
- **`completed` definitions** for each verb, as listed in [interfaces.md §6](interfaces.md#6-asset-primitives-and-outbound-classifier).

**Contract suite:** `companion/tests/assets/contract/`, owned by WS-B.

- It is parametrized `--assets mock|px4`.
- It runs arm → takeoff → goto → orbit → search mission → hold → rtl → land, plus the composed landed + search case and the landed + orbit case.
- **DLL case (C89):** armed in air → silence → AUTO.LOITER for `COM_FAIL_ACT_T` → AUTO.RTL → link restored (still RTL) → hold accepted → AUTO.LOITER.
- `edith sim record-px4` captures a golden PX4 trace on any laptop: the mode sequence, the ACKs, the mission handshake and the DLL case, saved to `sim/traces/px4_1.18.json`. CI diffs Mock's trace against it.

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
- **Process clock:** every process runs on ScaledClock, `now = T0 + (wall − T0)·speed` ([interfaces §1](interfaces.md#1-conventions)).
- **Teammate sim (WS-F):** sends PLI every **2 s** in sim (field PLI stays 10 s, C26) (C98).

## 4. Cameras, video policy and frame sync (C59, C60)

- **Camera model:** `simd` renders a synthetic view (NAIP orthophoto homography plus metric sprites; teammates are drawn as person sprites, C52), or plays back replay clips.
  - **Basemap fallback (C93):** when `data/naip` is absent, simd uses a procedural basemap. D7 goldens use the procedural basemap, so CI never reads `data/`.
  - **Gimbal:** `gimbal.mode: stabilized` is the default. Pitch is relative to the horizon, yaw is relative to the body, and body roll and pitch are ignored. The optical frame is x-right, y-down, z-forward. The projector in `perception/geo.py` uses the same convention, tested in D8.
- **Virtual frames:** these run on sim time at the scenario's `fps`. Each one produces:
  - a `FrameMeta` sidecar on 5700+i, carrying `pose_est` = true pose + `nav_noise` {σ_rp 1°, σ_yaw 3°, σ_alt 1.5 m, timestamp skew U(0, 50 ms)}. σ_alt is also applied to `rel_alt_m`, and in stabilized mode σ_rp is applied to the reported gimbal horizon reference, so geo sees pitch and altitude error (C96).
  - a `FrameTruth` record in `runs/<ts>/frame_truth_<i>.jsonl`.
- **Encoded video:** this is `video: on|off|auto`. `auto` means off for `--headless --detector gt` and on otherwise.
  - **`off` means no pixels (C93):** simd produces FrameMeta and FrameTruth analytically, renders nothing and loads no basemap.
  - When on, the encoder uses libx264 `tune=zerolatency` with no B-frames, and its rate is **capped at 15 fps of wall-clock time** (frames are decimated at `--speed` >1).
  - Each access unit is preceded by an SEI `user_data_unregistered` NAL carrying `frame_id`. The companion parses it from the packet bytes before decoding.
  - Fallback: `pts = frame_id·90000/fps`, anchored on the first sidecar pair.
  - The supervisor writes `runs/<ts>/sdp/drone<i>.sdp`.
- **Replay feeds (C95):** replay frames are resized to 1280×720 and carry `geo_quality: pseudo`. The pseudo pose is for display only. The companion runs the same Kalman tracker with a low-confidence second pass, but in a **motion-compensated image plane**:
  - an inter-tick homography (ORB + RANSAC at 640×360, ECC as the fallback) warps the predictions;
  - matching uses pixel Mahalanobis with σ = 0.1·box diagonal + 4 px;
  - tracks reset at every splice boundary.
- **Tier B:** there is no sidecar. Pose comes from interpolating ATTITUDE and GLOBAL_POSITION_INT (`pose_source: telemetry_interp`).
- **gt_detector** (WS-E, `sim/edith_sim/gt_detector.py`):
  - It reads FrameTruth in-process.
  - It applies `pd`, `fa_per_h`, latency, bbox noise, scripted `confusions` (the planted false positive) and persistent `clutter` objects.
  - It emits `[Detection]` (`placement=offload, model=gt`) on UDP 5800+i at the camera's virtual rate, capped at 4 Hz. The companion scheduler subsamples according to its rate policy.
  - It writes `runs/<ts>/gt_dets_<i>.jsonl {det_id, entity_id|null}` for the alert-to-entity join (§5.1).
  - The companion never imports `edith_sim`. A lint test enforces this.

## 5. Scenario YAML v2

| Key | Meaning |
|---|---|
| `version: 2`, `seed` | Format version; one seed for mover, noise, gt |
| `max_speed` | Highest `--speed` the scenario may run at (default 4; `demo_live` 1). The lint evaluates bounds at this speed (§6) |
| `origin{lat, lon, alt_msl, geoid_n_m}` | ENU origin; geoid N for `hae` |
| `vehicle_profile`, `profile_overrides` | §1 |
| `basemap`, `ao`, `safety` | NAIP item (procedural if absent); AO polygon (= geofence, ENU m); safety limits (C38) |
| `video` | `on|off|auto` |
| `operator`, `teammates[]` | Timed paths `{t, e, n, heading?}`; teammates have `sprite` (rendered as persons) |
| `assets[]` | `id, callsign, instance, spawn{e,n}, camera{mode: synth|replay, w, h, hfov, pitch, gimbal, fps, clip?}` |
| `gazetteer[]` | `name, e, n, area_m?, aliases[]` (C66) |
| `entities[]` | `id, cls (vehicle|person|animal), sprite, path[] or loiter_radius_m` |
| `gt_detector` | `pd, fa_per_h, latency_ms, bbox_noise_px, rate_hz, confusions{entity: cls}, clutter[]` |
| `events[]` | `id` plus `t:` (absolute sim s) **or** `on:` (`card_shown: <event>`, `alert_shown: {gt_entity}`, `event: <id>`, or a GT anchor `gt: {asset_mode|entity_in_fov, …}`) with `after_s`; action `say` (tasking `say` events also carry `cmd{asset, steps, target}`, C87), `touch`, `jam{duration_s, links}`, `assert_hold` |
| `beats[]` | Live-demo only: `{id, cmd?, anchor, window{after, from_s, to_s}}`, checked by `lint --beats` (§6, C92) |
| `expect[]` | Anchored assertions (§6); a headless run exits non-zero if any fails |

### 5.1 Runner seams (C87)

The scenario runner (WS-D, `sim/edith_sim/runner/`) is the only thing that executes `say` and `touch`, and it resolves `alert_shown{gt_entity}` anchors.

- **Runner drives FakeGlasses.** The runner hosts `FakeGlasses` in-process through a WS-B API in `tools/edith_tools/fake_glasses.py`:
  - `say(text)` sends, in order: `input.event ptt_down{held_ms: 300, ctx from the last HudState}` → `voice.session.start{trigger: text}` → `voice.text{text}` → `ptt_up`. Durations are ScaledClock ms.
  - `touch(kind, duration_ms?)` sends one `input.event`.
  - `on_card_shown(cb)` and `on_alert_shown(cb)` (with `alert_id`) fire when FakeGlasses emits those `hud.event`s.
  - The supervisor passes `--allow-text-injection` **only with `--headless`**. With it set, the gateway refuses any `sys.hello` whose role is `glasses` or `emulator`.
  - The supervisor refuses `--emulator` or real glasses at `--speed` ≠ 1, because glasses durations are wall ms (C94).
- **Alert-to-entity join.** gt_detector (E) writes `gt_dets_<i>.jsonl {det_id, entity_id|null}`. The eventlog (B) records `alert.created{alert_id, track_id}` and `track.update{track_id, det_ids}`. The runner maps an alert to the GT entity holding the majority of its track's `det_id`s, reading the eventlog read-only. Post-hoc expects (`gt_entity`) use the same join. No truth enters the companion.
- **Shared planner.** The lint pre-run turns each tasking `say` into motion with its `cmd` and `edith_common.px4.plan_search`, the same planner the adapter calls. A D4 test asserts that the parser's output for every vignette `say` equals its `cmd`.

## 6. Anchored expects and scenario lint (L15, C63, C88)

Every expectation is relative to an anchor:
- `after: <event id>`
- `after: {gt: entity_in_fov, asset, entity, min_dwell_s}`
- `during: {from, to}` (`from`/`to` may carry `plus_s`)
- `global`

with `within_s`. Absolute `by_t` is not allowed. The predicates are:
- `proposal{steps, state}`
- `gt{asset, mode, alt_agl_min}` (vehicle-side truth)
- `asset{id, link, mode}` (the companion's view)
- `alert{kind, cls, tier, shown}`
- `alerts{tier|gt_entity, count}` (alerts created)
- `cot{type|gt_entity, how, live, near_friend_m, count}`. In a `during` window, `live: true` with no `count` must hold throughout; `count` counts distinct matching uids live at any instant
- `tak{link}`
- `router_log{enqueued_min, flushed_uids_include, flushed, order_preserved, original_time}`. `enqueued_min` counts outbox enqueues **before** PLI compaction (C97)
- `wire{asset?, class, count, window_s}`
- `intent{result}`
- `assoc_friend{min}`
- `invariant_violations`

**Lower bounds (C88).** An expect's lower bound (LB) is the first time its predicate holds in the **deterministic pre-run**. The pre-run steps the mover and an in-process Mock (dt 20 ms, trapezoidal corners) with each `say`'s `cmd` at 50×, computes `entity_in_fov` analytically, and models latency with this table. Compute latencies are wall seconds and are **multiplied by the lint speed** (`max_speed`). Profile kinematics, lockout, expiry and `after_s` are sim seconds.

| Predicate | LB (s = lint speed) |
|---|---|
| Confirm path (`proposal{state: dispatched}`) | s·L_card (0.5) + max(lockout 0.6, `after_s` of the confirm) + s·L_cmd (0.3) |
| `proposal{state: expired}` | s·L_card + 10 |
| Mode predicates (`gt{mode}`, `alt_agl_min`) | confirm path + arm 1 + 0.9·alt / `MPC_TKO_SPEED` (or `alt_agl_min` / `MPC_TKO_SPEED`). No path term: PX4 enters ORBIT on ACK, and orbit is sent at alt ≥0.9× (C09) |
| Position and `completed` predicates | mode bound + path / `MPC_XY_CRUISE` with `MPC_ACC_HOR` corners |
| Response, stop, rejected (`intent`, `cot{how: h-e}`, `cot{live: false}`, stop modes) | s·L_cmd |
| Alert after an `entity_in_fov` dwell | gt `latency_ms` + s·L_cmd |
| `asset{link: lost}` | `COM_DL_LOSS_T` |
| Failsafe mode (`gt{mode: AUTO.RTL}` after a jam) | `COM_DL_LOSS_T` + `COM_FAIL_ACT_T` |
| `tak{link: lost}` | 3 |
| `tak{link: ok}` after a window | 0 |

`./edith scenario lint <file>` fails when:

1. Any `within_s` is below its LB, or below LB + 2 s when LB > 0.
2. A GT anchor never occurs in the pre-run.
3. An event references an unknown id, an `expect` uses `by_t`, or a tasking `say` lacks `cmd`.
4. With `--beats`: any beat's anchor in the pre-run falls outside its window (C92).

A lint test commits a deliberately infeasible copy of the vignette and asserts that lint rejects it.

## 7. `scenarios/demo_vignette.yaml` (authored in D2)

Geometry (ENU m):

| Item | Position |
|---|---|
| Launch / CP 3 | (0, 0) |
| D1 | (0, 0) |
| D2 | (8, 0) |
| Operator VIKING 1-1 | (−20, −15) |
| VIKING 1-2 | walks `{t: 0, e: −120, n: 40} → {t: 360, e: −60, n: 100}` (0.24 m/s) |
| VIKING 1-3 | (90, −60) |
| NAI 1 | (0, 250); 300 m square; 5 lawnmower legs from `plan_search` |
| NAI 2 | (380, −120) |
| Vehicle veh-7 | Parked at (60, 300) until **t280**, then drives to (400, 600) |
| deer-1 | Animal at (−70, 220), `loiter_radius_m: 3`; gt confuses it as a person |
| Sub-threshold clutter | (120, 380), conf **0.20** (below track start 0.25) |

The teammates sit 100–125 m from the operator, inside the ground footprint of D2's 150 m overwatch orbit (75–141 m radius), so friendly association is exercised. The deer and the vehicle are more than 150 m from the operator, so they raise CAUTION, never WARNING. Friendly PLIs include self.

```yaml
max_speed: 4
events:
  - {id: scout,    t: 30,  say: "drone one scout nai one",
     cmd: {asset: drone1, steps: [takeoff, search], target: {named: NAI 1}}}
  - {id: scout_ok, on: {card_shown: scout}, after_s: 2, say: "confirm"}
  - {id: ovw,      t: 40,  say: "drone two overwatch my position radius one five zero",
     cmd: {asset: drone2, steps: [takeoff, observe], target: {self: true}, radius_m: 150}}
  - {id: ovw_ok,   on: {card_shown: ovw}, after_s: 2, say: "confirm"}
  - {id: orb2,     t: 60,  say: "drone one orbit nai two",                 # never confirmed → timeout case
     cmd: {asset: drone1, steps: [orbit], target: {named: NAI 2}}}
  - {id: dism,     on: {alert_shown: {gt_entity: deer-1}}, after_s: 3, say: "dismiss"}
  - {id: watch,    on: {alert_shown: {gt_entity: veh-7}},  after_s: 3, say: "watch"}
  - {id: mark,     on: {event: watch}, after_s: 3, say: "mark"}
  - {id: jam,      t: 300, jam: {duration_s: 25, links: ["mavlink:drone2", "tak:*"]}}
  - {id: atk,      t: 340, say: "drone one attack the vehicle"}
  - {id: stop,     t: 350, touch: triple_tap}
expect:
  - {after: scout, within_s: 8,  proposal: {steps: [takeoff, search], state: dispatched}}
  - {after: scout, within_s: 60, gt: {asset: drone1, mode: AUTO.MISSION, alt_agl_min: 54}}
  - {after: ovw,   within_s: 35, gt: {asset: drone2, mode: POSCTL.ORBIT}}
  - {after: orb2,  within_s: 15, proposal: {state: expired}, wire: {asset: drone1, class: MOTION, count: 0, window_s: 15}}
  - {during: {from: {event: ovw_ok, plus_s: 35}, to: {event: jam, plus_s: 30}},
     alerts: {tier: warning, count: 0}, cot: {near_friend_m: 15, count: 0}, assoc_friend: {min: 1}}
  - {after: {gt: entity_in_fov, asset: drone1, entity: deer-1, min_dwell_s: 3}, within_s: 5,
     alert: {kind: new_contact, cls: person, tier: caution}, cot: {type: a-u-G}}
  - {after: dism,  within_s: 4, cot: {gt_entity: deer-1, live: false}}
  - {during: {from: {event: dism}, to: end}, alerts: {gt_entity: deer-1, count: 0}}
  - {during: {from: {event: dism, plus_s: 4}, to: end}, cot: {gt_entity: deer-1, live: true, count: 0}}
  - {after: {gt: entity_in_fov, asset: drone1, entity: veh-7, min_dwell_s: 3}, within_s: 5,
     alert: {kind: new_contact, cls: vehicle, tier: caution, shown: true}, cot: {type: a-u-G-E-V}}
  - {after: mark,  within_s: 4,  cot: {gt_entity: veh-7, how: h-e}}
  - {during: {from: {event: mark, plus_s: 4}, to: end}, cot: {gt_entity: veh-7, how: h-e, live: true}}
  - {after: jam,   within_s: 5,  tak: {link: lost}}
  - {after: jam,   within_s: 22, asset: {id: drone2, link: lost}}
  - {after: jam,   within_s: 27, gt: {asset: drone2, mode: AUTO.RTL}}
  - {after: {event: jam, plus_s: 25}, within_s: 5, tak: {link: ok},
     router_log: {enqueued_min: 5, flushed_uids_include: [self, D1], flushed: true, order_preserved: true, original_time: true}}
  - {after: atk,   within_s: 4,  intent: {result: rejected}, wire: {class: MOTION, count: 0, window_s: 10}}
  - {after: stop,  within_s: 4,  gt: {asset: [drone1, drone2], mode: AUTO.LOITER}}
  - {global: {invariant_violations: 0}, cot: {type_prefix: a-h, count: 0}}
```

Lint bounds at speed 4 (§6, each +2 s): scout 5.2 → 8; AUTO.MISSION 24.2 → 60; ovw 24.2 → 35; orb2 12 → 15; dism, mark, atk, stop 1.2 → 4; link lost 20 → 22; RTL 25 → 27; TAK lost 3 → 5.

Kinematic sanity checks (all sim time):
- **D1:** confirm ≈ t35; climb 20 s; transit to the first leg (≈170 m) ≈17 s; 5 legs plus turns ≈1,770 m at 10 m/s ≈177 s without corners. With trapezoidal corners at `MPC_ACC_HOR` (≈8 corners), D1 passes deer-1 on leg 2 (≈t125–140) and veh-7 on leg 4 (≈t225–235, still parked until t280), and finishes ≈t260–290 in LOITER.
- **D2:** reaches POSCTL.ORBIT ≈t65.
- **Jam:** D2 is `lost` at t320, holds in AUTO.LOITER until ≈t325, then enters AUTO.RTL. D2 is still airborne (descending) at t350, so the stop holds both drones.
- **Wall clock:** at `--speed 4` the 360 s scenario takes 90 s of wall time.

`demo_scout.yaml` and `demo_jam.yaml` are headless sub-scenarios that reuse this geometry. Replay appears only in `goal2_*.yaml` (C59), so CI never needs `data/`.

### 7.1 `scenarios/demo_live.yaml` (own layout, C92)

`max_speed: 1`, real detector, video on, `profile_overrides: {COM_DL_LOSS_T: 8}` (disclosed). The geometry is matched to the [PLAN §7.3](../PLAN.md#73-spring-2027) beat sheet, so the whole live demo runs in one file with no scenario switch:

| Item | Placement | Beat window (from the scout confirm, speed 1) |
|---|---|---|
| Launch, drones, operator, teammates, NAI 1 | As in the vignette | — |
| veh-7 | Parked at (−116, 160), on lawnmower leg 1 (flown north) | Alert ≤45 s |
| deer-1 (planted false positive) | (−48, 260), on leg 2, `loiter_radius_m: 3` | Alert 80–100 s, after the Alert beat |
| D2 | Tasked in the silent-touch beat (overwatch my position), so it is airborne for the jam | POSCTL.ORBIT before the jam |
| Jam | `{id: jam, on: {gt: asset_mode, asset: drone2, mode: POSCTL.ORBIT}, after_s: 20, jam: {duration_s: 25, links: [mavlink:drone2, tak:*]}}` | D2 `lost` ≤8 s and AUTO.RTL ≤13 s after jam start |

`edith scenario lint --beats scenarios/demo_live.yaml` checks each beat's GT anchor in the deterministic pre-run against its window. Owner Simon; due at the W7 G3 gate.

## 8. Ground-truth events and determinism

- `gt_events.jsonl` records:
  - `entity_spawn` / `entity_despawn`
  - `entity_in_fov{asset, entity, t_enter, t_exit, min_range, px_h_src, px_h_det}`
  - `jam_start` / `jam_end`
  - `asset_mode`
  - `battery`
- Truth is published on `sim.truth.*`. Only `bench/`, `tests/`, the scenario runner and `gt_detector` may import it, and a lint test enforces this.
- Determinism (C62): hash the mover output and the jam schedule, plus the in-process Mock stepped at dt 20 ms with scripted commands. Two runs with the same seed must give identical sha256. Socket runs use tolerances.
