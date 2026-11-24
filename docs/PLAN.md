# E.D.I.T.H. — Phase 0 Plan (v1)

Status: v1, merged by the plan editor from the eight round-1 proposals ([architect](council/r1/architect.md), [defense_sme](council/r1/defense_sme.md), [hud](council/r1/hud.md), [ml](council/r1/ml.md), [voice](council/r1/voice.md), [sim](council/r1/sim.md), [platform](council/r1/platform.md), [pm](council/r1/pm.md)) and the lead's binding rulings. Every conflict resolution is in [DECISIONS.md](council/DECISIONS.md) (IDs `L*` = lead ruling, `C*` = council resolution). Date: 2026-11-23.

Tags: **UNVERIFIED** = not yet confirmed (usually a device fact for day one). **[probed]** = measured in this workspace by a council member.

---

## 0. Summary and goals

E.D.I.T.H. is a voice-first operator layer. The RayNeo X3 Pro glasses are a thin client (screen, ears, eyes; never the brain). A pure-Python companion service (laptop in Phase 0, Android phone or ARM box in Phase 1) owns all state: world model, voice→intent, safety gate and confirmation state machine, MAVLink asset control, edge perception on drone video, alert ranking, the TAK/CoT bridge and store-and-forward sync. Drones are simulated only: Tier 0 MAVLink mock for CI, Tier A PX4 SIH + ground-truthed synthetic/replay camera (default), Tier B Gazebo on a GPU laptop. Detections are always published as **unknown**; only a human reclassifies. Every asset command needs read-back + explicit confirm, except the HOLD/ABORT safety stop, which only removes motion (L1). No weapons/targeting/engagement, no face or biometric ID, no real flights (L10). Everything runs offline.

| Goal (deck slide 7) | Numeric target (pre-registered) | Primary evidence |
|---|---|---|
| **G1** One operator directs a drone by voice from the glasses | Intent success ≥90% at 85 dB(A) through the glasses' mics. p95 end-of-speech→read-back ≤1.5 s (hard ceiling 2.5 s). Confirm→command sent ≤500 ms. **0 executions without confirmation** (safety stop excepted) across the adversarial suite (10,000 non-confirm utterances) and ≥2 h of replayed chatter. Confident-wrong proposals ≤0.5% at 10 dB SNR. | `bench goal1` noise curve; live demo at 85 dB(A); audit log |
| **G2** AI filtering cuts how much video the operator must watch | Watch reduction WR = 1 − AFS_E/AFS_B0 **≥80% at system event recall ≥90%**. False alerts ≤6/h per drone. Median time-to-detection ≤3 s. Geolocation CEP90 ≤30 m at 60 m AGL (sim). | `bench goal2` on replayed real aerial clips with bootstrap CIs |
| **G3** HUD stays readable and safe under stress | Alert response ≥20% faster than the same software on a chest-mounted phone (or an honestly reported null). SAGAT non-inferior within 5 points. NASA-TLX no higher. **0 accidental confirms in ≥180 lure trials**. Banner legible within 2 s in ≥95% of trials. Persistent lit-pixel ratio (APL) ≤13%. | N=18 within-subject study (IRB), golden-PNG lints |
| **G4** Cost model and roadmap to a real product | A sourced per-kit BOM (full kit and lite kit) and unit economics, with every number cited or marked UNVERIFIED. A Phase 1–3 roadmap with gates. | `docs/cost/model.csv` + `tools/cost_model.py`; §8 |

Targets sources: G1 [pm §1.6](council/r1/pm.md), [voice §3](council/r1/voice.md); G2 [ml §1.4](council/r1/ml.md); G3 [hud §5](council/r1/hud.md); G4 [pm §1.7](council/r1/pm.md).

---

## 1. Architecture

### 1.1 Layers and components

| Layer (deck slide 14) | Phase 0 realization | Owns |
|---|---|---|
| 1 Glasses · interface | Kotlin Android app on the RayNeo X3 Pro (`rayneo` flavor), or any Android phone (`generic`), or the desktop emulator | Rendering `HudState` and applying head-relative transforms locally (tape, heading-up map, conformal caret, clock wording). Capture of mic, IMU and (benchmark only) camera. Temple input. Staleness display. **No mission logic, and no mission data at rest.** |
| 2 Companion · compute | `edith_companion` (Python 3.13, asyncio) on a laptop | World model, voice pipeline, parser, safety gate, proposal state machine, asset adapters, perception, alert ranker, HUD policy, TAK bridge, outbox, event log, touch-fallback web UI |
| 3 Mesh · network | LAN Wi-Fi on a travel router. CoT over UDP multicast 239.2.3.1:6969. OpenTAKServer is optional (L7). | Team picture, store-and-forward after jamming |
| 4 Assets | PX4 SIH ×2 (Tier A) or MockVehicle (Tier 0) behind `AssetAdapter`; synthetic/replay cameras | Flight behavior, failsafes, video |

The design rule ([architect §1.1](council/r1/architect.md)) is that **policy lives on the companion and layout lives on the glasses**. The companion decides *what* is shown: one alert, the card, whether the inset is visible, which entities appear. The glasses decide *where the pixels go*. Policy is therefore unit-testable in Python, and the renderer stays dumb and portable to trusted hardware.

### 1.2 Diagram

```
                         ┌───────────────────────── Glasses (RayNeo X3 Pro / phone / emulator) ─────────────────────────┐
                         │ hud-core renderer (Compose DrawScope) ── StereoCompositor (SBS 2×640×480 | MONO)              │
                         │ PoseSource(3DoF heading) · InputSource(temple) · MicSource(16k PCM) · CameraSource(bench)      │
                         └──────────────▲───────────────────────────────┬────────────────────────────────────────────────┘
                     hud.state ≤10 Hz   │ video.down JPEG 320×240        │ head.pose 10 Hz · input.event · audio.up (PTT only)
                     voice.partial      │ 10–15 fps (inset visible)      │ sys.ping 1 Hz · glasses.telemetry 1 Hz · hud.event
                                        │        WebSocket :7400  (JSON text frames + binary frames)
┌───────────────────────────────────────┴────────────────────────────────▼────────────────────────────────────────────────┐
│ Companion (edith_companion, laptop)                                                                                     │
│  gateway ─ voice(VAD→ASR→normalize→Lark parse→resolve) ─ safety gate ─ proposals FSM ─ assets(AssetAdapter)              │
│     │                                                                         ▲            │ pymavlink                    │
│  hud projector ◄─ alerts(ranker) ◄─ perception(FrameSource→Detector→Tracker→Geo→Fusion)     │                              │
│     │                     ▲                                  ▲ RTP H.264 :5600+i            │ MAVLink :14740+i              │
│  eventlog(SQLite WAL)   tak(CoT build, scope guard, outbox) ─┼──── UDP mcast 239.2.3.1:6969 ─┼─► ATAK-CIV phone / TOC      │
│  http :7401 (/healthz, god-view, /ui/touch)                  │ pose sidecar :5700+i          │   (opt. OpenTAKServer :8087)│
└──────────────────────────────────────────────────────────────┼──────────────────────────────┼─────────────────────────────┘
                                                               │                              │
┌────────────────────────────── Sim (edith_sim) ───────────────┴──────────────────────────────┴─────────────────────────────┐
│ scenario runner (seeded clock) ─ entity mover ─ teammate CoT sim ─ GT logger (sim.truth.*, bench/tests only)              │
│ synthetic camera (NAIP ortho + sprites) | replay camera ─► RTP 5600+i + sidecar 5700+i                                     │
│ linkshaper (UDP proxy, jam windows) ◄──► PX4 SIH ×N (:14540+i)  or  MockVehicle ×N                                          │
└───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 1.3 Demo topology

| Box | Runs | Network |
|---|---|---|
| Demo laptop (Linux; macOS/WSL for dev) | companion, PX4 SIH ×2 (or Mock), synthetic cameras ×2, linkshaper, teammate sim, scenario runner; god-view on the projector | Wired or 5 GHz to the travel router |
| RayNeo X3 Pro | `app-android` `rayneo` flavor | 5 GHz Wi-Fi; mDNS `_edith._tcp` with manual-IP override |
| ATAK-CIV Android phone | Stock ATAK-CIV, mesh SA on, mirrored to the projector | Same Wi-Fi (multicast) |
| Optional TOC laptop | OpenTAKServer or WinTAK, plus the OTS web map | TCP 8087 |
| Optional GPU laptop | Tier B Gazebo | Its RTP 5600+i replaces the synthetic camera |
| Travel router (~$35) | No internet. A phone hotspot is the field fallback. | Venue Wi-Fi is never used ([platform §1.3](council/r1/platform.md)) |

### 1.4 Core loops

| Loop | Flow | Budget |
|---|---|---|
| **1 Voice → confirm → drone** | Hold right temple ≥300 ms → `input.event{ptt_down}` → `audio.up` streams → release + 150 ms tail → VAD trim, streaming ASR final (partials on HUD) → normalizer + Lark parse → resolver (heading snapshot at PTT release, MGRS, gazetteer) → safety gate → `CommandProposal` → card in `hud.state.proposal` → 600 ms lockout (longer while TTS plays) → second press "CONFIRM" alone, temple two-finger hold ≥1 s, or companion `/ui/touch` hold → `Confirmation` → gate re-check → `Execution{sent}` → MAVLink → `COMMAND_ACK` → `accepted` → telemetry → `completed`. **Safety stop:** one utterance (HOLD/ABORT/STOP), temple triple-tap or companion HOLD ALL sends hold (AUTO.LOITER) immediately and cancels any pending proposal (L1) | Card ≤500 ms p50 / ≤1.5 s p95 after end of speech; confirm→sent ≤500 ms; stop ≤500 ms |
| **2 Video → detection → alert → HUD/TAK** | 1280×720 H.264 on RTP 5600+i + pose sidecar 5700+i → latest-frame `FrameSource` → scheduler 2 Hz/feed (4 Hz tasked, 1 Hz after 30 s with no tracks) → YOLOX-Tiny on 2×2 tiles → ByteTrack-style tracker → confirmation (≥3 hits of 5, mean conf ≥ τ) → flat-earth geolocation with `ce_m` → cross-drone fusion and novelty → ranker → one banner in `hud.state.alert` + inset policy; in parallel CoT `a-u-*` to the mesh, remarks "machine · unconfirmed". Operator: WATCH (pin), MARK (human-confirmed, `how=h-e`), DISMISS (suppress) | TTD ≤3 s median; capture→alert ≤1.5 s p95 on a team laptop |
| **3 Jamming → degraded → resync** | Scenario `jam` → linkshaper drops both directions on `mavlink:drone2` and `tak:*` → 1.5 s without heartbeat: `link=degraded` → at `COM_DL_LOSS_T` (20 s): `lost`, PX4 runs `NAV_DLL_ACT`=Return (C12) → HUD greys the D2 chip, "D2 LINK LOST · RTL 0:12", CAUTION alert, any D2 proposal invalidated → CoT outbox (SQLite) queues, PLI compacted to latest per uid, track/alert events keep original `time` → window ends → heartbeat back, `link=ok` → outbox flushes in order, HUD clears staleness | `ok` ≤2 s after window; flush order 100% preserved |

**Glasses↔companion loss** is separate: the glasses keep the last snapshot, grey it after 3 s and show "COMPANION LOST — LOCAL ONLY" with a live tape; the companion expires any pending proposal; reconnect is `sys.hello` then a full snapshot. Commands never queue across disconnects.

---

## 2. Interfaces

### 2.1 Conventions
- **Time:** `ts_ms` is Unix epoch milliseconds on the sender's clock, and the companion clock is authoritative. Sim time travels separately as `t_sim_ms`. Glasses↔companion offset is estimated by min-RTT/2 over `sys.ping`. Every companion timer uses an injected `Clock`, so timeouts scale correctly under `--speed`.
- **Geo:** WGS-84 lat/lon in decimal degrees. `alt_msl_m`, `alt_agl_m`, and `hae_m` (CoT only). Bearings and headings are degrees true, 0–360 clockwise. Speeds in m/s. Sim internals use ENU metres from the scenario origin. **MGRS is used for display and voice only** (it truncates), via one `edith_common.geo` module ([sim §1.7](council/r1/sim.md)). Units are metric throughout (L2).
- **Versioning:** JSON Schema 2020-12 files in `schemas/v1/` are the source of truth. Python (pydantic) and Kotlin (kotlinx.serialization) models are hand-written and checked against shared fixtures (C27). Additive fields are minor and must be ignored by older readers. A breaking change bumps `v`.

### 2.2 Envelope and binary frames

```json
{ "v": 1, "type": "hud.state", "id": "uuid4", "ts_ms": 1795000000000,
  "src": "companion-01", "seq": 4182, "body": { } }
