# Interfaces spec (v1 wire protocol, PLAN v3)

Normative detail for [PLAN.md §2](../PLAN.md#2-interfaces). JSON Schema 2020-12 files in `schemas/v1/` are the source of truth (C27). Where this file and a schema disagree, fix the schema through WS-A. Decision IDs refer to [DECISIONS.md](../council/DECISIONS.md).

## 1. Conventions

- **Clock (C61).** The supervisor exports `EDITH_T0_NS` and `EDITH_SPEED`. Every process (companion, Mock, linkshaper, cameras, gt_detector, scenario runner, fake_glasses) reads time through `edith_common.clock.ScaledClock`: `now_ns = T0 + (wall_ns − T0) × speed`, so `ts_ms` stays epoch-like (C94). `ts_ms` is ScaledClock epoch ms on the sender, and the companion's clock is authoritative. Lockout and expiry are ScaledClock ms. `--assets px4` forces `--speed 1`. Glasses and emulator durations are wall ms, so the supervisor refuses `--emulator` or real glasses at `--speed` ≠ 1 (C94). Glasses never compare clocks: countdowns are `expires_ms − hud.ts_ms`, taken at receipt and run down on the glasses' monotonic clock.
- **Durations, not timestamps, cross the glasses link.** Input events carry `held_ms` and `duration_ms` (glasses-monotonic differences). The companion estimates press start as `t_recv − held_ms − rtt/2`.
- **Geo.** WGS-84 decimal degrees. `alt_msl_m`, `alt_agl_m`; `hae_m = alt_msl_m + N`, where N is a per-site geoid constant in the scenario (`origin.geoid_n_m`, ≈ −33 m at the Piatt County site, EGM96, UNVERIFIED). Bearings are degrees true, 0–360 clockwise. Sim internals use ENU metres from the origin. MGRS is used only for display and voice. The demo origin is 40.0700 N, 88.6300 W, 210 m MSL (PLAN §3.6) = MGRS `16TCK6100236799` (`edith_common.geo.SCENARIO_ORIGIN`). `to_mgrs` truncates; `from_mgrs` returns the cell centre.
- **Position error (C57).** `ce_m` is always the **CE90 radius** in metres. Filters use σ = ce_m / 2.146. CoT `ce` = ce_m. Whether CoT consumers read `ce` as CE90, CEP50 or 1σ is UNVERIFIED; CE90 is the conservative (larger) choice.
- **Versioning.** Additive fields are minor and must be ignored by older readers. A breaking change bumps `v`. Schemas allow additional properties; enums and types are strict. Fields marked `?` are optional and are omitted (never `null`) when absent; fields typed `x|null` are always present.
- **Schemas and fixtures (C27).** `schemas/v1/index.json` maps every type below to its schema file. Shared fixtures: `schemas/fixtures/{valid,invalid}/<type>/*.json` (each invalid fixture breaks exactly one rule, named in `_why`). Message fixtures are bodies; `envelope/` fixtures are whole wire messages.

## 2. Envelope and binary frames

```json
{ "v": 1, "type": "hud.state", "id": "uuid4", "ts_ms": 1795000000000,
  "src": "companion-01", "seq": 4182, "body": { } }
```
`seq` is monotonic per sender. Binary WS frame: `[u32 BE header_len][UTF-8 JSON header][payload]`. Header: `{stream: "audio.up"|"video.down/<asset_id>"|"video.crop/<alert_id>"|"video.up"|"audio.down", seq, ts_ms, codec: "pcm_s16le"|"jpeg"|"h264", w?, h?, sr?, ch?, frame_id?, preroll?: bool}`.

## 3. WebSocket messages (:7400 `/v1/ws`)

| Type | Dir | Rate | Body |
|---|---|---|---|
| `sys.hello` | ↔ | on connect | `role: glasses\|emulator\|fake\|companion`, `proto: [int]`, `token` (provisioned by adb intent extra, C76), `device{model, fingerprint, sdk_int}`, `display{win_w, win_h, eye_w, eye_h, eyes: sbs\|mono}` (measured window), `input{ptt: hold\|toggle\|bt_key, temple_confirm: bool}`, `caps{inference[], camera, tts}`. token/device/display/input/caps are required for client roles; the companion's reply is `{role: companion, proto}` |
| `sys.ping` / `sys.pong` | ↔ | 1 Hz | ping `t0_ms` (sender); pong echoes `t0_ms` and adds `t1_ms, t2_ms` (responder receive/send). RTT only; never used to compare clocks |
| `head.pose` | ↑ | 10 Hz | `yaw_deg, pitch_deg, roll_deg, heading_deg, heading_unc_deg, source: rv\|fused\|game_rv\|scripted` |
| `input.event` | ↑ | event | `kind: tap\|double_tap\|triple_tap\|slide_fwd\|slide_back\|slide_up\|slide_down\|ptt_down\|ptt_up\|two_finger_hold\|back\|bt_ptt_down\|bt_ptt_up`, `gesture_seq: int` (taps of one sequence share it; ≤300 ms between taps, C106), `held_ms?` (DOWN→emit; on `ptt_down` and `bt_ptt_down`), `duration_ms?` (on `two_finger_hold`), `pointer_count`, `ctx{proposal_id?, alert_id?}` (what was on screen at the first DOWN; required on `ptt_down`, `bt_ptt_down` and `two_finger_hold`, C101) |
| `voice.session.start` / `.stop` | ↑ | event | `session_id, trigger: ptt\|bt_ptt\|touch\|text`, `reason?` (`bt_ptt` matches the voice §5 press method) |
| `voice.text` | ↑ | event | `session_id, text`. Accepted only with `--allow-text-injection`, which the supervisor sets only with `--headless` (the gateway then refuses `glasses`/`emulator` hellos), and only inside a PTT window; the text becomes the session final, `asr.engine=text` (C40, C87) |
| `voice.partial` / `voice.final` | ↓ | partial ≤2 Hz (C58) | `session_id, text, conf: float\|null` |
| `hud.state` | ↓ | on change ≤10 Hz + 2 Hz heartbeat | `HudState` (§4) |
| `hud.event` | ↑ | event | `kind: inset_open\|inset_close\|alert_shown\|alert_cleared\|card_shown\|card_cleared, ref, ts_ms`. **`card_shown` is required for any confirm (C48).** It is emitted once per proposal from the draw pass of the first frame containing the card, re-emitted after reconnect while visible, and followed by `card_cleared` on removal (C105). `alert_shown` scopes bare responses (C81); `alert_cleared` is sent when the card covers the banner, and `alert_shown` again when the card closes (C101) |
| `glasses.telemetry` | ↑ | 1 Hz | `battery_pct, current_ua, voltage_mv, temp_c, thermal_status, thermal_headroom, fps, decode_ms_p95, rtt_ms, usb_connected: bool`. `thermal_headroom` is `null` when the platform returns NaN |
| `perception.detections` | ↑ | per frame | `{detections: [Detection]}` (placement benchmark only; bodies are objects. The UDP 5800+i payload stays a bare `[Detection]` array, schema `udp.detections`) |
| binary `audio.up` | ↑ | 50 frames/s during PTT only | pcm_s16le 16 kHz mono, 20 ms. The first frames after `ptt_down` are the pre-roll buffer from finger DOWN (`preroll: true`, C46) |
| binary `video.down/<asset>` | ↓ | 10–15 fps while the inset is visible | JPEG 320×240 q≈70; boxes not burned in |
| binary `video.crop/<alert>` | ↓ | per alert | JPEG 96×72 |
| binary `video.up` | ↑ | ≤10 fps (bench) | JPEG 640×480 |
| binary `audio.down` | ↓ | TTS (P2) | pcm_s16le 16 kHz |

## 4. Core schemas

```
AssetState     asset_id, callsign ("DRONE 1"), chip ("D1"), kind: quad|fixed_wing|vtol|ugs,
               link{state: ok|degraded|lost, last_heard_ms}, pos{lat, lon, alt_msl_m, alt_agl_m},
               att{roll_deg, pitch_deg, yaw_deg}, vel_ned{n_mps, e_mps, d_mps}, battery_pct,
               mode (PX4 name, e.g. AUTO.LOITER, POSCTL.ORBIT), armed, landed,
               failsafe{dll_action: hold|return|land|none, dll_countdown_s?},
               task{proposal_id?, steps?, step_idx?, status?}, sensors[{sensor_id, kind: eo|ir, hfov_deg, w, h, stream}]
FrameMeta      (UDP 5700+i) frame_id, t_capture_ms, t_sim_ms, asset_id,
               pose_est{lat, lon, alt_msl_m, alt_agl_m, roll_deg, pitch_deg, yaw_deg},   # true pose + nav_noise (C57)
               rel_alt_m (from GLOBAL_POSITION_INT.relative_alt), gimbal{mode: stabilized|body_fixed, pitch_deg, yaw_deg},
               K{fx, fy, cx, cy}, w, h, pose_source: sidecar|telemetry_interp, video: on|off
FrameTruth     (sim-internal; runs/<ts>/frame_truth_<i>.jsonl; never sent to the companion)
               frame_id, t_sim_ms, asset_id, objects[{entity_id, cls, bbox_norm, visible_frac, range_m, lat, lon}]
Detection      det_id, frame_id, frame_ts_ms, source{asset_id, sensor_id}, cls: person|vehicle|other,
               conf, bbox_norm[x, y, w, h], tile?, det_px_h (height at detector input, C58),
               infer{placement: companion|glasses|offload, model (gt for gt_detector), model_sha, t_capture_ms, t_start_ms, t_end_ms}
Track          track_id, alias ("contact 3"), cls, conf, hits, window, geo{lat, lon, ce_m}, vel{e_mps, n_mps},
               geo_quality: metric|pseudo (pseudo = replay, never contact_close, C70),
               first_seen_ms, last_seen_ms, source_assets[], status: new|confirmed|watched|marked|dismissed|lost,
               novelty, affiliation: unknown|friend|neutral|hostile, affiliation_src: machine|human,  # I6
               assoc_friend_uid?: str (C52, C98; sticky; set ⇒ no alert, no CoT, drawn as the friend), cot_uid, det_ids[-8:]
Alert          alert_id, tier: advisory|caution|warning, score, kind: new_contact|contact_close|link_lost|
               battery_low|geofence|teammate_stale|task_status|tak_link,
               label: PERSON|VEHICLE|GEOFENCE|TEAMMATE|D<n> LINK|TAK LINK|D<n> BATT|D<n> TASK|<n> NEW (enum, each ≤160 px at 28 px, C102),
               ref{track_id|asset_id|uid} (exactly one),
               bearing_deg: float|null, range_m: float|null (null for kinds with no bearing), ce_m?, row2, actions[watch|mark|dismiss|say_again|details], gesture_dismiss: bool (false on WARNING),
               signals{conf, novelty, proximity, closing, recency, class_w, aoi}, created_ms, expires_ms
CommandIntent  intent_id, session_id, utterance{text, asr_conf: float|null, nbest[], engine, model_sha, norm_profile: spoken|written},
               heading_snapshot_deg, operator_pos{lat, lon},
               parsed{kind: command|safety_stop|response|query|hud, verb?, asset_ref?: str|"all", stop_via?: grammar|spotting,
                      target?{kind: self|teammate|clock_range|grid|named|relative|track|area, uid?, clock?, range_m?, mgrs?, name?,
                              track_alias?, offset{dir, dist_m}?, size_m?}, params{alt_agl_m?, radius_m?, standoff_m?}},
               slots[{name, raw_tokens, value, conf}], parser{method: grammar|llm, conf}, result: ok|say_again|rejected, reject_reason?
CommandProposal proposal_id, intent_id, asset_id, steps[{verb, params}] (e.g. [takeoff, search] when landed, C09),
               resolved_target{lat, lon, alt_agl_m, mgrs, label, frozen_from_track?: track_id} (observe contact: frozen at confirm, C51),
               readback{rows[2], spoken}, checks[{name, pass, msg}], confirm_with[voice|touch_temple|touch_companion],
               nonce (companion-internal), created_ms, lockout_until_ms, expires_ms, card_shown_ms?,
               state: proposed|await_confirm|confirmed|dispatched|cancelled|expired|superseded|invalidated   # ends at dispatched (C64)
Confirmation   proposal_id, nonce, method, operator_id, ts_ms, press{ptt_down_recv_ms, held_ms, est_start_ms}?,
               asr{text_norm, conf: float|null, closed_grammar: str|null}?, duration_ms?
SafetyStop     stop_id, scope: all|<asset_id>, source: voice|voice_spotting|temple|bt|companion, ts_ms, asset_ids[],
               not_sent[{asset_id, reason: link_lost}], cancelled_tasks[]
Execution      exec_id, proposal_id|null (null ⇒ safety stop; stop_id then required), stop_id?, asset_id, step_idx,
               verb (allowlist verb, or `arm` for the arm step of a composed task),
               status: sent|accepted|rejected|in_progress|completed|failed|aborted, mav_result?, detail, ts_ms
Feedback       track_id, verb: watch|mark|dismiss|undo_dismiss|say_again|details|reclassify, affiliation? (required on reclassify), operator_id, method, alert_id, ts_ms
TeammatePosition uid, callsign, team, role, pos{lat, lon, hae_m}, course_deg, speed_mps, ts_ms, stale_ms, source: mesh|server|sim
HudState       seq, ts_ms, mode: day|night, declutter: full|min|warn, quiet,
               operator{lat, lon, heading_deg, heading_unc_deg},
               status{tak: ok|degraded|lost|off, gps: ok|sim|none, companion_battery_pct: float|null, data_age_ms, rec},
               assets[{asset_id, chip, mode_label, battery_pct, link, task_label, dll_countdown_s?}],
               minimap{range_m, entities[{ref, kind: self|friend|own_drone|unknown|hostile|point, marked: bool, rel_e_m, rel_n_m,
                       heading_deg?, label?, age_ms, stale}], clusters[{rel_e_m, rel_n_m, count}]},
               tape{carets[{ref, bearing_deg, style: friend|own_drone|unknown|warning|point}]},
               alert?{alert_id, tier, label, bearing_deg|null, range_m|null, ce_m|null, row2, row3, gesture_dismiss, shown_since_ms, flash_until_ms,
                      queue{count, warning, caution, advisory}},
               proposal?{proposal_id, rows[2], expires_in_ms, lockout_in_ms, confirm_with[],
                         state: await_confirm|lockout|sent|acked|no_ack|not_sent_timeout|cancelled},
               toast?{text, tier, until_in_ms}, undo?{alert_id, until_in_ms} (gesture dismiss pending, C47),
               inset?{stream, label, frame_age_ms, pinned, boxes[{alias, cls, bbox_norm}], crop_stream?},
               voice{state: idle|listening|processing|await_confirm|say_again|muted|offline, partial?, last_heard?}
```

Glasses compose banner row 1 as `label · <clock from bearing_deg − live heading> · ~<range rounded to max(50 m, ce_m)>`; the `~` is dropped at ≥1 km (C65). The rounding step is max(50 m, ce_m) taken up to a whole multiple of 50 m, and never shows less than one step; at ≥1 km the label is km with one decimal (`1.2 km`), rounded to max(100 m, step). Reference: `edith_common.geo.range_label` / `clock_from_bearing`. Kinds with no bearing (link, battery, task, TAK) render the label only, and row 1 is ≤470 px (C102). Rows 2/3 and the card rows come from the companion; the glasses append the `+N` queue to the right end of row 2 (≤400 px).

## 5. Ports (bind / send)

| Port | Proto | Binds | Sends to it | Use |
|---|---|---|---|---|
| 7400 | TCP/WS | companion | glasses, emulator, fake_glasses | `/v1/ws` |
| 7401 | TCP/HTTP | companion | browsers | `/healthz`, `/metrics`, god-view, `/ui/touch` |
| 14540+i | UDP | linkshaper | PX4 / Mock instance *i* | Vehicle → shaper (C62) |
| 14580+i | UDP | PX4 / Mock | linkshaper | Shaper → vehicle |
| 14740+i | UDP | companion (`udpin`) | linkshaper | Shaped vehicle ↔ companion, sysid 245 |
| 14640+i | UDP | `simd` (cameras + gt) | linkshaper (unimpaired copy) | True-pose tap |
| 14550 | UDP | must be free | — | `doctor` fails if bound (foreign GCS masks link loss) |
| 5600+i | UDP/RTP | companion FrameSource | camera *i* | H.264 + SEI frame_id (C60); SDP in `runs/<ts>/sdp/drone<i>.sdp` |
| 5700+i | UDP | companion | camera *i* | FrameMeta sidecar |
| 5800+i | UDP | companion `OffloadDetector` | gt_detector / P3 offload server | `[Detection]` JSON (C59) |
| 16968 / 16969 | UDP | companion / linkshaper `tak` | each other | mesh-emu CoT (C54) |
| 18088 | UDP | fake CoT router | linkshaper, teammate sim | mesh-emu fan-out to every peer that has sent to it; answers `t-x-c-t`; logs everything received |
| 18087 | TCP | fake CoT router | companion (`--tak tcp`) | TCP CoT + ping/pong |
| 239.2.3.1:6969 | UDP mcast | — | companion, ATAK | Field mesh (L7) |
| 8087 / 8089 / 8080 | TCP | OTS (optional) | companion | Plain / TLS (Phase 1) / web UI |

All test fixtures take `--port-base N` (default 0) added to every port so parallel runs don't collide (C77). mDNS `_edith._tcp` is P1 (C76).

## 6. Asset primitives and outbound classifier

`AssetAdapter`: `connect()`, `telemetry()`, `arm()`, `takeoff(alt_agl_m)`, `goto(lat, lon, alt_agl_m)`, `orbit(lat, lon, radius_m, alt_agl_m, vel_mps=5)`, `search(polygon, alt_agl_m, overlap=0.3)`, `follow(uid_stream, standoff_m)` (P2; friendly PLI only, C51), `hold()`, `rtl()`, `land()`, `configure(fence, gf_params)` (disarmed only; pushes only the fence and `GF_*` and reads them back; all other profile params are applied only by the sim launcher, C90). No generic `send_command`. Encodings and the search planner `plan_search` live in `edith_common.px4` (C62, C87), shared with MockVehicle and the lint.

**Outbound classifier (C50).** Every message the adapter emits passes `assets/outbound.py`:

| Class | Messages | Rule |
|---|---|---|
| MOTION | arm, `NAV_TAKEOFF`, `DO_REPOSITION`, `DO_ORBIT`, mission upload / clear / `MISSION_START` (any `MISSION_COUNT`, `MISSION_ITEM_INT`, `MISSION_CLEAR_ALL` of mission type), `NAV_RETURN_TO_LAUNCH`, `NAV_LAND`, `DO_CHANGE_SPEED`, `DO_SET_MODE` ≠ LOITER | Needs a DISPATCHED proposal with a valid Confirmation for this asset; after a SafetyStop at t_s, the Confirmation must be later than t_s (I7) |
| SAFE | `DO_SET_MODE` AUTO.LOITER (hold); retries of it | Always allowed; never queued for a `lost` asset |
| CONFIG | `HEARTBEAT` (1 Hz, `MAV_TYPE_GCS`), `SET_MESSAGE_INTERVAL`, `PARAM_SET`/`PARAM_REQUEST_READ`, fence upload (`MISSION_TYPE_FENCE`) | Heartbeat and intervals any time; params and fence only while disarmed |
| (anything else) | — | Dropped and logged as `outbound.blocked` |

**MAVLink mapping (PX4 v1.18; [probed] at tag v1.18.0-rc2 by sim r2).** Commands use `COMMAND_INT` with `MAV_FRAME_GLOBAL` (AMSL); mission items use `MAV_FRAME_GLOBAL_RELATIVE_ALT_INT`.

| Verb | MAVLink | Resulting mode | `completed` when |
|---|---|---|---|
| arm | 400 `COMPONENT_ARM_DISARM` p1=1 | — | armed (PX4 auto-disarms after `COM_DISARM_PRFLT` 10 s) |
| takeoff | 22 `NAV_TAKEOFF` (p7 AMSL) | AUTO.TAKEOFF → AUTO.LOITER | alt within ±1.5 m of target |
| goto | 192 `DO_REPOSITION` (p2=1) | AUTO.LOITER | within 5 m and in LOITER |
| orbit / observe(point or frozen contact) | 34 `DO_ORBIT` (radius, vel 5 m/s, yaw-to-centre) | **POSCTL.ORBIT** (main 3 / sub 1) | ongoing; `in_progress` |
| search(area) | Upload `[NAV_TAKEOFF if landed, plan_search waypoints…]` (16) via `MISSION_COUNT`/`MISSION_REQUEST_INT`/`MISSION_ITEM_INT`/`MISSION_ACK`, then 300 `MISSION_START`. Lawnmower spacing = centre-line ground width × 0.7 (≈68 m at 60 m AGL, −60°, HFOV 70°) | AUTO.MISSION → AUTO.LOITER at end | last `MISSION_ITEM_REACHED` |
| follow(friendly uid) (P2) | `DO_REPOSITION` re-issued ≤1 Hz at standoff ≥30 m | AUTO.LOITER | ongoing; cancelled by any stop (I7) |
| hold (safety stop) | 176 `DO_SET_MODE` custom main 4 / sub 3 | AUTO.LOITER | mode reached |
| rtl / land | 20 / 21 | AUTO.RTL → AUTO.LAND / AUTO.LAND | `ON_GROUND` and disarmed |
| speed | 178 `DO_CHANGE_SPEED` | — | ACK |
| fence | `MISSION_TYPE_FENCE`, items type 5001 with p1 = vertex count; `GF_ACTION 1`, `GF_MAX_VER_DIST 120` | — | ACK |

`custom_mode = main << 16 | sub << 24`. Composed landed tasks (C09): **search** = upload `[NAV_TAKEOFF, waypoints]` → arm → `MISSION_START`; **goto/orbit/observe** = arm → `NAV_TAKEOFF` immediately → send the verb once `IN_AIR` and alt ≥ 0.9 × target. Each step produces its own `Execution{step_idx}`. Liveness counts any inbound message: `degraded` after 1.5 s of silence, `lost` at the profile's `COM_DL_LOSS_T`. The vehicle then holds AUTO.LOITER for `COM_FAIL_ACT_T` before `NAV_DLL_ACT`; `dll_countdown_s = COM_DL_LOSS_T + COM_FAIL_ACT_T − silence` (C89).

## 7. CoT (TAK Protocol v0 XML out; v0 XML + v1 protobuf in)

| Entity | `type` | `how` | Rate / stale | uid |
|---|---|---|---|---|
| Self (VIKING 1-1) | `a-f-G-U-C` | `m-g` (`m-s` in sim) | 10 s / 120 s | `EDITH-<companion>-self` |
| Teammates (sim) | `a-f-G-U-C` | `m-s` | 2 s / 120 s (C98) | `EDITH-SIM-tm-<n>` |
| Own quadcopter | `a-f-A-M-H-Q` | `m-g` | 1 Hz / 30 s | `EDITH-<companion>-D<n>` |
| Machine vehicle | `a-u-G-E-V` | `m-f` (fused; UNVERIFIED against the CoT how taxonomy) | ≤1 Hz, ≥ every 30 s / 300 s | `EDITH-<companion>-trk-<track_id>` |
| Machine person | `a-u-G` | `m-f` | ≤1 Hz / 300 s | same |
| Human MARK | same `a-u-*` | `h-e` | / 900 s; never auto-deleted (C99) | same |
| Human reclassify (companion UI only) | `a-h-*` / `a-n-*` / `a-f-*` | `h-e` | / 900 s | same |
| Camera SPI | `b-m-p-s-p-i` | `m-g` | 1 Hz / 10 s | `EDITH-<companion>-D<n>-spi` |
| NAI / checkpoint | `b-m-p-w` (UNVERIFIED) | `h-e` | long | `EDITH-POINT-<name>` |
| Delete | `t-x-d-d` with `<link uid=… relation="none"/>` + `<__forcedelete/>` | `h-g-i-g-o` | once | target uid (C53) |
| Ping / pong | `t-x-c-t` / `t-x-c-t-r` | `h-g-i-g-o` | see link monitor | `EDITH-<companion>-ping` |

- **Retraction (C53, C99).**
  - DISMISS of a published machine track emits a delete within 1 s.
  - Loss deletes only **unmarked** `how=m-f` tracks. A track with `how=h-e` (MARKed) is never auto-deleted: on loss it is re-sent once as a last-known position (remarks `LKP <DTG>`) and keeps its 900 s stale.
  - ATAK-CIV handling of `t-x-d-d` is UNVERIFIED (week-1 LAN check); the fallback re-sends the uid with `stale = now`.
- **Dismiss disc gates CoT (C99).** The DISMISS suppression disc (15 m, same class, 10 min) also blocks CoT publication, so a dismissed object re-acquired under a new `track_id` is not re-published.
- **Friendly association (C52, C98).** Tracks with `assoc_friend_uid` are never published.
- **Sim markings (C55).** Every sim-sourced event's `remarks` starts with `EXERCISE`.
- **Scope guard.** `tak/` is the only CoT egress. It refuses `a-h-*` without `affiliation_src=human`, any type outside this table and any friend-associated track, and logs each refusal.
- **Inbound.** XML and TAK Protocol v1 mesh frames (`0xBF 0x01 0xBF` + protobuf) via `takproto` (Apache-2.0, optional extra), with one fixture each.

**Link monitor and outbox (C54).**

| Transport | Keepalive | `lost` when | `ok` when |
|---|---|---|---|
| `mesh-emu` (CI, sim, headless default) | companion → router `t-x-c-t` 1 Hz through linkshaper `tak` | no inbound packet (pong or CoT) for 3 s | any inbound packet |
| `tcp` (OTS / fake router) | `t-x-c-t` every 3 s | 2 consecutive missed `t-x-c-t-r` (OTS support UNVERIFIED) | a reply arrives |
| `mesh` (field multicast) | none possible | no inbound CoT from any peer for 12 s (config) | any peer CoT |

While `lost`, every outbound event goes to the SQLite outbox. PLI is compacted to the latest per uid, and track and alert events keep their original `time`. On recovery the outbox sends, in order: (1) every event sent during the `lost_after + 2 s` before detection (it may have been dropped unseen); (2) the queue; (3) the latest state of every live track, including MARKed LKPs (C99). Events whose `stale` has passed are dropped. CoT is idempotent on uid + time, so duplicates are harmless. Tests assert on the fake router's received log, never on the sender.