```
`seq` is monotonic per sender. Binary WS frame layout: `[u32 big-endian header_len][UTF-8 JSON header][payload]`. Header fields: `{stream: "audio.up"|"video.down/<asset_id>"|"video.crop/<alert_id>"|"video.up"|"audio.down", seq, ts_ms, codec: "pcm_s16le"|"jpeg"|"h264", w?, h?, sr?, ch?, frame_id?}`.

### 2.3 Message types (WS :7400)

| Type | Dir | Rate | Body (fields: type, unit) |
|---|---|---|---|
| `sys.hello` | ↔ | on connect | `role: glasses\|emulator\|fake`, `proto: [int]`, `token: str` (per-run pairing), `device{model, fingerprint, sdk_int}`, `display{eye_w:640, eye_h:480, eyes: sbs\|mono}`, `input{ptt: hold\|toggle}`, `caps{inference:[companion\|glasses\|offload], camera: bool, tts: bool}` |
| `sys.ping` / `sys.pong` | ↔ | 1 Hz | `t0_ms`, `t1_ms`, `t2_ms` |
| `head.pose` | ↑ | 10 Hz | `yaw_deg, pitch_deg, roll_deg, heading_deg, heading_unc_deg, source: rv\|fused\|game_rv\|scripted` |
| `input.event` | ↑ | event | `kind: tap\|double_tap\|triple_tap\|slide_fwd\|slide_back\|slide_up\|slide_down\|ptt_down\|ptt_up\|two_finger_hold\|two_finger_tap\|back`, `t_mono_ms`, `duration_ms?`, `ctx{proposal_id?, alert_id?}` (what was on screen at the time) |
| `voice.session.start` / `.stop` | ↑ | event | `session_id, trigger: ptt\|touch\|text`, `reason?` |
| `voice.text` | ↑ | event | `session_id, text`. Test and emulator injection only; accepted only when `--allow-text-injection` is set |
| `voice.partial` / `voice.final` | ↓ | ≤5 Hz | `session_id, text, conf?` |
| `hud.state` | ↓ | on change ≤10 Hz + 2 Hz heartbeat | `HudState` (§2.4) |
| `hud.event` | ↑ | event | `kind: inset_open\|inset_close\|alert_shown\|alert_cleared\|card_shown\|card_cleared, ref, ts_ms` (required for AFS) |
| `glasses.telemetry` | ↑ | 1 Hz | `battery_pct, current_ua, voltage_mv, temp_c, thermal_status: int, thermal_headroom: float, fps, decode_ms_p95, rtt_ms` |
| `perception.detections` | ↑ | per frame | `[Detection]` (glasses placement, benchmark only) |
| binary `audio.up` | ↑ | 50 frames/s during PTT only | pcm_s16le, 16 kHz, mono, 20 ms = 640 B |
| binary `video.down/<asset>` | ↓ | 10–15 fps while inset visible | JPEG 320×240 q≈70 (~1.5–2.5 Mbit/s); boxes are **not** burned in |
| binary `video.crop/<alert>` | ↓ | per alert | JPEG 96×72 |
| binary `video.up` | ↑ | ≤10 fps (bench) | JPEG 640×480 |
| binary `audio.down` | ↓ | TTS (P2) | pcm_s16le 16 kHz |

Glasses send **raw input events**. The companion maps them to actions using the displayed `ctx`, so a stale tap cannot confirm a newer card (C15).

### 2.4 Core schemas

```
AssetState     asset_id: str, callsign: str ("DRONE 1"), chip: str ("D1"), kind: quad|fixed_wing|vtol|ugs,
               link{state: ok|degraded|lost, last_heard_ms: int}, pos{lat, lon, alt_msl_m, alt_agl_m},
               att{roll_deg, pitch_deg, yaw_deg}, vel_ned{n_mps, e_mps, d_mps}, battery_pct: float,
               mode: str (PX4 mode name), armed: bool, landed: bool,
               failsafe{dll_action: hold|return|land|none, dll_countdown_s?: float},
               task{proposal_id?, verb?, status?}, sensors[{sensor_id, kind: eo|ir, hfov_deg, w, h, stream: url}]
FrameMeta      (UDP 5700+i sidecar) frame_id: int, pts: int, t_capture_ms, t_sim_ms, asset_id,
               pose{lat, lon, alt_msl_m, alt_agl_m}, att{roll_deg, pitch_deg, yaw_deg},
               gimbal{pitch_deg, yaw_deg}, K{fx, fy, cx, cy}, w, h          # pose AT EXPOSURE
Detection      det_id, frame_id, frame_ts_ms, source{asset_id, sensor_id}, cls: person|vehicle|other,
               conf: 0..1, bbox_norm[x, y, w, h], tile?: int,
               infer{placement: companion|glasses|offload, model, model_sha, t_capture_ms, t_start_ms, t_end_ms}
Track          track_id ("contact 3" speakable alias: alias), cls, conf, hits: int, window: int,
               geo{lat, lon, ce_m}, vel{e_mps, n_mps}?, first_seen_ms, last_seen_ms, source_assets[str],
               status: new|confirmed|watched|marked|dismissed|lost, novelty: 0..1,
               affiliation: unknown|friend|neutral|hostile, affiliation_src: machine|human,  # machine ⇒ unknown (invariant)
               det_ids[-8:]
Alert          alert_id, tier: advisory|caution|warning, score: 0..1, kind: new_contact|contact_close|
               link_lost|battery_low|geofence|teammate_stale|task_status, label ("VEHICLE"),
               ref{track_id|asset_id|uid}, bearing_deg, range_m, ce_m?, row2, actions[watch|mark|dismiss|say_again|details],
               signals{conf, novelty, proximity, closing, recency, class_w, aoi}, created_ms, expires_ms
CommandIntent  intent_id, session_id, utterance{text, asr_conf, nbest[{text, conf}], engine, model_sha},
               heading_snapshot_deg, operator_pos{lat, lon},
               parsed{kind: command|safety_stop|response|query|hud, verb?, asset_ref?: str|"all",
                      target?{kind: self|clock_range|grid|named|relative|track|area, clock?, range_m?, mgrs?, name?,
                              track_alias?, offset{dir, dist_m}?, size_m?},
                      params{alt_agl_m?, radius_m?, standoff_m?}},
               slots[{name, raw_tokens, value, conf}], parser{method: grammar|llm, conf},
               result: ok|say_again|rejected, reject_reason?
CommandProposal proposal_id, intent_id, asset_id, steps[{verb, params}] (e.g. [takeoff, search] when landed),
               resolved_target{lat, lon, alt_agl_m, mgrs, label}, readback{text, spoken},
               checks[{name, pass: bool, msg}], confirm_with[voice|touch_temple|touch_companion],
               nonce (companion-internal; never sent to glasses), created_ms, lockout_until_ms, expires_ms,
               state: proposed|await_confirm|confirmed|dispatched|cancelled|expired|superseded|invalidated
Confirmation   proposal_id, nonce, method: voice|touch_temple|touch_companion, operator_id, ts_ms,
               asr{text, conf, closed_grammar_agree: bool}?
SafetyStop     stop_id, scope: all|<asset_id>, source: voice|temple|companion, ts_ms, asset_ids[]
Execution      exec_id, proposal_id|null (null ⇒ safety stop), stop_id?, asset_id, verb,
               status: sent|accepted|rejected|in_progress|completed|failed|aborted, mav_result?: int, detail, ts_ms
Feedback       track_id, verb: watch|mark|dismiss|say_again|details|reclassify, affiliation?, operator_id, method, ts_ms
TeammatePosition uid, callsign, team, role, pos{lat, lon, hae_m}, course_deg, speed_mps, ts_ms, stale_ms, source: mesh|server|sim
HudState       seq, ts_ms, mode: day|night, declutter: full|min|warn, quiet: bool,
               operator{lat, lon, heading_deg, heading_unc_deg},
               status{tak: ok|degraded|lost|off, gps: ok|sim|none, companion_battery_pct, data_age_ms, rec: bool},
               assets[{asset_id, chip, mode_label, battery_pct, link, task_label, dll_countdown_s?}],
               minimap{range_m, entities[{ref, kind: self|friend|own_drone|unknown|hostile|point, rel_e_m, rel_n_m,
                       heading_deg?, label?, age_ms, stale: bool}], clusters[{rel_e_m, rel_n_m, count}]},
               tape{carets[{ref, bearing_deg, style}]},
               alert?{alert_id, tier, label, bearing_deg, range_m, row2, row3, shown_since_ms, flash_until_ms,
                      queue{count, warning, caution, advisory}},
               proposal?{proposal_id, rows[str], expires_ms, lockout_until_ms, hint, state},
               toast?{text, tier, until_ms},
               inset?{stream, label, frame_age_ms, pinned: bool, boxes[{alias, cls, bbox_norm}], crop_stream?},
               voice{state: idle|listening|processing|readback|await_confirm|say_again|muted|offline, partial?, last_heard?}
```

Glasses-side composition: banner row 1 is built on the glasses as `label · <clock from bearing_deg − live heading> · ~<range rounded to max(50 m, ce_m)>` so it updates at the head-pose rate. Rows 2 and 3 come from the companion ([hud §1.5](council/r1/hud.md)).

**Structural verb allowlist** ([architect §1.3](council/r1/architect.md)): `takeoff, goto, orbit, observe, search, follow, hold, rtl, land`. No enum value, field or adapter method exists for weapons, payload release or countermeasures. `follow` exists in the schema but is a stretch goal (L8).

### 2.5 Ports and rates

| Port | Proto | Use |
|---|---|---|
| 7400 | TCP/WS | Glasses, emulator and fake_glasses ↔ companion (`/v1/ws`) |
| 7401 | TCP/HTTP | `/healthz`, `/metrics`, god-view `/`, touch fallback `/ui/touch` |
| 14540+i | UDP | PX4 instance *i* API link (PX4 binds 14580+i) [probed] |
| 14740+i | UDP | Companion MAVLink endpoint behind linkshaper (always in path; pass-through by default) |
| 14550 / 18570+i | UDP | GCS link. QGC must not run unless routed through linkshaper ([sim §1.5](council/r1/sim.md)) |
| 19410+i | UDP | SIH viewer (optional jMAVSim display) |
| 5600+i | UDP/RTP | Drone video H.264 (all tiers) |
| 5700+i | UDP | FrameMeta sidecar JSON |
| 239.2.3.1:6969 | UDP mcast | CoT mesh SA (default, L7) |
| 8087 / 8089 / 8080 | TCP | TAK server plaintext / TLS (Phase 1) / OTS web UI (optional) |
| 18087 | TCP | In-repo fake CoT router (tests only) |
| 5353 | mDNS | `_edith._tcp` discovery |

| Stream | Rate |
|---|---|
| MAVLink telemetry in | `GLOBAL_POSITION_INT`, `ATTITUDE` 10 Hz; `SYS_STATUS`/`BATTERY_STATUS` 1 Hz; `HEARTBEAT` 1 Hz |
| Companion GCS `HEARTBEAT` out | 1 Hz, `MAV_TYPE_GCS`. **Required**: PX4's data-link-loss failsafe watches it |
| Camera out | 1280×720 @ 15 fps in this workspace, 30 fps on laptops (C32) |
| Detector | 2 Hz/feed default, 4 Hz tasked, 1 Hz idle |
| CoT out | Self PLI every 10 s (stale 120 s); drones 1 Hz (stale 30 s); unknown contacts ≤1 Hz and ≥ every 30 s while live (stale 300 s); SPI 1 Hz (stale 10 s); human marks (stale 900 s) |

### 2.6 Asset primitives (`AssetAdapter` → MAVLink; pymavlink 2.4.50 primary, C01)

`AssetAdapter`: `connect()`, `telemetry() -> AsyncIterator[AssetState]`, `arm()`, `takeoff(alt_agl_m)`, `goto(lat, lon, alt_agl_m)`, `orbit(lat, lon, radius_m, alt_agl_m, vel_mps)`, `search(polygon, alt_agl_m, overlap)`, `follow(track_stream, standoff_m)` (P2), `hold()`, `rtl()`, `land()`, `upload_fence(polygon, alt_max_m)`. There is deliberately no generic `send_command`. MockVehicle implements the same MAVLink subset.

| Verb | MAVLink (PX4) [sim §1.3] | MAVSDK equivalent (only if the team switches, C01) |
|---|---|---|
| arm | `COMMAND_LONG` 400 `COMPONENT_ARM_DISARM` p1=1 | `action.arm` |
| takeoff | 22 `NAV_TAKEOFF` (p7 = AMSL) | `action.set_takeoff_altitude` + `action.takeoff` |
| goto | `COMMAND_INT` 192 `DO_REPOSITION` (p2=1, x/y = lat/lon·1e7, z AMSL); vehicle ends in Hold | `action.goto_location` |
| orbit, observe(point) | `COMMAND_INT` 34 `DO_ORBIT` (radius, velocity, yaw-to-center, center, alt) | `action.do_orbit` |
| search(area) | Companion builds a lawnmower; spacing = footprint width × (1 − 0.3); `MISSION_COUNT`/`MISSION_ITEM_INT`(16)/`MISSION_START`(300) | `mission_raw.upload_mission` + `start_mission` |
| observe/follow(track) | Re-issue `DO_ORBIT`/`DO_REPOSITION` ≤1 Hz on the track estimate at standoff ≥30 m. Never PX4 Follow-Me. | same |
| hold (safety stop) | 176 `DO_SET_MODE` custom main 4 / sub 3 (AUTO.LOITER) | `action.hold` |
| rtl / land | 20 `NAV_RETURN_TO_LAUNCH` / 21 `NAV_LAND` | `action.return_to_launch` / `action.land` |
| speed | 178 `DO_CHANGE_SPEED` | `action.set_current_speed` |
| geofence | `MISSION_TYPE_FENCE` polygon upload, also enforced in the companion | `geofence.upload_geofence` |

MAVSDK method names are the 3.x gRPC plugin names; their 4.x ctypes equivalents are UNVERIFIED ([sim §1.3](council/r1/sim.md) found that 4.x is a rewrite). PX4 parameters per scenario: `NAV_DLL_ACT=2` (Return), `COM_DL_LOSS_T=20`. Enum values are UNVERIFIED and must be checked against the v1.18 parameter reference.

### 2.7 CoT type table (TAK Protocol v0 XML; `version="2.0"`)

| Entity | `type` | `how` | Rate / stale | Notes |
|---|---|---|---|---|
| Self (wearer) | `a-f-G-U-C` | `m-g` | 10 s / 120 s | Callsign RAVEN 1; `__group` |
| Teammates (sim) | `a-f-G-U-C` | `m-g` | 10 s / 120 s | RAVEN 2–4 |
| Own quadcopter | `a-f-A-M-H-Q` | `m-g` | 1 Hz / 30 s | `a-f-A-M-F-Q` if fixed-wing |
| Machine-detected vehicle | `a-u-G-E-V` | machine code UNVERIFIED (default `m-g`; pick at the week-1 ATAK check) | ≤1 Hz / 300 s | `remarks`: "VEHICLE · machine · unconfirmed · D2 · conf 0.81"; `link` to parent drone uid; honest `ce`; `le=9999999` |
| Machine-detected person | `a-u-G` | same | ≤1 Hz / 300 s | remarks "PERSON". **Never a unit type.** |
| Unknown air (drone class, later) | `a-u-A` | same | / 120 s | Not in Phase 0 classes (C16) |
| Human MARK | same `a-u-*` | `h-e` | / 900 s | remarks "marked by RAVEN 1" |
| Human reclassify (companion UI only) | `a-h-*` / `a-n-*` / `a-f-*` | `h-e` | / 900 s | Only path to non-unknown affiliation |
| Camera SPI | `b-m-p-s-p-i` | `m-g` | 1 Hz / 10 s | ATAK rendering UNVERIFIED |
| NAI / checkpoint | `b-m-p-w` (UNVERIFIED) | `h-e` | long | From the scenario gazetteer |

**Scope guard** (in `tak/`, the *only* CoT egress): it refuses any `a-h-*` whose `Track.affiliation_src` is not `human` and any type outside this table, and logs every refusal. `<detail>` carries `contact@callsign`, `__group@name/role`, `track@course/speed`, `remarks`, `link`, and an `<edith v="1" track_id=… asset_id=…/>` extension ([defense_sme §1.3](council/r1/defense_sme.md)).

---

## 3. Component specs

### 3.1 Companion modules (`companion/edith_companion/`)

| Module | Responsibility | Key interfaces |
|---|---|---|
| `gateway` | aiohttp WS :7400 + HTTP :7401; hello/token; snapshot push; binary demux | `Session`, `publish(msg)` |
| `bus` | In-process asyncio pub/sub; every message passes through `eventlog` | `Bus.subscribe(type)` |
| `eventlog` | Append-only SQLite (WAL) of every envelope and FSM transition; also the audit log (audio sha256, n-best, model hashes) | `EventLog.append`, replay |
| `world` | Assets, tracks, teammates, operator pose, gazetteer, AO/geofence | `World` snapshot |
| `voice` | VAD, `AsrEngine` (pluggable), confirm recognizer | `AsrEngine.stream(frames) -> partials/final` |
| `intent` | Normalizer, Lark grammar, resolver, read-back generator | `parse(text, ctx) -> CommandIntent` |
| `safety` | Gate checks, safety-stop path, proposal FSM, invariant monitor | `propose()`, `confirm()`, `stop()` |
| `assets` | `AssetAdapter` (pymavlink PX4 / MockVehicle), GCS heartbeat, telemetry→`AssetState` | §2.6 |
| `perception` | FrameSource, scheduler, detectors, tracker, geo, fusion | §3.5 |
| `alerts` | Alert generation and ranking, suppression, flood control | `Ranker.top()` |
| `hud` | Projects world + alerts + proposal + voice → `HudState`; inset policy; declutter/night | `project() -> HudState` |
| `tak` | CoT build/parse, scope guard, transports (mesh/TCP via PyTAK), outbox, inbound merge | `CotOut.send(evt)` |
| `config` | YAML: thresholds, ranker weights, safety limits, vocabulary | one file, versioned |

### 3.2 Voice pipeline

| Stage | Choice | Notes |
|---|---|---|
| Activation | **PTT only** (hold right temple; toggle fallback with 8 s cap if T7 fails; companion button). No wake word in Phase 0 (C35) | Porcupine's free tier ended 30 Jun 2026; openWakeWord models are NC ([voice §1.1](council/r1/voice.md)) |
| Capture | 16 kHz mono PCM16, 20 ms frames. RayNeo `audio_source_record=…` voice mode (exact string UNVERIFIED), with Android `VOICE_RECOGNITION` as fallback | Mic muted while `audio.down` plays |
| VAD | Energy trim in P0. Silero VAD (MIT) ONNX via onnxruntime in P1 | PTT already bounds speech |
| ASR | `AsrEngine` interface. **Primary candidate: Moonshine Small Streaming (MIT)**; biased fallback: **sherpa-onnx streaming zipformer + hotwords** (Apache-2.0). Whichever installs cleanly on Py 3.13 is integrated first; the W3 bake-off picks the winner (C18) | Vendor numbers: Moonshine Small 165 ms / 7.84% WER on Linux x86 ([voice §1.3](council/r1/voice.md)) |
| Hotwords | Call signs, NATO alphabet, digits + NINER, prowords, verbs, gazetteer names, contact aliases | Generated from config and world |
| Confirm recognizer | Open ASR "confirm" alone, conf ≥ τ_confirm (0.80 start). In P1, AND Vosk `small-en-us-0.15` closed grammar `["confirm","cancel","say again","[unk]"]` | Two-engine agreement |
| Parse | Normalizer → Lark Earley grammar (§3.3) → resolver | Deterministic; fully unit-tested |
| LLM | Deferred to S2 stretch. If used: Qwen2.5-0.5B/1.5B GGUF, GBNF-constrained to canonical text, **re-parsed by the same grammar**, with a grounding check (C20) | Never required; cloud only as a benchmark |
| Read-back | HUD card text is primary. TTS is optional, default off (P2; sherpa-onnx Piper with a permissively licensed voice, not Lessac) (C19) | |

Latency budget (end-of-speech → card): PTT tail + last frame 200 ms, ASR finalize 250 ms, parse + gate 30 ms, render ≈20 ms → **≈500 ms p50, ≤1.5 s p95** ([voice §1.7](council/r1/voice.md)).

### 3.3 Command grammar (Phase 0, v1)

```
utterance   := safety_stop | command | response | query | hud_cmd
safety_stop := [ "all" ("drones"|"assets") ] stop_word          # scope = all
             | callsign stop_word                                # scope = that asset
stop_word   := "hold" | "abort" | "stop"
command     := callsign verb_phrase
callsign    := "drone" ("one"|"two"|"three"|"four"|DIGIT)        # D1..D4; no broadcast tasking in Phase 0
verb_phrase := ("take off"|"launch") [ "to" distance ]                         -> takeoff(alt)
             | ("go to"|"move to") location [alt_mod]                          -> goto
             | ("orbit"|"circle") location [radius_mod] [alt_mod]             -> orbit
             | ("watch"|"overwatch"|"observe"|"look at") (location|contact) [radius_mod] [alt_mod] -> observe
             | ("search"|"scout"|"scan") area [alt_mod]                        -> search
             | "follow" contact [ "standoff" distance ]                        -> follow   (stretch, L8)
             | ("return"|"r t b"|"come home") ["home"]                          -> rtl      (needs confirm)
             | "land"                                                          -> land     (needs confirm)
location    := "my position" | clock_range | grid | named | relative
clock_range := CLOCK "o'clock" [","] distance                    # relative to heading snapshot at PTT release
grid        := ["grid"] [ GZD SQUARE ] DIGITS{4|6|8|10}          # GZD+square preloaded (16T CK)
named       := ("n a i"|"nai") NUM | ("checkpoint"|"c p") NUM | "waypoint" NATO | GAZETTEER_NAME
relative    := distance CARDINAL "of" named
area        := named | grid [ "size" distance ]                  # default square 300 m
contact     := "contact" NUM | "the" ("vehicle"|"person")        # only if unique
radius_mod  := "radius" distance                                 # 30–300 m
alt_mod     := "altitude" distance                               # 30–120 m AGL
distance    := NUMBER [ "meters"|"metres"|"m"|"k"|"kilometers" ] # default unit metres
response    := "confirm" | "cancel" | "watch" | "mark" | "dismiss" | "say again" | "details"
query       := [callsign] "status"
hud_cmd     := "show" callsign | "hide feed" | "map" ("two fifty"|"five hundred"|"one k"|"two k")
             | "declutter" | "night mode" | "day mode" | "brighter" | "dimmer"
```

The normalizer maps `niner→9`, `fife→5`, `tree→3`, NATO letters, digit strings ("four zero zero" → 400) and compounds ("one point five k" → 1500). Mixed number styles are **rejected, never guessed**. Unknown verbs ("attack", "engage", "fire", "drop") return `REJECTED: "Unsupported command"`, and nothing is sent. "Track" is not a spoken verb (L3).

Bare `watch` is an alert response: it pins the contact and moves nothing. `drone two watch contact one` is an asset command and needs confirmation (C03).

| Utterance | Result |
|---|---|
| "drone one scout NAI one" (D1 landed) | Proposal: `DRONE 1 → LAUNCH + SEARCH NAI 1 · 16T CK 6142 3705 · 300 m sq · ALT 60 m` (C09) |
| "drone two overwatch my position radius one five zero" | Proposal: observe(self) = orbit at operator, R 150 m |
| "drone two orbit two o'clock four hundred" | Proposal: resolved to BRG 062 / 400 m → MGRS, absolute in the read-back |
| "drone one orbit grid six one four two three seven zero five" | Proposal; read-back digit by digit, pin on the mini-map |
| "abort" / "all drones hold" / triple-tap | **Immediate** hold for all airborne assets; pending proposal cancelled; toast "ALL HOLD" |
| "drone two return" | Proposal (RTL needs confirmation, L1) |
| "drone one attack the vehicle" | REJECTED "Unsupported command"; 0 MAVLink commands |
| "drone two orbit grid six one four two three seven" (odd digit count) | SAY_AGAIN on the grid slot |
| "watch" (alert shown) | Feedback watch; inset pinned; no motion |

### 3.4 Safety state machine

```
Voice session:  IDLE ─ptt_down→ LISTENING ─ptt_up+150ms→ PROCESSING ─→ one of:
                 PROPOSED | SAY_AGAIN(≤2 per slot, then "use touch") | REJECTED | STOP_EXECUTED | RESPONSE_APPLIED | NOOP
Proposal:       PROPOSED ─lockout(max(600 ms, TTS end))→ AWAIT_CONFIRM ─valid Confirmation→ CONFIRMED
                 ─gate re-check pass→ DISPATCHED ─ACK→ IN_PROGRESS → COMPLETED | FAILED | ABORTED
   exits from PROPOSED/AWAIT_CONFIRM: CANCELLED (cancel word | double-tap | companion) · EXPIRED (10 s) ·
   SUPERSEDED (new command or safety stop) · INVALIDATED (WARNING alert | glasses link drop | asset link lost | gate fail)
Safety stop:    any state ─HOLD/ABORT/STOP | triple-tap | companion HOLD ALL→ hold() on scoped airborne assets (≤500 ms)
```

A **valid Confirmation** matches the live `proposal_id` and nonce, arrives after `lockout_until_ms` and before `expires_ms`, and is one of: voice "confirm" as the whole utterance in a press that started after the card appeared, with conf ≥ τ (plus closed-grammar agreement in P1); a temple two-finger hold ≥1 s whose `ctx.proposal_id` matches; or a companion `/ui/touch` hold ≥1 s. "Yes", "okay" and "roger" never confirm; anything ambiguous counts as cancel. Gate checks run at proposal time and again before dispatch:

| Check | Limit |
|---|---|
| Target inside AO polygon / geofence | Scenario `ao` |
| Altitude band | 30–120 m AGL; default 60 m |
| Range from home | ≤1,500 m |
| Battery for new task (not hold/rtl/land) | ≥30% |
| Asset link | `ok` |
| Track-referenced target age | <30 s |
| Orbit radius / follow standoff | 30–300 m / ≥30 m |
| Verb valid in asset state | e.g. landed ⇒ compose takeoff first |

**Invariants** (Hypothesis property tests + a runtime monitor that raises a WARNING and logs on violation): **I1** no motion-adding MAVLink command (arm, takeoff, reposition, orbit, mission start, rtl, land, speed, any mode other than LOITER) leaves the adapter without a DISPATCHED proposal and matching Confirmation; **I2** the only unconfirmed command is hold; **I3** at most one live proposal; **I4** no command survives a disconnect; **I5** every transition is in the event log; **I6** `affiliation_src=machine ⇒ affiliation=unknown`.

### 3.5 ML pipeline

| Item | Decision ([ml](council/r1/ml.md)) |
|---|---|
| Classes (Phase 0) | `person`, `vehicle` (COCO car/bus/truck/motorcycle). COCO animals → `other`, never alerted. `drone` deferred (C16). No face/ID/re-ID classes, ever. |
| Companion default | **YOLOX-Tiny @416, Apache-2.0**, 2×2 tiles (15% overlap) on 1280×720, ORT CPU, 1 thread. Measured here: ~250 ms per tiled frame ([probed], ml §0) |
| Glasses candidate | YOLOX-Nano @416 (or @320) → TFLite fp32/fp16/int8 via onnx2tf |
| Accuracy tier | D-FINE-N (Apache-2.0), companion only. RT-DETRv2-R18 as offline teacher / auto-labeler |
| Forbidden | Ultralytics (AGPL-3.0), Lessac voice, NC datasets in shipped artifacts |
| Thresholds | Detector floor 0.25 (tracker low-conf association 0.10); NMS IoU 0.5 including cross-tile; confirm ≥3 hits / 5 detections and mean conf ≥ τ_c (person 0.30, vehicle 0.35; swept to an operating point frozen at W8) |
| Tracker | ByteTrack via Roboflow `trackers` (Apache-2.0) if it installs on Py 3.13 without heavy deps; otherwise an in-repo ByteTrack-style IoU+Kalman tracker (C17) |
| Geolocation | Pixel → ray via K → gimbal → body → NED; intersect the plane at home elevation. Box bottom-center. Reject rays above −5° depression. `ce_m` from first-order propagation (≈4.2 m per 1° attitude error at 60 m AGL, 30° depression) |
| Fusion | Same class, Mahalanobis on ce₁²+ce₂², \|Δt\|<5 s, inverse-variance merge; `source_assets[]` |
| Novelty | New if no same-class track within max(15 m, 2·ce) in the last 120 s |
| Training (S2) | W1–4: fine-tune YOLOX-Tiny/Nano on VisDrone-DET (2-class, sliced 416 tiles; SAHI reports +12.7–14.5 AP). W4–7: 1:1 mix with sim frames. On Colab T4 or a Penn cluster (UNVERIFIED) |
| Data licenses | VisDrone CC BY-NC-SA 3.0, UAVDT research-only, Okutama no stated license: **research/eval only, fetched by `tools/fetch_data.py` into gitignored `data/` with SHA-256 pins and per-file license records** (L9). Phase 1 must retrain on synthetic + owned data |

**Alert ranking** (C10, C11). Tier wins outright: WARNING > CAUTION > ADVISORY. Within a tier:
`score = 0.35·proximity + 0.20·closing + 0.15·recency + 0.15·novelty + 0.10·class_w + 0.05·conf`, where
- proximity = 1 − min(r/1 km, 1)
- recency = e^(−age/30 s)
- novelty = 1 for new, 0.3 for a re-alert
- class_w is set per mission (vehicle 1.0, person 0.8)
- contacts inside a mission AOI get +0.1 (clamped)

A higher tier pre-empts immediately; within a tier, a new alert pre-empts only if ≥0.2 higher and the current one has been shown ≥3 s. DISMISS suppresses the track plus a 15 m same-class disc for 10 min, unless the tier escalates or range closes ≥30%. More than 3 alerts of a tier within 10 s collapse into one ("3 UNKNOWN · NE · 300–600 m"). Advisories expire at 30 s, cautions at 120 s. Target rate ≤2 alerts/min.

| Alert kind | Tier |
|---|---|
| new_contact (confirmed track) | CAUTION |
| contact_close (<150 m from operator) | WARNING |
| link_lost (asset) | CAUTION |
| battery_low | CAUTION at 25%, WARNING at 15% |
| geofence breach | WARNING |
| teammate_stale (>120 s) | ADVISORY |
| task_status (ack/complete/fail) | ADVISORY (fail = CAUTION) |

A WARNING arriving mid-confirm invalidates the proposal.

### 3.6 Simulation tiers and scenario format (L9; [sim](council/r1/sim.md))

| Tier | Autopilot | Camera | Where | Use |
|---|---|---|---|---|
| 0 MockVehicle | Pure-Python kinematic vehicle speaking MAVLink (pymavlink), 10× speed; mirrors the verb allowlist, `NAV_DLL_ACT` and battery model | Synthetic or `gt_detector` | Anywhere; CI | Unit, contract and e2e |
| **A (default)** | **PX4 v1.18 SIH** prebuilt `.deb` (`px4_1.18.0~rc2-noble_amd64.deb`, 12 MB [probed]; Docker image on macOS/Win) | **Synthetic**: NAIP ortho (public domain) homography + metric sprites + exact GT boxes, 4.0 ms/frame at 720p [probed]; **Replay**: real annotated clips registered to the SIH trajectory (VisDrone-MOT, Okutama) for G2 accuracy | Laptops; this workspace after approval | Dev, demo, G1/G2 metrics |
| B (showcase) | PX4 + Gazebo Harmonic `x500_mono_cam_down` | Rendered gz camera RTP 5600+i | Ubuntu 24.04 + NVIDIA laptop | Visual polish only |

Sprites serve flow and geometry only; **G2 accuracy numbers come only from replay or real imagery**. `gt_detector` emits Detections from GT with configurable Pd, FA rate, latency and noise, so the whole pipeline runs without ML. The PX4 binary has not run here (blocked by workspace permission policy, sim §1.2), so MockVehicle carries CI.

**Site** (C13): rural Piatt County, Illinois, origin 40.0700 N, 88.6300 W, 210 m MSL (MGRS 16TCK 61002 36799 [probed]), flat, with no military facility nearby. The named points are fictional: NAI 1 (road junction), NAI 2 (farm compound), CP 3, "north treeline".

**Scenario YAML v1** (sim format plus voice/assert events):

```yaml
version: 1
seed: 1234
origin: {lat: 40.0700, lon: -88.6300, alt_msl: 210}
basemap: {source: naip, item: il_m_4008859_ne_16_030_20230813_20240214, extent_m: 2000, gsd_m: 0.5}
ao: [[-800,-800],[800,-800],[800,800],[-800,800]]          # ENU m; also the geofence
safety: {alt_agl_m: [30,120], default_alt_m: 60, max_range_m: 1500, min_task_battery_pct: 30}
px4_params: {NAV_DLL_ACT: 2, COM_DL_LOSS_T: 20}
operator: {id: op1, callsign: "RAVEN 1", path: [{t: 0, e: -300, n: -300, heading: 45}]}
teammates: [{uid: tm-2, callsign: "RAVEN 2", path: [{t: 0, e: -320, n: -290}, {t: 300, e: -100, n: 0}]}]
assets:
  - {id: drone1, callsign: "DRONE 1", px4_instance: 0, spawn: {e: -300, n: -280},
     camera: {mode: synth, w: 1280, h: 720, hfov: 70, pitch: -60, fps: 15}}
  - {id: drone2, callsign: "DRONE 2", px4_instance: 1, spawn: {e: -280, n: -280},
     camera: {mode: replay, clip: visdrone-mot/uav0000086_00000_v, alt_agl_m: 50, track: orbit}}
gazetteer: [{name: "NAI 1", e: 400, n: 250}, {name: "NAI 2", e: 380, n: -120, area_m: 200}, {name: "CP 3", e: -300, n: -300}]
entities:
  - {id: veh-7, cls: vehicle, sprite: pickup_tan, path: [{t: 60, e: 400, n: 250}, {t: 180, e: 150, n: 420}]}
  - {id: per-3, cls: person, sprite: person_dark, path: [{t: 0, e: 380, n: -120}], loiter_radius_m: 15}
events:                                                    # say/touch inject operator input in headless runs
  - {t: 30,  type: say,  text: "drone one scout nai one"}
  - {t: 33,  type: say,  text: "confirm"}
  - {t: 120, type: jam,  duration_s: 25, links: ["mavlink:drone2", "tak:*"]}
  - {t: 250, type: say,  text: "drone one attack the vehicle"}
  - {t: 260, type: touch, gesture: triple_tap}
expect:                                                    # headless run exits non-zero if any fails
  - {by_t: 34,  proposal: {verb: search, state: dispatched}}
  - {by_t: 90,  alert: {kind: new_contact, cls: vehicle, tier: caution}, cot: {type: a-u-G-E-V}}
  - {by_t: 142, asset: {id: drone2, link: lost}}
  - {by_t: 150, outbox: {flushed: true, order_preserved: true}}
  - {at_t: 251, intent: {result: rejected}, mavlink_commands_since: {t: 250, count: 0}}
  - {by_t: 261, asset: {id: drone1, mode: AUTO.LOITER}}
```

Each run writes `gt_events.jsonl` (`entity_spawn/despawn`, `entity_in_fov{asset, entity, t_enter, t_exit, min_range, px_height}`, `jam_start/end`, `asset_mode`, `battery`) on `sim.truth.*`; **only `bench/`, `tests/` and `gt_detector` may import it** (lint test). PX4 is not bit-deterministic, so assertions use tolerances. Linkshaper is an asyncio UDP proxy for MAVLink and CoT with scripted drop/latency/partition/bandwidth windows; the true-pose tap feeding cameras is never impaired.

### 3.7 HUD spec ([hud](council/r1/hud.md), with L3/L5/L6 applied)

Display: 640×480 per eye, ~24.2°×18.3°, 26.4 px/deg. Vendor hard rules ([RayNeo design spec](https://rayneo.gitbook.io/rayneo-devdoc/x-xi-lie/she-ji-gui-fan)): safe area x30–610 / y20–460 per eye; text ≥16 px; lines ≥2 px; **black = transparent, no filled panels behind text**; APL ≤13% persistent, ≤25% transient; ≤30 fps; red for warnings only.

| Region | Box (x0,y0–x1,y1) | Content |
|---|---|---|
| Mini-map | 30,20–190,180 | Heading-up circle r=76 px; default 500 m (rings 50/100%); voice "map" 250/500/1k/2k; ≤12 symbols, then clusters |
| Status strip | 30,184–190,204 | 16 px `TAK●` `GPS●` companion battery %; `DATA 45s` when stale; `REC` when audio is retained |
| Heading tape | 200,20–420,58 | Compressed ±55° (2 px/°), 10° ticks, cardinals, boxed 3-digit heading; carets at y46–58 (cyan drones, yellow unknowns); ◄/► clamps |
| Drone inset | 440,20–610,148 + label to y166 | 170×128 of 320×240 video; label `DRONE 2 · LIVE · 0.4s`; `FROZEN 3s` + slash when the frame is >1 s old; contrast-stretched without lifting blacks |
| Drone chips | 440,170–610,204 | `D1 ORBIT 62%` `D2 LINK✕ RTL 0:12` (16 px) |
| Center clear zone | 170,150–470,330 | Nothing persistent; only the conformal caret band y232–248, \|Δ\|≤11°, hidden at yaw rate >60°/s or heading unc >10°; no reticle |
| Banner / confirm card | 60,336–580,410 (card may grow to y316) | §3.7.2 |
| Voice state | 30,432–250,458 | `● LISTENING` `◌ READY` `… PROCESSING` `■ MUTED` `✕ VOICE OFFLINE` (distinct shapes) |
| Transcript | 260,432–610,458 | 16 px last heard, fades after 3 s |

**Palette** (monochrome-first: shape and text carry meaning; C29):

| Token | sRGB | Use |
|---|---|---|
| `fg` | `#E8FFE8` | Text, tape, rings (40%) |
| `friend` | `#33DDFF` | Teammates, own drones |
| `unknown` | `#FFD400` | **All machine detections**, CAUTION tier (replaces amber `#FFB000`, L3) |
| `warning` | `#FF3030` | WARNING border/glyph; human-reclassified hostile only |
| `ok` | `#44FF66` | Voice/link nominal |
| `night` | `#33FF66` at the minimum readable level (target <5 cd/m², measured) | **Night mode: everything dim green, APL ≤3%, inset on request only, rings off** (L6; MIL-STD-3009 NVIS rationale). Red "dark-adapt" variant optional |

**Symbology** (2525-like, 12 px, 2–3 px strokes):

| Entity | Symbol |
|---|---|
| Self | `fg` chevron |
| Teammate | Cyan filled circle with heading tick |
| Own drone | Cyan "∩" plus its number |
| Machine detection | **Yellow open quatrefoil** (unknown frame, four 2 px lobes) with class letter P/V (C05); never a diamond |
| Human-marked contact | Filled quatrefoil |
| Human-reclassified hostile | Red open diamond |
| Stale | Dashed after 30 s; "last known 2m" after 120 s; removed at 5 min |

**Typography:** B612 Bold (OFL, bundled). Alert headline 28 px (~45′), detail/confirm rows 20 px, static labels 16 px.

#### 3.7.2 Alert and confirm cards

```
┌─◆ VEHICLE · 2 o'clock · ~400 m ─────────────────── +2 ◆▲ ┐   row1 28 px (≤28 chars), live clock
│   DRONE 2 · UNKNOWN · 12 s                               │   row2 20 px (source · affiliation · age)
└── say WATCH · MARK · DISMISS ────────────────────────────┘   row3 20 px
```
The 2 px tier-color border flashes at 2 Hz for 2 s, then holds (≤3 Hz). Glyphs: ▲ WARNING, ◆ CAUTION, ⓘ ADVISORY. `+N` shows the queue with per-tier pips.

```
CONFIRM TASK                                     ████████░░ 10s
DRONE 2 → SEARCH NAI 2  (16T CK 6138 3668)
ALT 60 m · AREA 200 m · ETA 2 min
say CONFIRM / CANCEL        hold 2 fingers = confirm
```
The card renders from `CommandProposal`, never the raw transcript. The hint reads `…` during the 0.6 s lockout. Timeout shows `NOT SENT — timed out` (it never auto-confirms). After confirm: `SENT` → `ACK DRONE 2`, or yellow `NO ACK — link` after 3 s. A safety stop shows the yellow toast `ALL HOLD` / `D2 HOLD`.

**Modes:** Day (full palette); Night (dim green, above); Quiet (no TTS/earcons, touch confirm preferred); Degraded (stale styling, `COMPANION LOST — LOCAL ONLY`, `✕ VOICE OFFLINE` → touch); Declutter (FULL → MIN: tape, banner, voice → WARN-ONLY).

**Temple gestures** (no single gesture can command an asset beyond STOP):

| Gesture | Action |
|---|---|
| Tap | Show queue |
| Swipe fwd/back | Next/prev alert |
| Double-tap | DISMISS / CANCEL |
| **Triple-tap** | **SAFETY STOP: hold all** (L1, C08) |
| Long-press ≥300 ms (hold) | PTT |
| Two-finger hold ≥1 s with ring | CONFIRM (only while a card is open) |

Input is ignored within 300 ms of a wear-state change. If T7 shows the system owns long-press, PTT becomes tap-toggle (8 s cap).

### 3.8 Glasses app (Kotlin; [platform](council/r1/platform.md), L5)

| Module | Content |
|---|---|
| `hud-core` (KMP: `commonMain` + `jvm` + `android`) | Protocol models (kotlinx.serialization), Ktor WS client, layout math in pure Kotlin, `HudRenderer` on Compose `DrawScope`, B612 font, lints (APL, min text, stroke) |
| `platform-api` | `GlassesPlatform` and sub-interfaces (below) |
| `platform-rayneo` | **The only module importing `com.ffalcon.*`**. Host `BaseEventActivity` (not `BaseMirrorActivity`); `TempleAction` + raw DOWN/UP → `InputEvent`; `MercurySDK.init`; `audio_source_record` mode; RV/fused heading |
| `platform-generic` | AOSP phone: touchscreen gestures, `VOICE_RECOGNITION`, phone RV, Camera2 |
| `app-android` | Flavors `rayneo` / `generic`. `HudActivity`, `SelfTestActivity` (T0–T18), `BenchActivity` (P1). `StereoCompositor` inside `DisplaySink`. mDNS + manual IP |
| `emulator-desktop` | Compose Desktop, same `hud-core` (§3.9) |

```kotlin
interface GlassesPlatform {
  val display: DisplaySink   // eyeSize 640×480, stereoMode: SBS_DUPLICATE|MONO|SBS_LEFT_ONLY, eyeOffsetPx(L,R), setBrightness(0..200), keepOn()
  val input: InputSource     // Flow<InputEvent>: Tap, DoubleTap, TripleTap, SlideFwd/Back/Up/Down, PttDown, PttUp, TwoFingerHold, TwoFingerTap, Back
  val mic: MicSource         // open(ASR|AMBIENT) -> Flow<ShortArray 320 samples @16 kHz>
  val pose: PoseSource       // Flow<Pose(yaw, pitch, roll, heading, headingUnc, source)> 20–50 Hz
  val camera: CameraSource   // frames(w, h, fps, YUV|JPEG)  (benchmark only, off by default)
  val power: PowerMonitor    // battery%, µA, mV, °C, thermalStatus, headroom
  val info: DeviceInfo       // model, fingerprint, sdkInt, capabilities -> sys.hello
}
```

- **Display (L5):** the app renders **side-by-side**. It is one `Row` of two 640×480 slots drawn by the same renderer, with per-eye `dx` offset; video is decoded once and drawn twice. The `rayneo` default is `SBS_DUPLICATE` (1280×480 logical, UNVERIFIED until T5: `wm size`). The mode is a runtime switch. A `View/Canvas` backend exists in case Compose is too slow when drawn twice.
- **Manifest:** `<meta-data android:name="com.rayneo.mercury.app" android:value="true"/>`, landscape, `keepScreenOn`. Permissions: CAMERA, RECORD_AUDIO, INTERNET, CHANGE_WIFI_MULTICAST_STATE, WRITE_SETTINGS.
- **Levels:** compileSdk 34 (installed at `/opt/android-sdk`), minSdk 29, targetSdk 34, JVM target 17. The device is very likely Android 12 / API 31–32 (UNVERIFIED, T0).
- **SDK handling:** `tools/fetch_rayneo_sdk.sh` downloads `MercuryAndroidSDK-v0.2.6-…aar`, `RayNeoIPCSDK…aar` and the sample. It verifies SHA-256 against `glasses/platform-rayneo/sdk.lock`; the full hashes are recorded on first fetch, because platform.md gives prefixes. Files land in gitignored `glasses/platform-rayneo/libs/`. The SDK has no license text, so it is treated as proprietary and never committed. Without the SDK, `rayneo` tasks fail with a clear message while `generic` still builds.
- **Inset:** MJPEG over WS, `BitmapFactory` on one worker, latest frame only. RTSP and WebRTC are rejected. H.264 via MediaCodec only if T13 latency is >250 ms.
- **Thermal policy:** at `MODERATE`, inset drops to 5 fps and the camera turns off. At `SEVERE`, HUD only.

### 3.9 Emulator (`glasses/emulator-desktop`)
- **Views (L5):** **single-eye 640×480** (×2 nearest-neighbor); **SBS 1280×480**, exactly as sent to the glasses; see-through composite out = clamp(T·bg + k·hud) over background clips; optional true-angular view.
- **Inputs:** mouse/arrows for head yaw/pitch (or a replayed IMU log); Space = PTT (laptop mic or injected WAV); typed text via `voice.text`; keys → `InputEvent` (e.g. T = triple-tap, C = two-finger hold).
- **Lints:** live APL meter (warns at 13%/25%), text ≥16 px, stroke ≥2 px, colorblind simulation.
- **Headless:** `--render-fixtures dir/` writes golden PNGs (both views) via `ImageComposeScene`. Headless Skia in this workspace is UNVERIFIED (D11 spike), with a Robolectric/Java2D fallback.
- **Python `tools/fake_glasses.py`:** a WS client for CI. It records HudState and scripts inputs.

---

## 4. Repo, stack, running, testing

### 4.1 Layout

```
edith/
  edith                         # bash shim → uv run python -m edith_tools.cli
  pyproject.toml uv.lock        # uv workspace root (owner WS-A)
  schemas/v1/*.schema.json      # source of truth (owner WS-A)
  schemas/fixtures/{valid,invalid}/<type>/*.json   schemas/cot/*.xml
  common/edith_common/          # envelope, models (pydantic), geo, clock, ids
  companion/edith_companion/    # gateway bus eventlog world voice intent safety assets perception alerts hud tak config
  sim/edith_sim/                # scenario, mover, mockvehicle, px4, camera, linkshaper, teammates, truth, gt_detector
  ml/edith_ml/                  # models.yaml (sha256+URL), detectors, export (onnx2tf), train, eval
  bench/edith_bench/            # goal1, goal2, placement, pareto
  tools/edith_tools/            # cli (+ commands/<ws>.py), fetch_data, cost_model
  tools/*.sh                    # fetch_rayneo_sdk.sh, install_px4.sh, bringup.sh
  scenarios/                    # demo_vignette.yaml, demo_scout.yaml, jam.yaml, goal2_*.yaml
  glasses/                      # settings.gradle.kts, gradle/libs.versions.toml, hud-core, platform-*, app-android, emulator-desktop
  tests/{e2e,lint}/             # cross-package
  docs/  PLAN.md  council/  bringup/  cost/  LICENSES.md
  data/ models/ runs/           # gitignored
```

### 4.2 Tech stack (pins; `uv.lock` and `libs.versions.toml` are authoritative)

| Component | Version | License | Note |
|---|---|---|---|
| Python | 3.13 | — | installed |
| uv / ruff | installed | MIT | |
| numpy | 2.5.3 | BSD | installed |
| onnxruntime | 1.29.0 | MIT | installed; benchmarks measured on it |
| opencv-python-headless | 5.0.0.93 | Apache-2.0 | installed |
| pydantic / jsonschema | 2.13.5 / 4.26.0 | MIT | installed |
| pytest / hypothesis | 9.1.1 / latest at lock | MIT/MPL-2.0 | |
| aiohttp | 3.x latest at lock | Apache-2.0 | WS + HTTP (C28) |
| pymavlink | 2.4.50 | LGPL-3.0 | [probed] wheels cp39–cp314; LGPL dynamic use is acceptable |
| pymap3d / mgrs | 3.2.0 / 1.7.1 | BSD / MIT | [probed] |
| lark | 1.x latest | MIT | grammar |
| PyAV (`av`) | latest cp313 wheel | BSD | RTP H.264 decode |
| PyTAK | 7.x | Apache-2.0 | transports; Py 3.13 UNVERIFIED → stdlib fallback |
| sherpa-onnx / moonshine / vosk | latest at lock | Apache/MIT/Apache | Py 3.13 wheels UNVERIFIED (D10) |
| onnx2tf + tensorflow (separate venv) | latest supporting the venv | Apache/MIT | D14 only |
| PX4 SIH | 1.18.0~rc2 deb | BSD-3 | pinned by sha256 |
| JDK / Gradle | 21 / 8.14.3 | — | installed |
| Kotlin / AGP | 2.2.x / 8.13.x | Apache-2.0 | exact patch fixed in the D11 spike |
| Compose Multiplatform | 1.9.x matching Kotlin | Apache-2.0 | |
| Ktor / kotlinx.serialization | 3.x / 1.9.x | Apache-2.0 | |
| Robolectric | 4.15+ (android-all 31) | MIT | |
| Android SDK | platforms;android-34, build-tools 34.0.0 | — | installed at `/opt/android-sdk` |
| B612 font | 1.008 | OFL | bundled |

### 4.3 How to run

```
./edith doctor                                  # env check: python, uv, java, gradle, android sdk, ports free
./edith fetch models|rayneo-sdk|naip|visdrone-mot|noise|all
./edith up --headless --scenario scenarios/demo_vignette.yaml --assets mock --detector gt --speed 4
./edith up --scenario scenarios/demo_vignette.yaml --assets px4 --detector yolox --emulator sbs --tak mesh
./edith up ... --tak tcp://10.0.0.5:8087        # optional OpenTAKServer
./edith test unit|contract|golden|integration|e2e|android|all
./edith bench goal1|goal2|placement|pareto [--clips set.yaml]
./edith glasses build|test|golden|emulator|install|selftest|pull
./edith ci                                       # what CI runs
```

`edith up` is a Python supervisor (there is no Docker). It starts the sims and PX4/Mock, linkshaper, cameras, the companion and the optional emulator, waits on `/healthz`, multiplexes logs into `runs/<ts>/`, and in `--headless` mode exits 0 only if every scenario `expect` passes.

### 4.4 Test strategy and CI

| Tier | Content | Budget here |
|---|---|---|
| unit | pytest + Hypothesis: normalizer, grammar, resolver, gate, FSM invariants I1–I6, ranker, geo, CoT, outbox; Kotlin JUnit: layout, PTT, heading fusion, compositor, clock offset | <90 s |
| contract | Every fixture validated by `jsonschema` (valid pass, invalid fail); pydantic and Kotlin round-trip of every valid fixture | <60 s |
| golden | Emulator PNGs (single + SBS) for every alert tier, card states, modes, stale/frozen, heading fallback; pixel diff ≤0.5%; lints | <3 min |
| integration | Companion + MockVehicle + fake_glasses + CoT fake router; voice WAV → proposal; linkshaper partition | <3 min |
| e2e | `edith up --headless` on `demo_vignette.yaml` (mock) | <5 min |
| e2e-px4 | Same against PX4 SIH ×2 | manual/nightly, after approval |
| android | `assembleRayneoDebug assembleGenericDebug`, `aapt2` manifest checks, JVM + Robolectric | <10 min |

CI runs `./edith ci` locally and through `.github/workflows/ci.yml` (ubuntu-latest) if a remote is added. Model and dataset downloads are cached and hash-checked. The NC dataset tests are skipped unless `data/` is present.

---

## 5. Pre-arrival build scope (Phase B, this workspace)

The workspace has 2 CPU, 7 GB RAM, no GPU, no KVM, no Docker, and no device. PX4 execution and `apt` were blocked by permission policy in round 1. All numbers measured here are **lower bounds**. Priorities: **P0** must ship, **P1** should, **P2** stretch.

### 5.1 Workstreams and file ownership

| WS | Owner role (human counterpart) | Owns (exclusive write) | Deliverables |
|---|---|---|---|
| A Core contracts | Architect (Anshuman) | `pyproject.toml`, `schemas/`, `common/`, `tools/edith_tools/cli/` core, `docs/LICENSES.md` | D0, D1 |
| B Companion core | Architect (Anshuman) | `companion/edith_companion/{gateway,bus,eventlog,world,safety,assets,alerts,hud,config}`, `tools/fake_glasses.py`, `tests/e2e/` | D3, D6 |
| C Voice | Voice (Om) | `companion/edith_companion/{voice,intent}`, `bench/edith_bench/goal1`, `tools/replay_voice.py` | D4, D10, D18 |
| D Sim | Sim (Arjun) | `sim/`, `scenarios/`, `tools/install_px4.sh` | D2, D7, D15, D17 |
| E ML | ML (Anshuman) | `ml/`, `companion/edith_companion/perception/`, `sim/edith_sim/gt_detector.py`, `bench/edith_bench/{goal2,placement,pareto}`, `tools/edith_tools/fetch_data.py` | D8, D9, D14, D16 |
| F TAK + cost | Defense SME / Systems (Simon) | `companion/edith_companion/tak/`, `sim/edith_sim/teammates/`, `docs/cost/`, `tools/edith_tools/cost_model.py` | D5, D19, D20 |
| G Glasses | Platform + HUD (Arjun, Alisha) | `glasses/`, `tools/fetch_rayneo_sdk.sh`, `tools/bringup.sh`, `docs/bringup/` | D11, D12, D13 |

Rules: `schemas/` changes go only through WS-A (others add fixtures under `schemas/fixtures/*/<their type>/` and request edits in `schemas/REQUESTS.md`); each Python package has its own `pyproject.toml` (uv workspace member) so dependency edits don't collide; CLI subcommands register from `tools/edith_tools/commands/<ws>.py`.

Order: D0 → D1 → {D2, D3, D4, D5, D7, D8, D11} in parallel → D6, D12 → the rest.

### 5.2 Deliverables and acceptance tests

| # | P | WS | Deliverable | Acceptance tests (run here) |
|---|---|---|---|---|
| **D0** | P0 | A | Repo skeleton: uv workspace, `./edith` CLI with all subcommands (stubs allowed), ruff config, `.gitignore` (data/, models/, runs/, glasses/platform-rayneo/libs/), `docs/LICENSES.md` | `./edith doctor` → exit 0, prints Python 3.13, Java 21, Gradle 8.14.3, Android SDK 34. `ruff check .` → 0 errors. `./edith test unit` → exit 0. `git check-ignore data/x models/x` → both ignored |
| **D1** | P0 | A | Schemas v1 for all §2.3/§2.4 types; ≥1 valid + ≥1 invalid fixture per type; pydantic models; `edith_common.geo` (ENU/LLA/MGRS, bearing, clock, range) and `clock` | `./edith test contract` → all valid fixtures pass and all invalid fail (≥40 fixtures); pydantic round-trip is byte-stable. Geo tests: ENU↔LLA round-trip <0.01 m; ENU→MGRS→ENU <1 m; `clock(rel_bearing=62°)=="2 o'clock"`; origin → `16TCK6100236799` |
| **D2** | P0 | D | Scenario loader (pydantic + JSON Schema), seeded entity mover, GT logger, **MockVehicle** (pymavlink: heartbeat, 10 Hz telemetry, §2.6 commands, mission + fence, battery, `NAV_DLL_ACT`), pymavlink `AssetAdapter`, **linkshaper** | `pytest sim -q` passes. The adapter contract suite against MockVehicle (arm→takeoff→goto→orbit→search mission→hold→rtl→land at 10×) passes in <60 s. Same seed twice → identical `gt_events.jsonl` sha256. Linkshaper: 0 packets pass during the window; `link=lost` at `COM_DL_LOSS_T`; Mock RTLs; `link=ok` ≤2 s after the window |
| **D3** | P0 | B | Companion core: bus, eventlog, world, safety gate, **proposal FSM + safety stop**, ranker, HUD projector, aiohttp gateway, `/ui/touch`, `fake_glasses.py` | Hypothesis (≥1,000 examples each): I1–I6 hold. Text-level adversarial suite: 10,000 non-confirm utterances into AWAIT_CONFIRM → **0 confirms**. Confirm before lockout ignored; at 10.1 s → EXPIRED. Safety stop → hold sent ≤500 ms, pending proposal SUPERSEDED. RTL/land require confirm. Ranker tests: dwell 3 s, +0.2 pre-empt, 10-min suppression with escalation override, flood collapse, WARNING invalidates proposal. fake_glasses receives hello + snapshot <500 ms; heartbeat 2 Hz ±10% |
| **D4** | P0 | C | Normalizer, Lark grammar (§3.3), resolver (clock / MGRS / gazetteer / relative / contact), read-back generator; ≥400 golden utterance→intent fixtures | `pytest companion/tests/intent -q` → 100% of fixtures pass. Out-of-scope verbs (`fire, engage, attack, drop, strike, shoot`) → 100% REJECTED. Mixed number styles → rejected. Hypothesis: number→words→number and MGRS→speech→MGRS round-trips. Read-back for every fixture equals the canonical string |
| **D5** | P0 | F | CoT build/parse (§2.7 table), scope guard, mesh multicast + TCP transports, SQLite outbox (compaction + replay), inbound merge (LWW on uid/time, honors stale), teammate sim, fake CoT router :18087 | Golden XML per table row. Scope guard: Hypothesis over Tracks → no `a-h-*` with machine source ever emitted. Outbox: 25 s partition then flush → order preserved, original `time` kept, PLI compacted to 1 per uid. TCP round-trip through the fake router. Multicast loopback test passes or skips with a logged reason (cloud network) |
| **D6** | P0 | B (+all) | **`./edith up --headless`** supervisor + `scenarios/demo_vignette.yaml` (the 7-min SME vignette, [defense_sme §1.4](council/r1/defense_sme.md)) exercising all three loops with `gt_detector` | `./edith up --headless --scenario scenarios/demo_vignette.yaml --assets mock --detector gt --speed 4` → exit 0 in <5 min wall time. All `expect` pass, including: scout dispatched; vehicle alert ranked #1 and CoT `a-u-G-E-V`; D2 link lost → RTL; outbox flushed in order; "attack" rejected with 0 MAVLink commands; triple-tap → AUTO.LOITER; confirm-timeout case. `runs/<ts>/summary.json` holds loop latencies |
| **D7** | P0 | D | Synthetic camera (NAIP homography + 6 in-house CC0 sprites + noise) → RTP H.264 5600+i + sidecar 5700+i; `fetch naip` (2×2 km range read); replay mode skeleton; companion `RtpH264Source` + JPEG inset encoder | PyAV receives ≥100 frames; sidecar `frame_id`/pts match 100%. Render ≥25 fps at 720p single-thread. PNG snapshot with GT boxes overlaid matches golden. Companion emits `video.down` 320×240 at 10–15 fps to fake_glasses |
| **D8** | P0 | E | Model fetch (sha256: YOLOX nano/tiny/s, D-FINE-N, RT-DETRv2-R18); YOLOX + DETR adapters; tiler; latest-frame scheduler; tracker; GeoProjector with `ce_m`; fusion; novelty; `gt_detector` | Hashes match. Timing table reproduces within ±25% (YOLOX-Tiny@416 1 thread ≈62 ms). Geo: pixel→ground→pixel <0.1 px; Monte-Carlo ce calibration ≈50% inside CEP50 (±10%). Tracker on GT+noise: IDF1 ≥0.8. Fusion on a synthetic two-drone overlap: duplicate rate <1.2. Tiled frame p95 ≤350 ms here |
| **D9** | P1 | E | `bench goal2` (WR, event recall, FA/h, TTD, CEP, duplicate rate, bootstrap CIs) + replay of VisDrone-MOT via `fetch visdrone-mot` (not committed) | Two runs, same seed → identical metrics JSON. With `gt_detector` Pd=0.95, FA=2/h → WR ≥80% and recall ≥90% (pipeline sanity). With YOLOX COCO on 3 replay sequences: numbers reported with no target (baseline for S2) |
| **D10** | P1 | C | `AsrEngine` with ≥1 real engine (Moonshine or sherpa zipformer); replay-WAV client over real WS; synthetic noisy corpus generator (Kokoro/Piper voices, MUSAN + CC0 noise, SNR clean/20/10/5/0, license manifest); bake-off harness; Vosk confirm recognizer | `./edith bench goal1 --set clean50` → intent accuracy ≥90% on clean TTS. Per-SNR CSV produced. Integration test: WAV → proposal → WAV "confirm" → Mock dispatch. p50/p95 latency recorded (lower bound). `noise_manifest.csv` has a license on every row |
| **D11** | P0 | G | Gradle project; `hud-core` models + renderer + lints; Kotlin contract test on shared fixtures; `emulator-desktop` with single-eye + SBS views and headless golden render | `./edith glasses test` → JVM tests pass; every valid fixture round-trips. `./edith glasses golden` renders ≥20 states × 2 views; diff ≤0.5% vs approved; APL ≤13% on persistent states; no text <16 px. Integration: headless emulator connects to the companion for 10 s and renders ≥15 snapshots |
| **D12** | P0 | G | `platform-api`, `platform-rayneo`, `platform-generic`, `app-android` flavors; `HudActivity`, `StereoCompositor`, PTT FSM, heading fusion, mic capture, inset decoder, mDNS + manual IP; `fetch_rayneo_sdk.sh` | `./edith fetch rayneo-sdk` → hashes recorded/match; `classes.jar` contains `BaseEventActivity`, `TempleAction`. `assembleRayneoDebug assembleGenericDebug` succeed. `aapt2 dump badging` check: meta-data true (rayneo), minSdk 29, landscape, permissions. `com.ffalcon` classes only in the rayneo APK. JVM tests: PTT (300 ms / 50 px), triple-tap → stop event, heading wrap/drift, compositor geometry 1280×480 / 640×480 / phone, latest-frame queue, clock offset. Robolectric: activity starts; injected MotionEvents → PttDown/Up; mic released and `audio_source_record=off` on pause |
| **D13** | P0 | G | **Day-one bring-up kit**: `SelfTestActivity` (T0–T18, platform §5) writing `selftest/<ts>.json`; `tools/bringup.sh` (adb install, getprop, `wm size`, dumpsys sensor/battery/thermal, pull results, push `.tflite` + LiteRT `benchmark_model`); `docs/bringup/CHECKLIST.md` (T0–T18 + voice B1–B6 + HUD measurements: luminance, leakage at 1/5/10 m, ambient sensor); result JSON schema | `tools/bringup.sh --dry-run` with a fake `adb` shim on PATH runs every step and writes `docs/bringup/dryrun.json`, which validates against the schema. A unit test asserts the self-test registry has 19 tests, each with a pass criterion. CHECKLIST lists the owner and pass threshold for every test |
| D14 | P1 | E | TFLite export of YOLOX-Nano/Tiny (fp32/fp16/int8 static, 200 calibration frames) in a separate venv; parity test; LiteRT `benchmark_model` android_aarch64 downloaded | Parity F1 ≥0.95 vs ORT fp32 for each variant (LiteRT Python interpreter). Artifacts with sha256 in `ml/models.yaml` |
| D15 | P1 | D | PX4 SIH launcher (`install_px4.sh`, `edith up --assets px4`), multi-instance homes, params from scenario | **Requires user approval to run the PX4 binary.** Then: the contract suite passes against 2 SIH instances; the jam scenario triggers `NAV_DLL_ACT`; `demo_vignette` with `--assets px4` passes |
| D16 | P1 | E | `bench placement` harness (JSONL schema shared with glasses `BenchActivity`; companion placement measured here) | `bench placement --placement companion` writes per-stage timestamps and summary p50/p95. Glasses JSONL import validates against the schema |
| D17 | P2 | D | Tier B scripts + SDF world generated from the scenario origin | SDF lints; documented run on a GPU laptop |
| D18 | P2 | C | TTS read-back via sherpa-onnx Piper (permissive voice) on `audio.down`; mic gating | TTS never says "confirm"; mic muted during playback (test) |
| D19 | P1 | F | Cost model v0: `docs/cost/model.csv` + `cost_model.py` (full kit, incremental kit, lite kit, Phase 0 spend) | Totals reproduce; every row has a source URL or UNVERIFIED; the script fails if any row lacks both |
| D20 | P2 | F | OpenTAKServer connector config + docs | TCP 8087 client tested against the fake router; OTS install doc |
| D21 | P2 | B/D | `follow` verb end to end (schema exists) | Mock follows a moving entity at standoff ≥30 m ±5 m |

---

## 6. Evaluation plan

### 6.1 G1: voice tasking
| Item | Protocol |
|---|---|
| Synthetic corpus (now → W3) | 2,000 grammar-sampled commands + ~30 paraphrase templates per verb; Kokoro-82M and Piper voices at 0.9/1.1 speed; MUSAN, CC0 Freesound and ESC-50 noise (NC clips eval-only) at clean/20/10/5/0 dB SNR plus a "glasses channel" step. Bar at 10 dB: intent ≥95%, slot exact ≥90%, confident-wrong ≤0.5% ([voice §3](council/r1/voice.md)). Ranks engines; does not prove G1 |
| Real corpus (Dec → W2) | B6: ≥3 speakers × 100 commands through the glasses' mics, indoors and in wind; playback at 60/75/85/95 dB(A) with the SPL meter visible; all-party consent (Pennsylvania law, [defense_sme §1.7](council/r1/defense_sme.md)) |
| Metrics | WER, intent accuracy, slot exact-match, **confident-wrong rate** (safety metric), say-again rate, confirm FA/FR, per-stage p50/p95 latency from the event log |
| False activation | ≥2 h replayed chatter with PTT pressed at random; 10,000-utterance adversarial suite; study lure trials. Target 0 executions |

### 6.2 G2: watch reduction ([ml §1.4](council/r1/ml.md))
- **AFS** (attended feed-seconds) is logged from `hud.event` inset open/close. In baseline B0 all N feeds are visible all mission (AFS = N·T); in condition E feeds are hidden and the inset appears only on alert or request.
- **Event:** an entity is detectable once in FOV, ≥12 px tall and unoccluded ≥1 s; it is recalled if a matching alert (same class, ≤20 m or ≤2·ce) fires within 10 s. Recall is also reported by pixel height (8–32 px).
- **Protocol:** 10 seeded missions × 10 min × 2 drones on replay clips (4–8 entities, 1 cross-drone overlap, 2 distractors, long empty stretches); bootstrap 95% CIs; sweep τ_c and persistence, then **freeze the operating point at W8**. WR is always reported with recall and FA/h, so "never alert" cannot game it.

### 6.3 Edge vs offload benchmark
| Placement | Path |
|---|---|
| P1 (default) | Detector on companion; glasses render only |
| P2 | Companion relays 320×240/640×360 JPEG to glasses; glasses detect; Detections return |
| P3 | Offload server (second laptop / Penn GPU) over Wi-Fi, same API (optional) |
| P4 | Glasses camera → on-glasses detection (point at a monitor replaying clips for repeatability) |

- **Measurements:** per-stage timestamps; capture→alert p50/p95; sustained fps and drops; parity F1 ≥0.95 vs ORT fp32 and accuracy vs GT; bytes/s each way; glasses energy (`CURRENT_NOW` × voltage at 1 Hz minus idle baseline → mJ/inference, %/h); thermal status/headroom; 20-min soak per config.
- **Glasses runtimes, in order** (all UNVERIFIED on AR1): LiteRT CPU 1/2/4 threads → LiteRT GPU fp16 → NNAPI → QNN if its libraries load (LiteRT's QNN list omits AR1). Hypothesis: P1 wins on latency and battery; P2 is viable only for Nano-class models at ≤2 Hz.
- **Research contribution for the mentor** ([pm §1.2](council/r1/pm.md)), W8: a Pareto curve of alert latency and recall vs link bandwidth/loss (50 kbps–5 Mbps, 0–30%, via linkshaper) for stream-video-then-detect, detect-at-source + detections + thumbnails, and detect-on-companion.

### 6.4 G3: HUD user study ([hud §5](council/r1/hud.md))
| Item | Spec |
|---|---|
| Design | Within-subjects, counterbalanced. **Glasses HUD vs the same E.D.I.T.H. software on a chest-mounted phone (`generic` flavor) + earbud** (C21), both driven by one CoT scenario. Optional ablation: ranked vs all alerts. ATAK-CIV shown only in SME think-alouds |
| N | **18 target** (paired, d=0.7, 80% power); **floor 12** with effect sizes and CIs (C22); plus 3–5 SME think-alouds (ROTC/veterans as civilians) |
| Protocol | 10-min scripted scenario walking a marked indoor or Penn Park loop. Stressors: call-sign dual task, 75–80 dB(A) noise, time pressure, a dusk block. Tasks: respond to alerts, navigate to bearings, issue 4 confirmed drone tasks, call out peripheral LED events. Lures: "confirm"/"cancel" spoken by script or confederate while a card is open |
| Measures | Alert response time, hits/misses/wrong actions; SAGAT (3 freezes); SART, raw NASA-TLX, SUS, SSQ; heads-up time from IMU pitch; walking speed; peripheral detection; accidental confirms; 2 s legibility |
| Analysis | Mixed model on response time; Wilcoxon on questionnaires; exclude photosensitive epilepsy; record acuity and color vision |
| Optional G2 block | 10 min: B0 feed grid on a laptop vs E, operator-reported events |

**IRB timeline** (owner Alisha, with Prof. Zhao as faculty PI; the PI requirement is UNVERIFIED):

| Date | Step |
|---|---|
| Dec 4 | Request a determination; at Penn, exemption is not self-determined ([Pennbook](https://catalog.upenn.edu/pennbook/human-subject-research/)). Likely Exempt Cat. 3, possibly expedited because of walking plus noise |
| Dec 18 | CITI training done (all 5) |
| Jan 8 | Protocol + consent + recruitment text submitted |
| Feb 19 | Approval target (before the W6 pilot) |
| Feb 22–28 | Pilot with 3–5 users |
| Mar 15–Apr 4 | Main study |

Budget: about 23 × $20.

### 6.5 G4: cost model outline ([pm §1.7](council/r1/pm.md))
- **Anchors:** IVAS was up to $22B for ~120k headsets (lifecycle value, not unit price; hardware ~$80k/unit); Skydio X10D ≈$21k/system. Compare unit to unit and lifecycle to lifecycle.
- **BOM lines per kit:** glasses, companion EUD, radio (usually already owned), software per seat-year, power/cables, training/sustainment, amortized accreditation; drones separate.
- **Scenarios:** incremental kit ≈$7–12k (trusted glasses $2–5k + EUD $1.5–2.5k, both UNVERIFIED, + software $3–5k/seat/yr); full kit ~$25k only with a MANET radio (pricing UNVERIFIED); lite kit ~$8k (e.g. goTenna Pro X, $849).
- **Unit economics:** software ARR per seat; hardware pass-through at 15–25%; 30–100 seats per pilot; sales-cycle cash. **Phase 0 spend:** RayNeo $1,099–1,399 plus <$2k accessories. **NC-data line:** Phase 1 retraining on owned/synthetic data.

---

## 7. Semester plan

Penn Spring 2027 starts **Wed Jan 20**, spring break is Mar 6–14, and the last class is May 4 ([pm §1.5](council/r1/pm.md); UNVERIFIED against the Almanac; C23). Planning assumptions: final demo the week of Apr 26, feature freeze Apr 16, demo freeze Apr 23.

**Owners:** **Arjun** HW/platform, HAL, power, network, SITL host, mmWave · **Anshuman** vision/ML, architecture, integration lead, edge vs offload · **Alisha** HUD UX, alert policy, IRB, study · **Om** voice/NLP, grammar, confirmation safety, noise eval · **Simon** systems/commercial, CoT/ATAK interop, cost model, interviews/CRM, demo narrative.

### 7.1 Now → December

| Dates | Work | Owner | Gate |
|---|---|---|---|
| Nov 23–29 | Council builds Phase B (D0–D13). Draft the IRB determination request; interview list; buy router, power bank, USB-C data cable, SPL meter, speaker, IR thermometer | Council; Alisha; Simon; Arjun | — |
| ~Nov 30–Dec 4 | **Glasses arrive → day-one bring-up** (D13: T0–T18, B1–B6). Retire A1. IRB request sent Dec 4 | Arjun lead; Om (T9/B*); Alisha (T5/T16); Anshuman (T18) | — |
| Dec 5 | A2: battery/thermal for a 10-min demo + 20-min session (T14/T15) | Arjun | — |
| Dec 10 | **G0 platform go**: T5/T6/T7/T9/T13 pass or a workaround is chosen (SBS vs mono, PTT hold vs toggle). Native Kotlin confirmed; Unity closed | Arjun + Anshuman | G0 |
| Dec 12 | A3: mic ASR at ≥85 dB(A) (20 commands × 5 levels × 3 speakers). A4: link p95 voice→HUD ≤2.5 s. Contracts v0 frozen | Om; Arjun; Anshuman | — |
| by Dec 17 | Semester-1 deliverable: PLAN + hardware characterization memo + ≥5 interviews | All; Simon | — |

### 7.2 Winter break (Dec 18 – Jan 19)
Arjun holds the glasses; everyone else uses the emulator and the `generic` flavor.

| Person | Break deliverable |
|---|---|
| Arjun | Walking skeleton on the glasses; on-glasses TFLite numbers (T18) |
| Anshuman | VisDrone fine-tune run #1 (Colab/Penn); `bench goal2` baseline |
| Om | ASR bake-off on synthetic + B6 data |
| Alisha | HUD v1 from T16 daylight data |
| Simon | ATAK-CIV interop on the LAN; cost model v0; ≥10 interviews |

**Exit gate G1 (Jan 19):** walking skeleton end to end on the glasses: voice → confirm → SITL → HUD → ATAK.

### 7.3 Spring 2027

| Wk | Dates | Milestones (owner) | Gate |
|---|---|---|---|
| 1 | Jan 20–24 | Skeleton demo to the TA; contracts v1 frozen (Anshuman); IRB status (Alisha) | Fri integration #1 |
| 2 | Jan 25–31 | Glasses-mic noise corpus v1 at 60/75/85/95 dB(A) (Om, Arjun); HUD v1 layout on device (Alisha); on-glasses bench JSONL (Arjun, Anshuman) | — |
| 3 | Feb 1–7 | ASR engine chosen; grammar v1 frozen (≤20 intents) + Vosk confirm (Om); fine-tuned triage baseline (Anshuman); CoT→ATAK-CIV live (Simon) | Fri integration #2 |
| 4 | Feb 8–14 | **G2 gate**: WR ≥80% at recall ≥90% on replay, else fallback (D-FINE tier, more tiles, narrower claim) (Anshuman). Link-degradation profiles (Arjun). Sim+real training mix starts | G2 |
| 5 | Feb 15–21 | Touch fallback for every intent (Alisha, Arjun); ranker v1 tuned (Anshuman, Alisha); IRB approval target Feb 19 | Fri integration #3 |
| 6 | Feb 22–28 | Pilot study, 3–5 users (Alisha); mmWave go/no-go (Arjun); cost model v0 review (Simon) | — |
| 7 | Mar 1–5 | **G3 feature-complete v1**; eval harnesses automated (all); internal demo | G3 |
| — | Mar 6–14 | Spring break: nothing scheduled | — |
| 8 | Mar 15–21 | Pilot fixes; **operating point frozen** (Anshuman); edge-vs-offload + Pareto runs (Anshuman, Arjun); study sessions begin (Alisha) | — |
| 9 | Mar 22–28 | Main study (Alisha lead; all run sessions) | — |
| 10 | Mar 29–Apr 4 | Main study completes (N=18 target) | — |
| 11 | Apr 5–11 | Noise curve + false-activation results (Om); G2 report (Anshuman); study analysis (Alisha); cost model v1 (Simon) | — |
| 12 | Apr 12–18 | **Feature freeze Apr 16**; dry run #1 with mentor/TA | G4 |
| 13 | Apr 19–25 | **Demo freeze Apr 23**; backup video of every live segment; poster/report; dry run #2 | G5 |
| 14 | Apr 26–May 2 | **Final demo** (date to confirm with course staff) | — |

**Final demo** (~8 min; [pm §1.6](council/r1/pm.md), [defense_sme §1.4](council/r1/defense_sme.md)): problem → one architecture slide → **live**: beside 85 dB(A) babble, "Drone one, scout NAI one" → card → CONFIRM, drone moves in SITL and stock ATAK-CIV; vehicle alert → WATCH/MARK; planted false positive → DISMISS; a judge reads a paragraph full of "confirm/drone/go" and nothing executes; same task silently by touch; jam → degraded → resync with original timestamps; "attack" → Unsupported; triple-tap ALL HOLD → evidence slides (G1 curve, G2 WR vs recall, G3 A/B, Pareto) → cost model and roadmap, with the same APK on a phone → scope-boundary slide. A SAR "missing hiker" re-skin is scripted too.

---

## 8. Long-term direction

| Phase | Scope | Gate to enter next |
|---|---|---|
| **0 (this year)** | Three core loops in simulation; operator-tested HUD; cost model | **May 2027:** G1–G3 targets met or honestly reported; ≥15 interviews (≥3 operators/drone users); ≥1 LOI or pilot conversation (DIU, SOFWERX, fire/SAR); portability proven (RayNeo-specific LOC <5% and the same APK on a phone); full-time decision; Penn IP policy checked |
| **1 (6–12 mo)** | Trusted-hardware port; companion on Android EUD or ARM64 Linux; ATAK plugin v0; first real flights with a Blue UAS drone at a range; retrain on owned data; TLS 8089 + mTLS | SBIR Phase I / DIU CSO award + field test |
| **2** | Squad-leader workflows, deep ATAK integration, ATO/RMF path (NIST 800-53, FIPS 140-3, STIGs, encryption at rest, signed builds), offline sync at scale | Accreditation sponsor |
| **3** | Multi-asset ISR tasking (every task still human-confirmed), team mesh, lite SKU | Program of record conversation |

**Trusted hardware path:** only `platform-rayneo` is replaced by a new `platform-<vendor>` module. Candidates: Vuzix (US waveguides; Collins dismounted-soldier display), DigiLens ARGO (XR2, 30° FOV; build location UNVERIFIED), ThirdEye X2 (NJ; TAA ≠ US-made). Audit components, not just brands, against 1260H; the June 2026 additions included display makers ([pm §1.1](council/r1/pm.md)); TCL's status is UNVERIFIED. The companion moves to an ARM64 box or Android EUD (pymavlink and MAVSDK both ship aarch64 wheels).

**ATAK plugin path (the wedge):** Phase 0 needs CoT only. Phase 1 ships a phone-first **voice-tasking and feed-triage ATAK plugin** built on the ATAK-CIV SDK from tak.gov (the GitHub repo was archived May 2025) and signed through TAK.gov third-party signing; the glasses become the upgrade. This has the lowest adoption friction and survives losing the glasses A/B test. Moat candidates: integration breadth (Blue UAS adapters, CoT, MAVLink), published voice-tasking safety evidence, the WATCH/DISMISS feedback data loop (if data rights allow), and ATO.

**Dual use and buyers:** SAR and wildland fire first; law enforcement last (no ID, published retention, audit logs). DIU's drones/autonomy portfolio (**never as a kill-web component**), SOFWERX assessment events, the next xTech cycle, SBIR/STTR (foreign-ties screening; clean cap table).

**What not to build:** weapons, targeting, fires/CAS hooks or target handoff; automatic hostile classification; countermeasure actuation; face, biometric or re-ID; 6DoF anchoring in Phase 0; swarms before Phase 3; a free-form LLM as primary control; cloud dependence; our own drones, radios, glasses or map engine; a general chatbot; DJI/Autel SDKs. Staying inside DoDD 3000.09's exclusions depends on never adding effects ([defense_sme §1.7](council/r1/defense_sme.md)).

---

## 9. Risk register (top 10)

| # | Risk | Owner | L | I | Mitigation |
|---|---|---|---|---|---|
| 1 | RayNeo display/input/mic differs from docs: SBS size, long-press stolen, audio mode string (UNVERIFIED) | Arjun | M | H | `DisplaySink.stereoMode` runtime switch; toggle-PTT fallback; standard `VOICE_RECOGNITION`; day-one T5–T9; G0 Dec 10 |
| 2 | One pair of glasses breaks, is lost or is monopolized | Arjun | M | H | `generic` flavor on phones; SBS emulator; sign-out log; budget ask for a second unit (Q3) |
| 3 | Battery/thermal shorter than a session (~30 min continuous video per reviewers) | Arjun | H | M | Camera off by default; transient inset; 30 fps cap; power bank; thermal policy; sessions ≤30 min |
| 4 | ASR fails in noise through glasses mics | Om | M | H | PTT; constrained grammar + hotwords; per-slot say-again; named points over grids in the demo; close-talk BT headset fallback; touch path |
| 5 | Unsafe or accidental command execution | Om, Anshuman | L | H | Two-press confirm, lockout, nonce, 10 s expiry, closed-grammar agreement, invariant monitor, adversarial suite; stop = hold only |
| 6 | COCO models miss small aerial targets; no GPU here | Anshuman | H (measured) | M | Tiling now; VisDrone fine-tune W1–4 on Colab/Penn; recall by pixel height; G2 gate at W4 with fallbacks |
| 7 | IRB delay or no relevant participants | Alisha | M | H | Request Dec 4; submit Jan 8; civilian student pool with cadets/veterans as civilians; floor N=12 |
| 8 | Integration slip; no skeleton by Jan 19 | Anshuman | M | H | Frozen contracts; Phase B e2e already green in CI; Friday integrations; G1 gate |
| 9 | Perceived as weapons, a toy, or China-dependent; export-control slip | Simon | M | H | Unknown-only detections, no effect verbs, scope guard in code, "watch" vocabulary, boundary slide, portability proof, public data only (no CUI/ITAR) |
| 10 | PX4 SIH packages (v1.18 RC) misbehave or can't run here | Arjun | M | M | MockVehicle carries CI; pin the deb by sha256; source-build recipe; Docker image on Mac/Win |

Watch list: magnetometer heading error (uncertainty gate and text-bearing fallback); Wi-Fi jitter at the venue (dedicated router); NC-data commercialization (provenance tracking + retrain); Compose drawn twice too slow (View/Canvas backend).

---

## 10. Open questions for the human team

1. **Workspace approvals:** may the council run the extracted PX4 SIH binary here (D15), and optionally `apt install gz-harmonic` for a 10-minute llvmpipe probe? Without it, Tier A is verified only on team laptops.
2. **Course logistics:** what is the exact final demo date and format (SEAS-wide competition or the department's own), and what are the required deliverables (report, poster, video)?
3. **Hardware budget:** is there money for a second display device (backup and portability proof) and for the ~$2k of accessories? Does a teammate have an Android phone for the `generic` pre-flight, the chest-phone study arm and the ATAK-CIV interop phone?
4. **Compute:** is Penn GPU access available (which cluster, what quota) for S2 fine-tuning, or do we budget for Colab? Does any team laptop have an NVIDIA GPU with native Ubuntu 24.04 for Tier B? How many members are on Apple silicon or Windows?
5. **Mentor expectations:** does Prof. Zhao want a research contribution (the Pareto study or the mmWave ground sensor) or a product demo? Will he agree in writing, before Jan 20, that "SITL + real recorded footage" counts as proof for G1/G2? Will he serve as IRB PI?
6. **Vendor terms:** RayNeo SDK redistribution terms. Arjun to ask RayNeo; until then it is fetched by script, never committed.
7. **Post-May:** who intends to go full-time, and what does Penn's IP policy say about student project IP?

Not open questions: operator-dependent choices (confirm vocabulary CONFIRM/CANCEL vs EXECUTE/DISREGARD, MGRS precision, TTS on/off, alerts-per-hour budget) are settled by interviews and the pilot, with defaults already in config.
