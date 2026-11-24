# E.D.I.T.H. — Phase 0 Plan (v3)

Status: v3, 2026-11-23. Closes the round-3 issues ([r3/](council/r3/)) with the smallest edits to v2 under lead rulings L25–L27 (converge; no new features). Every resolution is logged in [DECISIONS.md](council/DECISIONS.md) (`L*` = lead ruling, `C*` = council resolution) and indexed issue by issue in [r3/RESOLUTION.md](council/r3/RESOLUTION.md) (round 2: [r2/RESOLUTION.md](council/r2/RESOLUTION.md)). Normative detail lives in five spec files that this plan links to:
- [interfaces](spec/interfaces.md)
- [voice](spec/voice.md)
- [hud](spec/hud.md)
- [sim](spec/sim.md)
- [eval](spec/eval.md)

Tags: **UNVERIFIED** = not yet confirmed. **[probed]** = measured in this workspace by a council member.

---

## 0. Summary and goals

E.D.I.T.H. is a voice-first operator layer.

- **Glasses.** The RayNeo X3 Pro is a thin client: screen, ears and eyes, never the brain.
- **Companion.** A pure-Python service owns all state. It runs on a laptop in Phase 0 and on an Android phone or ARM box in Phase 1. It holds:
  - the world model;
  - voice→intent;
  - the safety gate and confirmation FSM;
  - MAVLink asset control;
  - edge perception on drone video;
  - alert ranking;
  - the TAK/CoT bridge;
  - store-and-forward.
- **Drones are simulated only.** Tier 0 is MockVehicle, the CI and default tier now. Tier A is PX4 SIH, gated on approval (L14). Tier B is Gazebo on a GPU laptop.
- **Detections are always published as unknown.** Only a human reclassifies.
- **Confirmation.** Every motion command needs a read-back the glasses confirm they displayed, plus an explicit confirm. The only exception is the HOLD/ABORT safety stop, which only removes motion (L1).
- **Scope limits.** No weapons, targeting or engagement. No face or biometric ID. No real flights (L10).
- **Everything runs offline.**

| Goal | Pre-registered target | Evidence |
|---|---|---|
| **G1** One operator directs a drone by voice from the glasses | Intent success ≥90% on naive study participants' utterances (≈144, 75–80 dB(A) Leq30 at the ear), and separately ≥90% on the B6 engineering corpus at 85 dB(A). p95 end-of-speech→card ≤1.5 s (ceiling 2.5 s), idle and under `edith up`. Confirm→sent ≤500 ms. **0 executions without a valid confirmation** across the audio lure suite (≥480), the 10,000 text suite and ≥2 h of chatter. Confident-wrong ≤0.5% at 10 dB SNR | Study log; `bench goal1`; audit log ([eval §1](spec/eval.md#1-g1-voice-tasking-c69)) |
| **G2** AI filtering cuts the video the operator must watch | WR ≥80% at event recall ≥90% on composed real-footage missions at 10% duty cycle (curve at 5/10/20%). FA ≤6/h per drone over real seconds (point estimate; exposure hours and Poisson CI reported, C100). Median TTD ≤3 s. CEP90 ≤30 m on synthetic missions with nav noise | `bench goal2` ([eval §2](spec/eval.md#2-g2-watch-reduction-c70)) |
| **G3** HUD stays readable and safe under stress | Alert response ≥20% faster than the phone-native arm with the same PTT and earbud, or an honestly reported null. SAGAT non-inferior within 5 points. TLX no higher. **0 accidental confirms in ≥192 lures** (95% UB 1.6%). Wrong-read-back catch rate reported. Row 1 read correctly within 2 s in ≥95%. APL ≤13% | N=18 study ([eval §4](spec/eval.md#4-g3-hud-user-study-c72)); golden lints |
| **G4** Cost model and roadmap | Capex per kit, opex per seat-year and 5-yr TCO, all sourced or UNVERIFIED. Phase 1–3 roadmap with gates | `docs/cost/model.csv` + `cost_model.py` ([eval §5](spec/eval.md#5-g4-cost-model-c79)); §8 |

---

## 1. Architecture

### 1.1 Layers

| Layer | Phase 0 realization | Owns |
|---|---|---|
| 1 Glasses | Kotlin app: `rayneo` flavor on the X3 Pro, `generic` on any Android phone, or the desktop emulator | Rendering `HudState`; head-relative transforms (tape, heading-up map, caret, clock wording); mic with PTT pre-roll; IMU; temple and BT-key input; staleness display. No mission logic and no mission data at rest |
| 2 Companion | `edith_companion` (Python 3.13, asyncio) on a laptop | All policy (list above) plus the event log and the `/ui/touch` fallback |
| 3 Mesh | LAN Wi-Fi on a travel router. CoT over UDP multicast in the field, mesh-emu through linkshaper in sim and CI (C54). OTS optional (L7) | Team picture; keepalive link monitor; store-and-forward |
| 4 Assets | MockVehicle ×N now; PX4 SIH ×N once approved; both behind `AssetAdapter` and a shared `edith_common.px4` profile (C62) | Flight behaviour, failsafes, video |

**Design rule:** policy lives on the companion and layout lives on the glasses. The companion decides *what* is shown: one alert, the card, the inset, the entities. The glasses decide *where the pixels go*. Policy is unit-testable in Python, and the renderer stays dumb and portable.

### 1.2 Diagram

```
 ┌──────────────── Glasses (RayNeo X3 Pro / phone / emulator) ────────────────────────────────┐
 │ hud-core (GraphicsLayer → StereoCompositor SBS|MONO) · InputFsm(dispatchTouchEvent, BT key)  │
 │ PoseSource 3DoF · MicSource (500 ms pre-roll ring from finger DOWN) · CameraSource (bench)    │
 └───────▲ hud.state ≤10 Hz · voice.partial ≤2 Hz · video.down JPEG 320×240 ───┬───────────────┘
         │                WebSocket :7400 /v1/ws                               │ input.event · audio.up (PTT only)
         │                                                                      ▼ hud.event (card_shown!) · head.pose
 ┌───────┴──────────────────────── Companion (edith_companion) ─────────────────────────────────┐
 │ gateway ─ voice(VAD→ASR→normalize[spoken|written]→Lark→resolve) ─ safety(gate, FSM,          │
 │   confirm_rule, stop) ─ assets(AssetAdapter → outbound classifier MOTION|SAFE|CONFIG) ──┐    │
 │ hud projector ◄ alerts(ranker) ◄ perception(FrameSource|OffloadDetector → detector →    │    │
 │   ground-plane tracker → geo CE90 → fusion → friendly association)                     │    │
 │ eventlog (SQLite WAL) · tak(CoT, scope guard, LinkMonitor, outbox) · http :7401         │    │
 └──────▲ RTP :5600+i (SEI frame_id) · sidecar :5700+i · Detections :5800+i ───────┐     │    │
        │                                       CoT mesh-emu :16968⇄16969 ─┐     │     │ MAVLink udpin :14740+i
 ┌──────┴────────────────────────── Sim (edith_sim) ───────────────────────┼─────┼─────┼────────┐
 │ scenario runner (ScaledClock) · mover · simd cameras + gt_detector ◄─ truth tap :14640+i     │
 │ linkshaper (MAVLink 14540+i⇄14580+i, tak, video windows; mavlink_wire.jsonl) · fake CoT     │
 │ router :18088/:18087 · teammate sim · MockVehicle ×N (or PX4 SIH ×N) · gt_events.jsonl       │
 └──────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 1.3 Demo topology

| Box | Runs | Network |
|---|---|---|
| Demo laptop (native Linux, designated by Dec 12, C78) | Companion, PX4 SIH ×2 (or Mock), simd, linkshaper, teammate sim, scenario runner; god-view on the projector | Wired or 5 GHz to the travel router |
| RayNeo X3 Pro | `rayneo` APK, provisioned by `adb shell am start … --es ws … --es token …` (C76) | 5 GHz Wi-Fi |
| ATAK-CIV phone | Stock ATAK-CIV, mesh SA | Same Wi-Fi (multicast) |
| Forearm phone (fallback) | `/ui/touch` if T7 disables temple confirm (C65) | Same Wi-Fi |
| Optional TOC laptop / GPU laptop | OTS or WinTAK; Tier B Gazebo | TCP 8087; RTP 5600+i |
| Travel router (~$35) | No internet; phone hotspot as field fallback | Venue Wi-Fi never used |

### 1.4 Core loops

| Loop | Flow | Budget |
|---|---|---|
| **1 Voice → confirm → drone** | Finger DOWN on the right pad → mic opens into a 500 ms local ring → at 300 ms held, `ptt_down{held_ms, ctx}` + pre-roll frames, then live `audio.up` (a second pointer or an early UP discards the buffer; nothing leaves the device) → release + 150 ms tail → ASR final (partials ≤2 Hz) → normalizer profile → Lark → resolver (heading snapshot at release) → gate → `CommandProposal` → card → glasses send `hud.event{card_shown}` → 600 ms lockout → confirm per the rule on the joined session text, with every press method gated alike ([voice §5](spec/voice.md#5-confirmation-c48-single-owner-companionedith_companionsafetyconfirm_rulepy)) → gate re-check → DISPATCHED → MOTION messages leave via the outbound classifier → `Execution` per step → `COMMAND_ACK` → completed. **Safety stop:** a stop utterance (grammar or spotting), triple-tap or companion HOLD ALL cancels adapter repeating tasks and retries, sends hold to every scoped airborne asset with a live link, and supersedes any pending proposal (L1, L16) | Card ≤500 ms p50 / ≤1.5 s p95; confirm→sent ≤500 ms (incl. mission upload); stop ≤500 ms |
| **2 Video → alert → HUD/TAK** | RTP H.264 + SEI frame_id on 5600+i and sidecar `pose_est` on 5700+i → latest-frame FrameSource (or `[Detection]` on 5800+i from gt_detector/offload) → scheduler (2 Hz default, 4 Hz tasked, 1 Hz idle, 4 Hz for 5 s after any unconfirmed detection, capped at 1 Hz while PTT is down) → YOLOX-Tiny tiles → geo-project → **ground-plane ENU Kalman tracker** → confirm 3/5 → fusion, novelty, **friendly association** → ranker → one banner + inset policy; CoT `a-u-*` `how=m-f` to the mesh. Operator WATCH / MARK / DISMISS (DISMISS retracts the CoT) | TTD ≤3 s median; capture→alert ≤1.5 s p95 on a team laptop |
| **3 Jamming → degraded → resync** | Scenario `jam` → linkshaper drops `mavlink:drone2` and `tak:*` → MAVLink: `degraded` after 1.5 s of silence, `lost` at `COM_DL_LOSS_T` → PX4/Mock hold AUTO.LOITER for `COM_FAIL_ACT_T` (5 s), then run `NAV_DLL_ACT`=Return, which persists after the link returns (C89) → HUD greys D2, "D2 LINK LOST · RTL 0:12", D2 proposals invalidated, holds for D2 are not queued → TAK `LinkMonitor` sees no pong for 3 s → `lost` → outbox queues → window ends → pong returns → `ok` → outbox replays the lookback window, then the queue, then the latest live-track states, in order with original `time`, dropping expired events | TAK `lost` ≤3 s; `ok` ≤2 s after the window; order 100% on the router log |

**Glasses↔companion loss:**
- The glasses keep the last snapshot and grey it after 3 s, with "COMPANION LOST — LOCAL ONLY" and a live tape.
- The companion expires the pending proposal.
- On reconnect: `sys.hello`, then a snapshot.
- Commands never queue across a disconnect.

---

## 2. Interfaces

Full tables are in [spec/interfaces.md](spec/interfaces.md). The binding points:

- **Clock (C61).**
  - The supervisor exports `EDITH_T0_NS` and `EDITH_SPEED`, and every process uses `ScaledClock`: `now = T0 + (wall − T0)·speed`, so `ts_ms` stays epoch-like (C94).
  - `--assets px4` forces `--speed 1`. The supervisor refuses `--emulator` or real glasses at speed ≠ 1, because glasses durations are wall ms.
  - `--allow-text-injection` is set only with `--headless`, and the gateway then refuses glasses/emulator hellos (C87).
  - Only durations (`held_ms`, `duration_ms`, `expires_in_ms`) cross the glasses link. Clocks are never compared.
- **Geo.**
  - WGS-84; MGRS for display and voice only; metric units (L2).
  - `hae = MSL + N` (site constant; EGM96, UNVERIFIED).
  - `ce_m` is always **CE90**, with σ = ce_m/2.146; CoT `ce` = ce_m (C57).
- **Schema.**
  - JSON Schema 2020-12 in `schemas/v1/` is the source of truth.
  - Pydantic and kotlinx models are hand-written and contract-tested on shared fixtures (C27).
- **Schema changes in v2 (C64):**
  - `CommandProposal.state` ends at `dispatched`. After that, one `Execution{step_idx}` per step carries the lifecycle.
  - `HudState.proposal.state` adds `lockout|sent|acked|no_ack|not_sent_timeout`.
  - `HudState` also gains `alert.ce_m`, `alert.gesture_dismiss`, `entities[].marked`, the enum `carets[].style` and `undo`.
  - `Track` gains `assoc_friend_uid`, `geo_quality` and `cot_uid`.
  - `input.event` gains `gesture_seq`, `held_ms` and `pointer_count`, plus the BT PTT kinds.
  - `FrameMeta` carries `pose_est` and `gimbal.mode`.
  - `FrameTruth` is sim-internal.
- **Ports.** The spec gives a bind/send table for every port (C77). New ports:
  - 5800+i: gt/offload Detections.
  - 14640+i: truth tap.
  - 16968/16969: mesh-emu.
  - 18088: router fan-out.
  - 14550 must be free (`doctor` fails otherwise).
  - Linkshaper binds 14540+i, the vehicle binds 14580+i, and the companion `udpin`s 14740+i with sysid 245.
- **Structural verb allowlist:** `takeoff, goto, orbit, observe, search, follow, hold, rtl, land`. No field, enum or adapter method exists for weapons, payload release or countermeasures.
  - `follow` takes only a friendly uid stream (C51) and is a stretch goal (L8).
  - `observe contact` uses the position frozen at confirm (L16).
- **Outbound classifier (C50).** Every adapter message is MOTION, SAFE or CONFIG; anything else is dropped.
  - MOTION: arm, takeoff, reposition, orbit, mission upload/clear/start, rtl, land, speed, any mode ≠ LOITER. It needs a dispatched, validly confirmed proposal that postdates any stop on that asset.
  - SAFE: LOITER hold.
  - CONFIG: heartbeat and message intervals any time; params and fence only while disarmed.
- **CoT.**
  - Machine contacts: `a-u-G-E-V` / `a-u-G`, `how=m-f` (UNVERIFIED), uid `EDITH-<companion>-trk-<id>`.
  - DISMISS emits `t-x-d-d` + `__forcedelete` within 1 s (fallback: `stale=now`) (C53). Loss deletes only unmarked `m-f` tracks. A MARKed (`h-e`) track is never auto-deleted: on loss it is re-sent once as `LKP <DTG>` with its 900 s stale (C99).
  - The DISMISS disc also gates CoT, so a re-acquired dismissed object is not re-published (C99).
  - Friend-associated tracks are never published (C52).
  - Sim teammates are VIKING 1-2…1-4 with `how=m-s`, `EXERCISE` remarks and PLI every 2 s (C55, C98).
  - Inbound accepts XML and TAK Protocol v1 via `takproto`.

---

## 3. Component specs

### 3.1 Companion modules (`companion/edith_companion/`)

| Module | Owner WS | Responsibility |
|---|---|---|
| `gateway`, `bus`, `eventlog`, `world`, `config` | B | aiohttp WS :7400 + HTTP :7401 (`/ui/touch`); pub/sub; append-only SQLite audit log; world snapshot; one YAML config |
| `assets` | B | pymavlink `AssetAdapter` (search via the shared `plan_search`), `outbound.py` classifier, GCS heartbeat, MAVLink link monitor, fence + `GF_*` push with read-back (profile params are applied only by the sim launcher, C90) |
| `voice`, `intent` | C | VAD, `AsrEngine`, normalizer profiles, Lark grammar, resolver, read-back rows |
| `safety` | C | Gate, proposal FSM, `confirm_rule.py` (the only home of the confirm predicate, C85), safety stop with task cancellation, invariant monitor |
| `perception` | E | FrameSource (RTP + SEI), OffloadDetector (5800+i), scheduler, detectors, ground-plane tracker, geo, fusion, novelty, friendly association, inset encoder |
| `alerts`, `hud` | H | Ranking, suppression, budget, card-open queueing, bare-response scoping; `HudState` projection, inset policy, declutter/night |
| `tak` | F | CoT build/parse, scope guard, transports (mesh, mesh-emu, tcp), LinkMonitor, outbox, retraction, inbound merge |

### 3.2 Voice pipeline

| Stage | Choice |
|---|---|
| Activation | **PTT only** (C35). Right-temple hold ≥300 ms **with a 500 ms pre-roll from finger DOWN** (C46). Toggle fallback (confirmed single tap, 8 s cap) if T7 shows the system owns long-press. BT HID PTT key for the study. Companion button |
| Capture | 16 kHz mono PCM16, 20 ms frames. RayNeo `audio_source_record` voice mode (string UNVERIFIED), with `VOICE_RECOGNITION` as fallback. SDK click sound off while armed |
| ASR | `AsrEngine`. **Moonshine Small Streaming via `moonshine-voice==0.1.6` is integrated first** ([probed]: installs on Py 3.13; finalize 133–174 ms). `sherpa-onnx==2.0.3` zipformer + hotwords is the biased alternative. The W3 bake-off picks the winner (C18). Moonshine has no Intel-macOS wheel, and `doctor` says so (C68) |
| Normalizer | Per-engine profile: `spoken` or `written` (C66); gazetteer aliases ([voice §1](spec/voice.md#1-normalizer-profiles-c66)) |
| Parse | Lark grammar v2 ([voice §2](spec/voice.md#2-grammar-v2-lark-earley)) with stop token spotting (C49) and the extended rejected lexicon (C66) |
| Confirm | Exact normalized `confirm` over the **joined session text** (every ASR line of the press, C101), after `card_shown` and outside lockout, with no confidence threshold where the engine has none. P1 adds AND-agreement from `vosk==0.3.45`'s closed grammar **with decoys** (C48) |
| Partials | ≤2 Hz (each Moonshine partial costs ~230 ms of CPU [probed]) |
| LLM | Deferred to a semester-2 stretch, GBNF-constrained and re-parsed (C20) |
| TTS | Off by default (C19). Never the `piper-tts` package (GPL) |

Latency budget (end of speech → card): 150 ms tail + ASR final ≈170 ms + parse/gate 30 ms + render ≈20 ms ≈ **400–500 ms p50, ≤1.5 s p95**. D10a measures it both idle and under `edith up`.

### 3.3 Grammar summary

The grammar is in [voice §2](spec/voice.md#2-grammar-v2-lark-earley).

- **Callsigns:** D1–D4. There is no broadcast tasking.
- **Verbs:** take off/launch, go to, orbit, watch/overwatch/observe (point or frozen contact), search/scout/scan, follow (me/teammate; stretch), return, land.
- **Locations:** my position, teammate, clock+range, grid, named (with aliases), relative.
- **Stops:** `[all [drones] | callsign] stop_word+ [position]`, plus token spotting.
- **Bare responses:** apply only to the displayed alert (or the one WATCH pinned). While a card is open the banner is hidden, so they are NOOP + `NO ALERT` (C101). Bare `watch` moves nothing (C03).
- **Rejected:** out-of-scope verbs (the C66 lexicon) return `REJECTED: "Unsupported command"`, and nothing is sent.

### 3.4 Safety state machine

```
Voice:     IDLE ─ptt_down→ LISTENING ─ptt_up+150ms→ PROCESSING → PROPOSED | SAY_AGAIN(≤2/slot) | REJECTED |
           STOP_EXECUTED | RESPONSE_APPLIED | NOOP
Proposal:  PROPOSED ─card_shown + 600 ms→ AWAIT_CONFIRM ─valid Confirmation→ CONFIRMED ─gate re-check→ DISPATCHED
           (then Execution per step: sent → accepted → in_progress → completed|failed|aborted)
  exits: CANCELLED (cancel | double-tap held 400 ms | companion) · EXPIRED (ptt_up not received by 10 s after card_shown) ·
         SUPERSEDED (new command | stop) · INVALIDATED (WARNING | glasses drop | asset link lost | gate fail)
Stop:      any state → cancel adapter repeating tasks + retries for scope → hold() to scoped airborne assets with link ≠ lost
           (lost → "D2 HOLD NOT SENT · LINK", never queued) ≤500 ms
```

- **Valid confirmation.** Defined once in `safety/confirm_rule.py`. Every press method (temple PTT, BT PTT, headless text `say`, two-finger hold, `/ui/touch`) obeys the same lockout, card-context and expiry rules. Lockout and card context gate only `confirm` and a superseding command; **stop and `cancel` always apply** (C101). The rule and the press-outcome table are in [voice §5](spec/voice.md#5-confirmation-c48-single-owner-companionedith_companionsafetyconfirm_rulepy).
- **Gate checks.** These run at proposal time and again before dispatch:
  - inside the AO and geofence;
  - 30–120 m AGL (default 60);
  - ≤1,500 m from home;
  - battery ≥30% for a new task;
  - asset link `ok`;
  - track age <30 s for `observe contact`;
  - orbit radius 30–300 m;
  - follow only of a friendly uid with PLI <30 s and standoff ≥30 m;
  - the verb is valid in the current state (landed ⇒ compose takeoff, C09).

**Invariants.** Each is checked by Hypothesis property tests and by a runtime monitor that raises a WARNING and logs on violation. Wire-level invariants are checked against the linkshaper `mavlink_wire.jsonl`, an independent witness.

| ID | Invariant |
|---|---|
| I1 | No MOTION message reaches an asset unless it belongs to a DISPATCHED proposal with a valid Confirmation |
| I2 | Unconfirmed outbound messages are only SAFE or CONFIG (C50) |
| I3 | At most one live proposal |
| I4 | No command survives a glasses disconnect |
| I5 | Every transition is in the event log |
| I6 | `affiliation_src=machine ⇒ affiliation=unknown` |
| I7 | After a SafetyStop at t_s on asset *a*, no MOTION reaches *a* unless it comes from a proposal confirmed after t_s. `stop()` cancels follow re-issues, retries and pending uploads before sending the hold (L16) |
| I8 | A track with `assoc_friend_uid` is never alerted or published (L17) |

### 3.5 ML pipeline

| Item | Decision |
|---|---|
| Classes | `person` and `vehicle`. COCO animals map to `other` and are never alerted. No drone class. No face, ID or re-ID ever (C16) |
| Companion default | **YOLOX-Tiny (Apache-2.0)** on a 2×2 grid of 692×389 tiles (15% overlap) from 1280×720, ORT CPU, 1 thread. P0 runs the official static 416² ONNX (letterbox scale 0.60). **P1 runs 576×320** exported from the Apache PyTorch weights (scale 0.82; cost UNVERIFIED), with 416² kept as the fallback (C58) |
| Glasses candidate | YOLOX-Nano → TFLite fp32/fp16/int8 (D14) |
| Accuracy tier | D-FINE-N companion-only; RT-DETRv2-R18 as offline teacher |
| Forbidden | Ultralytics (AGPL); NC-derived weights in any APK or wheel (lint, C84) |
| Thresholds | Output floor 0.10; tracks start at ≥0.25; cross-tile merge by IOS ≥0.5; confirm ≥3 hits in 5 with mean conf ≥ τ_c (person 0.30, vehicle 0.35, swept, frozen at W8) |
| **Tracker (L19, C56)** | In-repo **ground-plane tracker**: geo-project each detection, constant-velocity Kalman in ENU metres, same class, Mahalanobis d² < 9.21 with σ from ce_m, plus a ByteTrack-style low-confidence second pass. Inset boxes are reprojected through the current FrameMeta. IoU is used only for the cross-tile merge. Roboflow `trackers` is an offline A/B only. Supersedes C17. **Replay feeds (`geo_quality: pseudo`, C95)** run the same tracker in a motion-compensated image plane: inter-tick homography (ORB+RANSAC at 640×360, ECC fallback) warps predictions, pixel Mahalanobis with σ = 0.1·box diagonal + 4 px, frames resized to 1280×720, tracks reset at every splice; pseudo geo is display-only |
| Geolocation (C57) | Pixel → ray (K, stabilized gimbal, optical x-right/y-down/z-fwd) → intersect the home-elevation plane; box bottom-centre; reject rays above −5°; h from `relative_alt`. CE90: σ_r = (h/sin²θ)·σ_θ ⊕ σ_h/tanθ ⊕ box term; σ_x = R_slant·σ_ψ; ce_m ≈ 2.146·√((σ_r²+σ_x²)/2). The sidecar carries `pose_est` with nav noise, so CEP is not trivial |
| Fusion / novelty | Same class, Mahalanobis on combined σ, \|Δt\|<5 s, inverse-variance merge. Novel if no same-class track within max(15 m, ce_m) in 120 s |
| **Friendly association (L17, C52, C98)** | Each friendly PLI (teammates and self) is **dead-reckoned** to the detection time with `course_deg`/`speed_mps`. A `person` track within max(15 m, ce_m) + min(0.5 m/s·age_s, 15 m) of it gets `assoc_friend_uid`: no alert, no CoT, drawn as the friend. Affiliation stays `unknown` (I6). Association is evaluated in the update that confirms the track, before any alert. The PLI <30 s freshness test applies only to the **first** association; while `status.tak = lost`, PLI age is measured from the moment the link was lost. Association is **sticky**: it is released only after 3 consecutive updates beyond 2× the radius, or on track loss. Known limit: an unknown person within the radius of a teammate is masked (§9 watch list, scope slide) |
| Scheduler | 2 Hz/feed; 4 Hz tasked; 1 Hz after 30 s with no tracks; 4 Hz for 5 s after any unconfirmed detection; capped at 1 Hz on all feeds while PTT is down (C58) |
| Training (S2) | VisDrone-DET fine-tune W1–4, sim mix W4–7, on Colab or a Penn cluster (UNVERIFIED). `ml/models.yaml` records `license` and `derived_from` (C84) |
| Data | VisDrone CC BY-NC-SA, UAVDT research-only, Okutama no stated license: eval and research only, fetched by script with SHA-256 pins into gitignored `data/` (L9, L13) |

**Alert ranking** (C10, C11, C81):
- The tier wins outright.
- Within a tier: `score = 0.35·proximity + 0.20·closing + 0.15·recency + 0.15·novelty + 0.10·class_w + 0.05·conf`, with +0.1 for an AOI contact.
- A new alert pre-empts within a tier only if it scores ≥0.2 higher and the current one has been shown ≥3 s.
- DISMISS suppresses the track plus a 15 m same-class disc for 10 min, unless the tier escalates or the range closes ≥30%. The disc gates CoT publication as well as alerts (C99).
- More than 3 alerts of a tier in 10 s collapse into one.
- **Budget:** ≤2 alerts in any 60 s and ≤20/h mission mean; interviews set the final budget. In Phase 0 it is a **measured target, not a cap**: excess CAUTION/ADVISORY alerts queue and are never dropped (C100).

| Alert kind | Tier |
|---|---|
| contact_close (<150 m from the operator; `geo_quality=metric` only) | WARNING |
| geofence breach | WARNING |
| battery_low | CAUTION at 25%, WARNING at 15% |
| new_contact | CAUTION |
| link_lost, tak_link | CAUTION |
| task_status fail | CAUTION |
| task_status ack/complete | ADVISORY |
| teammate_stale | ADVISORY |

- While a card is open, CAUTION and ADVISORY alerts queue.
- A WARNING invalidates the card and **cannot be gesture-dismissed** (C47).

### 3.6 Simulation

Full detail is in [spec/sim.md](spec/sim.md).

| Tier | Autopilot | Camera | Use |
|---|---|---|---|
| **0 MockVehicle (default now)** | Pure-Python, pymavlink codec, `edith_common.px4` behaviour (incl. the `COM_FAIL_ACT_T` delayed hold and trapezoidal corners), reads `sim/profiles/quad_sim.yaml` | Synthetic, or video off with gt | Unit, contract, e2e, CI |
| A (P1, approval-gated, L14) | PX4 v1.18 SIH `.deb` (rc2 [probed]; pin the final release if out by Dec 12), same profile applied after boot by the sim launcher only and read back (C90) | Synthetic or replay | Dev, demo, G1/G2 |
| B (P2) | PX4 + Gazebo Harmonic, GPU laptop | Rendered gz camera, telemetry-interp pose | Visual polish |

- **One vehicle profile (L15, C62).** Climb 3 m/s and cruise 10 m/s are sim-tuned and disclosed. Mock and PX4 read the same keys. The contract suite runs against both, and `edith sim record-px4` captures the trace that Mock is diffed against.
- **Anchored expects (L15, C63, C88).** Expectations are anchored to scripted events or GT events (e.g. "within 5 s of D1's camera seeing veh-7 for ≥3 s"). `edith scenario lint` rejects kinematically impossible expectations. An expect's lower bound is the first time its predicate holds in a deterministic in-process pre-run, using a per-predicate latency table ([sim §6](spec/sim.md#6-anchored-expects-and-scenario-lint-l15-c63-c88)) whose compute latencies are multiplied by the scenario's `max_speed`. The +2 s margin applies only when the bound is >0.
- **Profile additions.** `COM_FAIL_ACT_T: 5` (PX4 holds LOITER 5 s before the DLL action [probed], C89) and `MPC_ACC_HOR` corners (C91).
- **Runner seams (C87).** The scenario runner hosts `FakeGlasses` (WS-B API): `say(text)` sends `ptt_down{held_ms 300, ctx}` → `voice.session.start{trigger: text}` → `voice.text` → `ptt_up`; `touch(kind)`; `on_card_shown`; `on_alert_shown`. Alerts map to GT entities by majority `det_id` (gt_detector's `gt_dets_<i>.jsonl` joined with the eventlog's `alert.created` and `track.update`), so no truth enters the companion. Tasking `say` events carry `cmd{asset, steps, target}`, which the pre-run flies with the shared `edith_common.px4.plan_search`.
- **Vignette.** The vignette was re-laid-out:
  - NAI 1 is 250 m from launch.
  - Both drones are tasked.
  - Teammates sit inside D2's overwatch footprint, which exercises friendly association.
  - It includes a timeout case, a dismiss with CoT retraction, a MARK that survives loss as an LKP, a jam with the delayed RTL, a rejected "attack" and a triple-tap stop.
  - `demo_live.yaml` has its own layout matched to the §7.3 beat sheet (veh-7 on leg 1, deer-1 on leg 2, the jam in the same file) and is checked by `lint --beats` (C92).
  - The timeline is in [sim §7](spec/sim.md#7-scenariosdemo_vignetteyaml-authored-in-d2).
- **Headless policy (L20, C59).**
  - Encoded video is off by default for `--headless --detector gt`. `video: off` means no pixels: FrameMeta and FrameTruth are analytic, nothing is rendered and no basemap is loaded. Without `data/naip`, simd uses a procedural basemap (C93).
  - gt_detector runs inside the sim and publishes `[Detection]` on UDP 5800+i to the companion's OffloadDetector, the same path as P3 offload.
  - Encoded video is capped at 15 fps of wall-clock time.
  - The vignette is synthetic on both drones, and replay appears only in `goal2_*`, so CI never needs `data/`.
- **Frame sync (C60).** An SEI `frame_id` precedes every access unit, with a pts anchor as the fallback. The supervisor writes the SDP files.
- **Site (C13).** Rural Piatt County, IL (origin 40.0700 N, 88.6300 W, 210 m MSL, MGRS 16TCK 61002 36799 [probed]); fictional named points.

### 3.7 HUD

Full detail is in [spec/hud.md](spec/hud.md). Binding changes (L22, C65, C102, C103):

- **Layout:**
  - The banner/card is fixed at 60,330–580,424, with rows of 28/20/20 px at pitch 32/24/24.
  - The clear zone is **190,150–430,326** (±4.5°). Drone chips stack at a 17 px pitch, ≤2 chips, then `+N D`.
  - The card has 3 rows (header + bar, row A, row B). The confirm hint moves to the voice row and is derived from `confirm_with`.
  - Read-back is `rows[2]`, each ≤490 px **measured** on the bundled B612.
  - **Banner row 1 is ≤470 px at 28 px** (only the 32 px tier glyph reserved; `~` dropped at ≥1 km). The `+N` queue moves to the right end of row 2, which is ≤400 px. Alert `label` is an enum, each value ≤160 px [measured r3]; the flood label is `<n> NEW`; kinds with no bearing render the label only. Row 1 is composed on the glasses with the live clock, so D4 (Pillow) and D11 (Skia) sweep every label × 12 clocks × all rounded ranges.
  - While a card covers the banner, the glasses send `alert_cleared`, then `alert_shown` again when the card closes (C101).
- **Glyphs:** every symbol (tier glyphs, voice shapes, ✕, clamps, bar, quatrefoils, progress ring) is a vector path in `Glyphs.kt`. A lint checks every text codepoint against the cmap.
- **Small-text fixes:** inset label `D2 · LIVE · 0.4s`; DATA stale on its own line; `REC` in the voice row; transcript ellipsized at the head.
- **Night:** dim green, APL ≤3%. The inset is green-mapped, ≤8% transient, and auto-closes after 10 s.
- **Gestures (L18, C46, C47):**

  | Gesture | Action |
  |---|---|
  | Triple-tap | STOP, immediately |
  | Double-tap | Held 400 ms by the companion, dropped if a triple-tap follows. Then CANCEL the card or DISMISS (never on WARNING). A gesture dismiss shows `DISMISSED · slide back to undo` for 3 s |
  | Slide down | Show the queue |
  | Two-finger hold | Raw-timed ≥1000 ms with a progress ring = CONFIRM, only if T7 passed and the same lockout, card-context and expiry rules as PTT pass (C101). It never opens PTT |
  | A second pointer during the PTT window | Cancels PTT |
  | Raw input | Feeds `InputFsm` via `dispatchTouchEvent`; hud-core has no pointer modifiers. PTT needs movement below touch slop for the first 300 ms (else it is a slide); taps join one `gesture_seq` only within ≤300 ms (C106) |

- **Stereo (L5):** the HUD is recorded once into a `GraphicsLayer` and drawn into both slots from the measured window. `dx` defaults to 0.
- **Lints:** APL as defined in [hud §9](spec/hud.md#9-lints-and-goldens-d11); region bounds and clear zone on the **ink bbox**, not the line box; ≥16 px text; ≥2 px strokes; cmap. Phase B commits **provisional** goldens and a contact sheet; Alisha's approval on Linux is a post-handoff gate (C106).

### 3.8 Glasses app (Kotlin)

| Module | Owner | Content |
|---|---|---|
| `hud-core` (KMP `commonMain` + `jvm` + `android`) | H | Protocol models, Ktor WS client, layout math, `HudRenderer`, `Glyphs.kt`, B612, lints |
| `emulator-desktop` | H | Compose Desktop. Single-eye 640×480 and SBS 1280×480 views; see-through composite; mouse/arrow head yaw; Space = PTT; keys → InputEvent; headless `--render-fixtures` via `ImageComposeScene` (headless Skia UNVERIFIED, with a Java2D fallback) |
| `platform-api` | G | `GlassesPlatform { display, input, mic, pose, camera, power, info }` |
| `platform-rayneo` | G | The only module importing `com.ffalcon.*`. `BaseEventActivity` host; **`MercurySDK.init` in the flavor `Application.onCreate`** (required by the SDK; without it `BaseEventActivity` throws, [probed], C106), also in `:selftest`; voice mode; RV/fused heading; `cyttsp5_mt` right-pad id; slide direction mapped from the system "natural mode" |
| `platform-generic` | G | AOSP phone: touchscreen, `VOICE_RECOGNITION`, phone RV, Camera2 |
| `app-android` | G | Flavors `rayneo` / `generic`. `HudActivity` (dispatchTouchEvent → InputFsm first), `StereoCompositor`, PTT FSM with pre-roll, BT HID key, inset decoder (MJPEG, latest frame), provisioning from intent extras into SharedPreferences, `BenchActivity` (P1) |
| `selftest` | G | Standalone `SelfTestActivity` that depends only on `platform-api`, `platform-rayneo` and OkHttp 4.12 (T5–T18), so it ships before hud-core (C74). Its peer is `./edith glasses selftest --serve` (aiohttp, no companion; `/v1/selftest` on :7400) for T9 (PCM → WAVs in `runs/bringup/<ts>/`), T11 (TCP throughput) and T13 (JPEG 320×240 at 15 fps with `frame_id`, RTT-based latency) (C104). Tests are defined normatively in [`docs/bringup/TESTS.md`](bringup/TESTS.md) |

- **Levels (L12, C43):** compileSdk **36**, targetSdk 34, minSdk 29, JVM 17. The device is very likely API 31–32 (UNVERIFIED, T0).
- **Manifest (C45):**
  - `com.rayneo.mercury.app=true` meta-data, landscape, `keepScreenOn`.
  - `Theme.AppCompat.NoActionBar` with a black `windowBackground` (`BaseEventActivity` extends AppCompatActivity [SDK]).
  - `network_security_config.xml` with cleartext permitted, because Phase 0 is LAN `ws://` only.
  - Permissions: CAMERA, RECORD_AUDIO, INTERNET, ACCESS_NETWORK_STATE. No WRITE_SETTINGS and no multicast permission.
  - Brightness through `window.attributes.screenBrightness`.
  - `adb install -r -g`.
- **RayNeo SDK (L13, C44):**
  - `tools/fetch_rayneo_sdk.sh [--from <zip>]` fetches **only the sample zip** and verifies sha256 `1c78e3c4…f47` (full hashes in `sdk.lock` [probed]).
  - It extracts the Mercury AAR (`5d408e2c…676`) into a local Maven repo `glasses/platform-rayneo/libs/m2/com/ffalcon/mercury-sdk/0.2.6/`, with a generated POM listing the SDK's runtime dependencies at pinned versions: appcompat 1.3.0, fragment-ktx 1.5.3, lifecycle-runtime-ktx 2.5.1 (from the sample's `build.gradle`), and activity-ktx 1.5.1, lifecycle-viewmodel-ktx 2.5.1, recyclerview 1.2.1, viewbinding 7.2.1, coroutines-android 1.6.4 (C106). Gradle upgrades them to the Compose set [probed].
  - Hashes live in `glasses/platform-rayneo/sdk.lock` (WS-G).
  - It deletes `xr2-platform.jks`.
  - The IPC AAR is not used.
  - `settings.gradle.kts` includes `:platform-rayneo`, `:selftest` and the `rayneo` flavor only when the repo exists. Otherwise it warns, and `generic` still builds.
  - The SDK is never committed.
- **Thermal:** at `MODERATE` the inset drops to 5 fps and the camera turns off. At `SEVERE` the app runs the HUD only.
- **Python `tools/edith_tools/fake_glasses.py`:** the CI client and the scenario runner's `FakeGlasses` API (C87). It records `HudState`, scripts inputs and **emits `card_shown`**.
- **Kotlin `hud.event` emission (C105):** hud-core emits `card_shown{ref}` exactly once per proposal from the draw pass of the first frame that contains the card (never on receipt), re-emits it after reconnect while visible, and sends `card_cleared` on removal; `alert_shown` follows the same rule. D11 tests it.
- **Debug signing (C106):** APKs built here and on a team laptop have different debug keys. `bringup.sh` and `glasses install` detect `INSTALL_FAILED_UPDATE_INCOMPATIBLE`, uninstall, reinstall and re-provision.

---

## 4. Repo, stack, running, testing, delivery

### 4.1 Layout

```
edith/                              (git: github.com/Anshuman-Singhal/edith, private, branch main — L13)
  edith                             # bash shim → uv run python -m edith_tools.cli
  pyproject.toml uv.lock            # uv workspace root; uv.lock sole writer = WS-A
  docs/OWNERS.yaml                  # path globs → WS; lint proves no overlap and full coverage
  schemas/v1/ schemas/fixtures/ schemas/cot/
  common/edith_common/              # envelope, models, geo, clock (ScaledClock); px4/ (owned by D)
  companion/edith_companion/        # §3.1 modules
  sim/edith_sim/ sim/profiles/ sim/traces/ sim/data.lock.yaml
  ml/edith_ml/ ml/models.yaml ml/splits.yaml
  bench/edith_bench/ bench/noise.lock.yaml
  tools/pyproject.toml tools/edith_tools/{__init__.py,cli,fetch,supervisor,commands/<ws>.py,fake_glasses.py,cot_router.py,capture_asr.py,cost_model.py}
  tools/{fetch_rayneo_sdk.sh,install_px4.sh,bringup.sh}
  scenarios/   glasses/   tests/{e2e,lint}/   .github/workflows/ci.yml
  docs/{PLAN.md,spec/,council/,bringup/TESTS.md,cost/,walkthroughs/,requests/,LICENSES.md}
  data/ models/ runs/ dist/ glasses/platform-rayneo/libs/     # gitignored
```

### 4.2 Pinned stack (`uv.lock` and `glasses/gradle/libs.versions.toml` are authoritative)

| Component | Version | Note |
|---|---|---|
| Python / uv / ruff | 3.13 / installed | |
| numpy · onnxruntime · opencv-python-headless | 2.5.3 · 1.29.0 · 5.0.0.93 | installed |
| pydantic · jsonschema · pytest · hypothesis | 2.13.5 · 4.26.0 · 9.1.1 · pinned at lock | |
| aiohttp · lark | 3.x at lock · **1.3.1** | |
| pymavlink | 2.4.50 | LGPL-3.0, dynamic use |
| pymap3d · mgrs | 3.2.0 · 1.7.1 | |
| PyAV (`av`) | cp313 at lock | Whether the bundled FFmpeg has GPL parts is UNVERIFIED; `av.library_meta` is recorded in LICENSES.md, and encoding stays in `sim/` (C84) |
| moonshine-voice · sherpa-onnx · vosk · kokoro-onnx | **0.1.6 · 2.0.3 · 0.3.45** · at lock | Optional extra `voice` [probed on 3.13]; Kokoro model and the 3 voices hashed in `voice/models.lock.yaml` (C107); never `piper-tts` |
| pytak · takproto | at lock | Optional extra `tak` |
| Pillow · fontTools | at lock | Text-fit tests on B612 |
| D14 venv | `uv venv -p 3.12`: torch CPU, onnx2tf, tensorflow, ai-edge-litert | Separate; never in the lock |
| PX4 SIH | 1.18.0~rc2 deb (sha256 pinned); final release if available | Approval-gated |
| JDK / Gradle | 21 / **8.14.3 wrapper committed** | |
| **AGP · Kotlin · CMP** | **8.13.2 · 2.2.21 · 1.9.3** | One compatible set (L12, C43) |
| **Ktor · kotlinx.serialization · coroutines** | **3.3.3 · 1.9.0 · 1.10.2** | Ktor ≥3.4 and serialization ≥1.10 need Kotlin 2.3 |
| Robolectric | **4.16.1**, `@Config(sdk=[31])` | |
| OkHttp | 4.12 | `:selftest` only (C104) |
| Android SDK | platforms 34/35/36, build-tools 34/35/36 at `/opt/android-sdk`; `adb` from platform-tools | L12 |
| B612 | 1.008 (OFL) | bundled TTF |

**Verified (L27).** A probe Gradle project with exactly these pins (KMP `hud-core` jvm + android, `rayneo`/`generic` flavors, Mercury 0.2.6 from the local m2 + generated POM) built `assembleRayneoDebug` and `assembleGenericDebug` here in 3 min from a cold cache at ≈3.7 GB peak, and Robolectric 4.16.1 at `sdk=31` passed in both flavors [probed by platform r3]. Maven Central returned one transient HTTP 429, so `./edith ci` and `doctor`'s Gradle check retry once on 429.

### 4.3 Commands

```
./edith doctor                         # versions, SDK 36, adb on PATH, ports free (14550 must be free), Intel-mac Moonshine note
./edith fetch models|naip|noise|visdrone-mot|rayneo-sdk [--from zip]|all   # hash-pinned per-WS lockfiles
./edith scenario lint scenarios/*.yaml [--beats]       # --beats: live-demo beat windows (C92)
./edith up --headless --scenario scenarios/demo_vignette.yaml --assets mock --detector gt --speed 4
./edith up --scenario scenarios/demo_live.yaml --assets px4 --detector yolox --emulator sbs --tak mesh   # speed 1
./edith test unit|contract|golden|integration|e2e|e2e-px4|android|lint|all   # unit = Python only
./edith bench goal1|goal2|placement|pareto
./edith glasses build|test|golden|emulator|dist|install --ip <ip>|selftest [--serve]|pull   # --serve: host peer for T9/T11/T13
./edith sim record-px4                 # golden PX4 trace on any laptop
./edith ci
```

`edith up` is a Python supervisor; there is no Docker. It does the following:

1. Exports the ScaledClock environment.
2. Starts Mock or PX4, linkshaper, simd and gt, the fake router, the teammate sim, the companion and the optional emulator.
3. Waits on `/healthz`.
4. Writes logs, SDP files, the wire log and the summary to `runs/<ts>/`.
5. With `--headless`, exits 0 only if lint and every expect pass.

### 4.4 Tests and CI

| Tier | Content | Budget here |
|---|---|---|
| lint | ruff; OWNERS overlap/coverage; no-binaries; truth-import; companion never imports `edith_sim`; NC-artifact packaging | <30 s |
| unit | Python: normalizer, grammar, resolver, confirm rule, FSM, I1–I8, ranker, geo, tracker, CoT, outbox, scenario lint | <90 s |
| contract | Fixtures through jsonschema; pydantic + Kotlin round-trip; adapter contract vs Mock | <90 s |
| golden | Emulator PNGs (≥24 states × 2 views), lints | <3 min |
| integration | Companion + Mock + fake_glasses + fake router; WAV → proposal; partitions | <3 min |
| e2e | `demo_vignette` headless (mock, gt, video off) | <5 min |
| e2e-px4 | Same with `--assets px4 --speed 1` | On team laptops; here after approval |
| android | `assembleRayneoDebug assembleGenericDebug :selftest:assembleRayneoDebug`, aapt2 checks, JVM + Robolectric | <10 min |

- **Gradle memory (C77):** `glasses/gradle.properties` sets `-Xmx3g`, the Kotlin daemon to 1536m, `parallel=false`, `workers.max=2`, and Robolectric `maxHeapSize=1g`.
- `./edith ci` runs the glasses build **serially, never alongside e2e**.
- Tests take `--port-base`.
- CI never reads gitignored data. Tests needing `data/` are marked `needs_data` and skip with a reason.
- `.github/workflows/ci.yml` runs the same steps on ubuntu-latest, without the RayNeo SDK. Gradle steps retry once on HTTP 429 (L27).

### 4.5 Delivery (L13, C75)

- **Git:** one commit per deliverable, pushed to `origin main`.
- **No binaries in git.** The banned list is APKs, AARs, model weights, datasets, archives, keystores and the RayNeo SDK.
  - A lint allowlists only the B612 TTF, `gradle-wrapper.jar`, the ≤200 KB CC0 sprites and the golden PNGs.
  - Models, data and the SDK are fetched by script with pinned hashes. The RayNeo script accepts `--from <local zip>`, because vendor URLs are tokenized.
- **APKs are reproducible with one command:** `./edith glasses dist` → `dist/edith-rayneo-debug.apk`, `dist/edith-generic-debug.apk`, `dist/edith-selftest-rayneo-debug.apk` and `SHA256SUMS`. These files are **handed to the user directly**, so day-one bring-up needs no Gradle build on a team laptop.
- **`docs/bringup/INSTALL.md`** covers adb on macOS, Windows and Linux, plus the provisioning command.

---

## 5. Pre-arrival build scope (Phase B, this workspace)

The workspace has 2 CPU, 7 GB RAM, no GPU, no Docker and no device. PX4 and apt are pending approval (L14), so everything P0 runs on MockVehicle. Numbers measured here are lower bounds. Priorities: **P0** must ship, **P1** should, **P2** stretch.

### 5.1 Workstreams and exclusive file ownership (L23, C73)

`docs/OWNERS.yaml` encodes the table below. `tests/lint/test_owners.py` fails if any tracked file has zero or two owners. The most specific glob wins only where this table lists it as an exception.

| WS | Phase B builder | Human owner | Exclusive write |
|---|---|---|---|
| **A** Contracts & repo | architect | **Anshuman** | `pyproject.toml`, `uv.lock` (sole writer), `edith`, `schemas/`, `common/` (except `common/edith_common/px4/`), `tools/pyproject.toml`, `tools/edith_tools/__init__.py`, `tools/edith_tools/{cli,fetch}/`, `tools/edith_tools/commands/__init__.py`, `tests/lint/`, `.github/`, `.gitignore`, `README.md`, `docs/{OWNERS.yaml,LICENSES.md,PLAN.md,spec/interfaces.md}`, `docs/council/**` (C107) |
| **B** Companion runtime & integration | architect | **Arjun** | `companion/pyproject.toml`, `companion/edith_companion/{__init__.py,__main__.py,gateway,bus,eventlog,world,assets,config}/`, `companion/tests/` (except the C/E/F/H subdirs), `tools/edith_tools/{supervisor/,fake_glasses.py}`, `tests/e2e/`, `bench/edith_bench/pareto/` |
| **C** Voice, intent & safety | voice | **Om** | `companion/edith_companion/{voice,intent,safety}/`, `companion/tests/{voice,intent,safety}/`, `bench/edith_bench/goal1/`, `bench/noise.lock.yaml`, `tools/edith_tools/capture_asr.py`, `docs/spec/voice.md` |
| **D** Sim | sim | **Simon** | `sim/` (except `gt_detector.py` and `teammates/`), `common/edith_common/px4/`, `scenarios/`, `tools/install_px4.sh`, `docs/spec/sim.md` |
| **E** ML & perception | ml | **Anshuman** | `ml/`, `companion/edith_companion/perception/`, `companion/tests/perception/`, `sim/edith_sim/gt_detector.py`, `bench/{pyproject.toml,edith_bench/__init__.py,edith_bench/goal2,edith_bench/placement}`, `docs/spec/eval.md` |
| **F** TAK & cost | defense_sme + pm | **Simon** | `companion/edith_companion/tak/`, `companion/tests/tak/`, `sim/edith_sim/teammates/`, `tools/edith_tools/{cot_router.py,cost_model.py}`, `docs/cost/` |
| **G** Glasses platform | platform | **Arjun** | `glasses/{settings.gradle.kts,build.gradle.kts,gradle.properties,gradlew*,gradle/}`, `glasses/{platform-api,platform-rayneo,platform-generic,app-android,selftest}/` (incl. `platform-rayneo/sdk.lock`), `tools/{fetch_rayneo_sdk.sh,bringup.sh}`, `docs/bringup/` (incl. `TESTS.md`) |
| **H** HUD | hud | **Alisha** | `glasses/{hud-core,emulator-desktop}/`, `companion/edith_companion/{alerts,hud}/`, `companion/tests/{alerts,hud}/`, `docs/spec/hud.md` |

**Rules:**
- **Dependencies.** A declares every §4.2 dependency in D0. Additions are requested in `docs/requests/<ws>.md`; each WS owns its own file, and A merges the request into the lockfile.
- **Schemas.** Schema changes go through A. Other workstreams add fixtures under `schemas/fixtures/*/<their type>/` via request.
- **CLI.** Each WS owns `tools/edith_tools/commands/<ws>.py`; A creates the stubs in D0.
- **Walkthroughs.** Each WS owns `docs/walkthroughs/<ws>.md`: one runnable walkthrough, used for the Dec 17 handoff (C83).
- **Workload.** Anshuman owns 2 of 8 workstreams. Integration lead moves to Arjun.

### 5.2 Order

1. **D0** (repo, git, owners, lints).
2. **{D1, D13a}** in parallel. D13a is the deadline-bound, G0-critical bring-up kit.
3. **{D2, D3b, D3c, D4, D5, D7, D8, D10a, D11}** in parallel. D3a starts here too, but its contract acceptance waits for D2.
4. **{D3a, D12}**. D11's emulator-vs-companion `card_shown` test runs once D3a and D10a land.
5. **D6** (e2e vignette).
6. **D13b** (full self-test).
7. **P1:** D9, D10b, D14, D16, D19; D15 when PX4 is approved.
8. **P2.**

The glasses arrive around Nov 30. **Session 1 needs only the selftest APK**, so D13a is due by Nov 29 and is done only when the user has received `edith-selftest-rayneo-debug.apk` + `SHA256SUMS` and checked the hash (C108). D12's dist APKs follow when D12 passes.

### 5.3 Deliverables and acceptance tests

| # | P | WS | Deliverable | Acceptance tests (run here) |
|---|---|---|---|---|
| **D0** | P0 | A | uv workspace with every §4.2 dependency declared (UNVERIFIED wheels as extras); `./edith` CLI with all subcommands (stubs allowed); ruff; `.gitignore`; `docs/OWNERS.yaml`; lint suite; LICENSES.md; commit pushed to `origin main` | `./edith doctor` → exit 0 and prints Python 3.13, Java 21, Gradle 8.14.3, "Android SDK platforms 34,35,36; build-tools 36.0.0", adb path. `uv sync --all-extras` → 0. `ruff check .` → 0. `./edith test unit` (Python only) → 0. `git check-ignore data/x models/x runs/x dist/x glasses/platform-rayneo/libs/x` → all ignored. `./edith test lint` → owners (no overlap, full coverage), no-binaries and truth-import lints pass. `git ls-remote origin main` matches local HEAD |
| **D1** | P0 | A | Schemas v1 for every type in [interfaces §3–4](spec/interfaces.md#3-websocket-messages-7400-v1ws); ≥1 valid + ≥1 invalid fixture per type; pydantic models; `edith_common.geo` (ENU/LLA/MGRS, bearing, clock, range, CE90 helpers, hae); `ScaledClock` | `./edith test contract` → every valid fixture passes and every invalid one fails (≥50 fixtures); pydantic round-trip is byte-stable. Geo: ENU↔LLA <0.01 m; ENU→MGRS→ENU <1 m; `clock(62°)=="2 o'clock"`; origin → `16TCK6100236799`. ScaledClock: two processes started with the same env agree within 5 ms at speed 4 |
| **D13a** | P0 | G | **G0-critical bring-up kit:** `fetch_rayneo_sdk.sh [--from zip]` → local m2 repo + POM; `:selftest` module (T5, T6, T7, T9, T13, T14 implemented); `./edith glasses selftest --serve` host peer (C104); `docs/bringup/TESTS.md` (normative T0–T18); `bringup.sh` (T0–T4 host-side; `adb install -r -g` with debug-key reinstall; provisioning `am start --es ws --es token --es peer`; pull results; `--tier g0`); `CHECKLIST.md`; `INSTALL.md`; `./edith glasses dist --selftest` | With the sample zip (`--from` or URL): sha256 matches `sdk.lock`; the POM lists the 7 dependency groups; `xr2-platform.jks` absent. `./gradlew :selftest:assembleRayneoDebug` succeeds; `aapt2 dump badging` shows minSdk 29 and landscape; `aapt2 dump xmltree --file AndroidManifest.xml` shows mercury meta-data=true, `networkSecurityConfig` and no WRITE_SETTINGS (C106). The registry, **generated from TESTS.md**, holds 19 tests (T0–T4 in bringup.sh, T5–T18 in the APK), each with a pass criterion and a `g0` tag on T0/T5/T6/T7/T9/T13/T14. A JVM test runs the selftest T13 and T9 clients against `selftest --serve` on localhost, and the result JSON validates. `bringup.sh --dry-run --tier g0` with a fake-adb shim writes `docs/bringup/dryrun.json` valid against its schema. `dist/edith-selftest-rayneo-debug.apk` + `SHA256SUMS` produced. Without the SDK: `./gradlew help :platform-api:assemble` succeeds and prints the warning. **Done** when the user has received the selftest APK + `SHA256SUMS` and confirmed the hash, by Nov 29 (C108) |
| **D2** | P0 | D | `sim/profiles/quad_sim.yaml` (incl. `COM_FAIL_ACT_T`, `MPC_ACC_HOR`); `edith_common.px4` (incl. delayed-hold failsafe and `plan_search`); scenario loader v2 + scenario runner with the FakeGlasses seams + **`edith scenario lint [--beats]`** with the per-predicate bound table; seeded mover; GT logger; **MockVehicle** (§2/§6 of the sim spec, reads the profile, DLL failsafe only when armed and airborne); **linkshaper** (MAVLink, `tak`, `video` windows, wire log); `scenarios/demo_vignette.yaml` (+ `demo_jam.yaml`, `demo_scout.yaml`, `demo_live.yaml`) | `pytest sim -q` passes. In-process Mock, same seed twice → identical sha256 of mover + jam + Mock trace. Mock heartbeat `autopilot=12, type=2`; orbit → `POSCTL.ORBIT`; reposition → LOITER; RTL → LAND → disarm; armed and idle disarms at 10 s; disarmed Mock takes no DLL action; armed in air + silence → AUTO.LOITER for `COM_FAIL_ACT_T` → AUTO.RTL, which persists after the link returns, and a hold is then accepted; corners are trapezoidal. `edith scenario lint scenarios/*.yaml` → 0, reproducing the sim §7 bounds at speed 4 (scout 5.2, ovw 24.2, orb2 12, RTL 25 s); the committed infeasible copy → non-zero naming the expect; `lint --beats scenarios/demo_live.yaml` → 0. Linkshaper: 0 packets pass in-window; the wire log records every message with direction and class |
| **D3a** | P0 | B | Gateway, bus, eventlog, world, config; pymavlink `AssetAdapter` + `outbound.py` + GCS heartbeat + MAVLink link monitor + fence/`GF_*` push with read-back; eventlog `alert.created` / `track.update` records; `fake_glasses.py` with the `FakeGlasses` API (`say`, `touch`, `on_card_shown`, `on_alert_shown`; emits `card_shown`); supervisor skeleton | The contract suite vs Mock (arm → takeoff → goto → orbit → search → hold → rtl → land; landed + search; landed + orbit; the DLL case) passes in <60 s at 10×. `FakeGlasses.say` emits `ptt_down` → `voice.session.start{text}` → `voice.text` → `ptt_up` in order. With `--allow-text-injection` the gateway refuses a `glasses` hello; the supervisor refuses `--emulator` at speed 4. Classifier: every MAVLink msgid in the adapter maps to MOTION/SAFE/CONFIG; an unlisted msg is dropped and logged; PARAM_SET while armed is blocked. Link: `degraded` 1.5 s after silence, `lost` at COM_DL_LOSS_T, liveness on any message. fake_glasses gets hello + snapshot <500 ms; heartbeat 2 Hz ±10%. Fence/`GF_*` mismatch on read-back → abort |
| **D3b** | P0 | C | Safety core: gate, proposal FSM, `confirm_rule.py`, safety stop with task cancellation, invariant monitor; tested with a recording `FakeAdapter` (no D2 dependency) | Hypothesis ≥1,000 examples each: I1–I5 and I7 hold (I6 and I8 are asserted in D8, D5 and D3c; the D6 monitor covers all eight, C109). Every press-outcome row ([voice §5](spec/voice.md#5-confirmation-c48-single-owner-companionedith_companionsafetyconfirm_rulepy)) passes. Rejected: confirm without `card_shown`; press started in lockout (`held_ms` estimate); `ctx.proposal_id` mismatch; "confirmed"; `ptt_up` after expiry; two-finger hold 900 ms; a 1200 ms two-finger hold started 300 ms before `card_shown`; `two_finger_hold` with no `ctx.proposal_id`; temple confirm while disabled; `voice.text` "confirm" outside a PTT window; a press whose joined session text is "and then you confirm it. Confirm." Accepted: a BT PTT press confirms; "abort" and "cancel" in a lockout-started press each take effect (C101). Card open over alert A + bare `dismiss` → 0 Feedback, A not suppressed. Text suite: 10,000 non-confirm utterances → 0 confirms. Stop ≤500 ms, pending SUPERSEDED, and a running follow re-issue loop is cancelled before the hold (I7). double_tap@0 + triple_tap@250 ms → SafetyStop only, 0 Feedback. 3 taps in 600 ms → stop only. Mission upload is emitted only after Confirmation. Hold for a lost asset → not sent, toast. RTL/land need confirm |
| **D3c** | P0 | H | `alerts` (ranker, suppression, flood collapse, budget, card-open queueing, bare-response scoping, `gesture_dismiss`) + `hud` projector (`HudState` v2 fields, inset policy, declutter, night) | Ranker: 3 s dwell, +0.2 pre-empt, 10-min suppression with escalation/closure overrides, collapse >3 in 10 s, budget counter. While a card is open a CAUTION queues (`+1`) and a WARNING invalidates. Bare `watch` with no alert shown → NOOP + `NO ALERT`; card open over alert A + `dismiss` → NOOP, A not suppressed; `mark` 3 s after `watch` applies to the watched alert. An over-budget CAUTION queues and is never dropped (C100). I6 holds on every projected entity. No declutter level hides card/stop toast/voice/WARNING. WARNING has `gesture_dismiss=false`. Gesture dismiss → `undo` for 3 s; `slide_back` restores the alert. Projection: 10 world snapshots → golden HudState JSON |
| **D4** | P0 | C | Normalizer (`spoken` + `written`), grammar v2, resolver (clock/MGRS/gazetteer + aliases/relative/teammate/frozen contact), read-back rows; ≥400 synthetic fixtures + **≥150 Moonshine-captured fixtures** (`capture_asr.py` on Kokoro TTS, committed as text) | `pytest companion/tests/intent -q` → 100% pass, both profiles. Rejected lexicon (all 19 entries) → 100% REJECTED; "repeat" is not say-again. Stop variants ("abort abort", "stop, stop", "all stop", "drone two hold position") → stop; "drone two orbit … abort" → spotted stop scoped to D2. `follow contact` → REJECTED. Mixed number styles → rejected (spoken). A 7-digit grid → SAY_AGAIN; written `2:00` and `i1` normalize (C109). "abort, don't fire" → stop. The parser's output for every vignette tasking `say` equals its `cmd` (C87). **Every read-back row ≤490 px; every alert label × 12 clocks × all rounded ranges gives banner row 1 ≤470 px; row 2 ≤400 px, measured on bundled B612 (Pillow)** (C102). The relabelled-capture count is reported. Hypothesis number and MGRS round-trips |
| **D5** | P0 | F | CoT build/parse (XML + takproto v1 inbound), scope guard, uids, retraction, transports (mesh, mesh-emu, tcp), `LinkMonitor`, outbox, inbound merge, `cot_router.py` (UDP 18088 fan-out + TCP 18087, answers `t-x-c-t`, logs received), teammate sim (VIKING, `m-s`, EXERCISE) | Golden XML for every table row. Scope guard (Hypothesis): no `a-h-*` from a machine source; no CoT for an `assoc_friend_uid` track. Dismiss → `t-x-d-d` ≤1 s from `Feedback(dismiss)`; a lost unmarked `m-f` track → delete; a lost MARKed (`h-e`) track → one `LKP <DTG>` re-send and never a delete; a dismissed object re-acquired under a new `track_id` inside the disc → no CoT (C99). mesh-emu partition of 25 s: `lost` ≤3 s after start, `ok` ≤2 s after end; router log shows ≥5 enqueues (counted before compaction) flushed in order, original `time`, expired events dropped, latest live-track states and LKPs re-sent. TCP: the fake router's "stop answering pings" switch → 2 missed pongs → `lost`. A takproto v1 fixture parses. The multicast loopback test passes or skips with a logged reason |
| **D6** | P0 | B | `./edith up --headless` supervisor complete; the vignette passes end to end with gt, video off | `./edith up --headless --scenario scenarios/demo_vignette.yaml --assets mock --detector gt --speed 4` → exit 0 in <5 min wall, with **every** expect in [sim §7](spec/sim.md#7-scenariosdemo_vignetteyaml-authored-in-d2) passing: scout dispatched; D2 in POSCTL.ORBIT; timeout case expired with 0 MOTION; 0 WARNING and 0 friend CoT from overwatch through jam + 30 s, with ≥1 association (C98); deer alert, then dismiss → CoT not live, no re-alert and no re-publication; vehicle alert shown with `a-u-G-E-V`, then MARK → `h-e`, still live (LKP) to the end (C99); TAK lost/ok, router flush in order; D2 lost, then AUTO.RTL after the 5 s delay (C89); "attack" rejected with 0 MOTION; triple-tap → both AUTO.LOITER; 0 invariant violations. `runs/<ts>/summary.json` holds loop latencies. Peak CPU <170% of 2 cores (sampled) |
| **D7** | P0 | D | simd synthetic camera (NAIP homography, or a procedural basemap without `data/naip` (C93), + 6 in-house CC0 sprites incl. persons for teammates + noise; stabilized gimbal); RTP H.264 with SEI `frame_id`, sidecar with `pose_est` + nav noise; FrameTruth JSONL; SDP; `fetch naip`; replay skeleton; video wall-capped at 15 fps | A PyAV test receiver joining **mid-stream** matches ≥99% of frames to sidecars by SEI (verified by a test-only frame-ID barcode); the pts-anchor fallback is tested too. Render ≥25 fps at 720p single-thread. A PNG snapshot with GT boxes on the procedural basemap matches golden. With `video: off`, simd renders no pixels and opens no basemap. At `--speed 4` the encoder emits ≤15 fps of wall time. Sidecar pose error statistics, including `rel_alt_m` and the gimbal horizon reference (C96), match the nav-noise σ within 10% |
| **D8** | P0 | E | Model fetch (sha256; YOLOX nano/tiny/s, D-FINE-N, RT-DETRv2-R18); YOLOX adapter (416²); tiler with IOS merge; scheduler; FrameSource (RTP+SEI); OffloadDetector; **ground-plane tracker**; geo CE90; fusion; novelty; **friendly association**; inset encoder (night green map); `gt_detector` (confusions, clutter, `gt_dets_<i>.jsonl`); image-plane tracking for pseudo feeds | Hashes match. YOLOX-Tiny@416 1 thread, measured in isolation, within ±25% of 62 ms; tiled frame p95 ≤350 ms isolated. Geo: pixel→ground→pixel <0.1 px with the stabilized gimbal at a 20° bank; Monte-Carlo with nav noise: **90% ±3%** inside ce_m. Tracker on synthetic GT: lawnmower at 8 m/s, 60 m AGL, 2 Hz — a stationary target and a 10 m/s target are each confirmed ≤2.5 s, IDF1 ≥0.8. Pseudo mode (C95): synthetic frames with the true camera panning 20°/s while `pose_est` is frozen → stationary targets confirmed ≤2.5 s, IDF1 ≥0.8. Fusion duplicate rate <1.2 on a two-drone overlap. Friendly association (C98): a teammate walking at 1.5 m/s with 10 s PLI and nav noise → 0 alerts and 0 CoT over 120 s in view, while a stranger 30 m from that teammate still alerts; a 25 s TAK partition with a teammate in FOV → 0 alerts and 0 CoT. Scheduler: boost to 4 Hz for 5 s; 1 Hz cap during PTT. Persistent clutter above τ_c becomes a confirmed track (FA path exercised). No test needs `data/` |
| **D10a** | P0 | C | Moonshine `AsrEngine` (0.1.6, model pinned in `voice/models.lock.yaml`); replay-WAV client over the real WS; **audio lure suite**; gazetteer alias check | Lure suite (≥40 confusables × 3 Kokoro voices × clean/10/5/0 dB, plus ≥20 multi-line lures × 3 voices, through Moonshine + `confirm_rule` on the joined session text) → **0 confirms**. Every lure press satisfies rules 1–5; the suite is invalid if the positive-control false-reject rate is >20% (C108). Procedural noise + Kokoro babble, no fetch. Every gazetteer name in `demo_vignette.yaml` parses from Moonshine at clean and at 10 dB on 3 voices. Integration (after D3a): WAV → proposal → `card_shown` → WAV "confirm" → Mock dispatch. Latency p50/p95, idle and (after D6, speed 1) under `edith up`, written to `runs/` |
| **D11** | P0 | H | Gradle `hud-core` + `emulator-desktop`; renderer via GraphicsLayer; `Glyphs.kt`; lints; Kotlin contract tests; headless goldens + contact sheet | `./edith glasses test` → JVM tests pass and every valid fixture round-trips. `./edith glasses golden` renders ≥24 states × 2 views, diff ≤0.5% vs the committed provisional goldens (Linux; Alisha's approval follows, C106). Lints on the ink bbox: APL per definition (≤13% persistent, ≤3% night); every text run inside its region; nothing in the clear zone 190,150–430,326 except the caret band (C103); Skia banner sweep (every label × 12 clocks × all rounded ranges → row 1 ≤470 px, C102); text ≥16 px; stroke ≥2 px; every codepoint in the B612 cmap; no pointer modifiers in hud-core. The emulator connects to the companion for 10 s and renders ≥15 snapshots. `hud.event` (C105): JVM test that `card_shown` is emitted once from the draw pass of the first frame containing the card, re-emitted after reconnect, `card_cleared` on removal, and `alert_cleared`/`alert_shown` around a card; integration (after D3a, D10a; `./edith test integration`): emulator + real companion + Mock — a CONFIRM WAV is accepted only after the emulator renders the card, and rejected with emission suppressed |
| **D12** | P0 | G | `platform-*`, `app-android` flavors; `HudActivity` with dispatchTouchEvent → `InputFsm`; PTT pre-roll; BT HID PTT; heading fusion; mic; `StereoCompositor` (measured slots); inset decoder; provisioning via intent extras; manifest fixes; `./edith glasses dist` | `assembleRayneoDebug assembleGenericDebug` succeed; `com.ffalcon` classes only in the rayneo APK. aapt2 (C106): `dump badging` → minSdk 29, landscape; `dump xmltree --file AndroidManifest.xml` → meta-data, cleartext `networkSecurityConfig`, theme (parent resolved via `dump resources` = AppCompat); permission set exact, allowing `<pkg>.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION`. JVM tests: pre-roll frames from DOWN−0 ms are included in `audio.up`; UP <300 ms in hold mode → nothing sent and mic released; toggle mode keeps the ring through the 450 ms tap decision; a 400 ms slide → `slide_*` and no `ptt_down`; taps ≤300 ms apart share one `gesture_seq`, a slower tap starts a new one; pointerCount 2 → no PttDown and no voice session; two-finger hold `duration_ms` from raw events; triple-tap emits `triple_tap` at once; double-tap carries `gesture_seq`; compositor slots for 1280×480, 640×480 and a phone window; heading wrap/drift; latest-frame queue. Robolectric (sdk 31): activity starts with its theme; intent extras → persisted connection config; mic released and `audio_source_record=off` on pause. `dist/` holds both APKs + SHA256SUMS |
| **D13b** | P0 | G | Full self-test T5–T18 plus `CHECKLIST.md` (T0–T18, voice B1–B6, HUD luminance/leakage, BT key test, T5 circle-aspect, T7 raw triple-tap log and DOWN→first frame ≤100 ms, T16 swatches `fg/friend/#FFD400/#FF3030`, T18 `CURRENT_NOW` sign/units/period) | Registry and CHECKLIST are generated from `docs/bringup/TESTS.md`: 19 tests with pass criteria and owners. `bringup.sh --dry-run --tier all` validates. CHECKLIST lists owner and threshold per test |
| D9 | P1 | E | `bench goal2` on composed timelines ([eval §2](spec/eval.md#2-g2-watch-reduction-c70)); `ml/splits.yaml`; operator model R=3/6/10 s; image-space recall on replay; Poisson FA CI | Same seed twice → identical metrics JSON. gt Pd 0.95, FA 2/h at 10% duty → WR ≥80% and recall ≥90%, with synthetic seconds charged at the real-seconds FA upper CI × R and the inset-boxed recall credit; FA reported as a point estimate with exposure hours, each unique segment once (C100). With `data/` present: YOLOX COCO on 3 composed missions reported without a target; without it the test skips with `needs_data` |
| D10b | P1 | C | `sherpa-onnx` engine; corpus generator (own verbalizer, ≥100 paraphrases); noise per [voice §6](spec/voice.md#6-corpus-and-noise-c67-c69) with `noise.lock.yaml`; SNR to −5 dB; bake-off; Vosk decoy grammar + AND-agreement | `bench goal1 --set clean50` → intent ≥90%. Per-SNR CSV produced. Every noise row has a license. Lure suite repeated with AND-agreement → 0 confirms |
| D14 | P1 | E | `uv venv -p 3.12`; YOLOX 576×320 ONNX export + TFLite (fp32/fp16/int8, 200 calibration frames); parity | Parity F1 ≥0.95 vs ORT fp32 per variant. 576×320 latency measured vs 416². Artifacts in `models.yaml` with sha256, `license` and `derived_from` |
| D15 | P1 | D | PX4 SIH (`install_px4.sh`, params after boot + read-back, `record-px4`). **Needs user approval here (L14)**; runs on a team laptop regardless | Contract suite `--assets px4` passes against 2 instances, including the DLL case (LOITER for `COM_FAIL_ACT_T`, then RTL; C89); `demo_vignette` with `--assets px4 --speed 1` passes; the Mock-vs-PX4 trace diff has no mode or ACK mismatches |
| D16 | P1 | E | `bench placement` (JSONL shared with BenchActivity; P2 sends the same detector input; energy rule) | Per-stage timestamps and p50/p95; an energy run refuses `usb_connected=true`; glasses JSONL import validates |
| D19 | P1 | F | Cost model v0 with `basis` column; capex / opex / 5-yr TCO | Totals reproduce; the script fails on a row missing a basis or a source/UNVERIFIED |
| D17 | P2 | D | Tier B scripts + SDF from the scenario origin; `telemetry_interp` pose | SDF lints; run documented on a GPU laptop |
| D18 | P2 | C | TTS via sherpa-onnx (permissive voice), mic gating | TTS never says "confirm"; mic muted during playback |
| D20 | P2 | F | OTS connector + docs | TCP ping/pong against the fake router; install doc |
| D21 | P2 | C+B | `follow me/teammate` end to end (grammar + gate in C; `follow(uid_stream)` in B) | Mock follows the VIKING 1-2 PLI at 30 m ±5 m; a stop cancels it within 500 ms (I7); a follow of a track → REJECTED |
| D22 | P2 | B | Pareto harness (linkshaper bandwidth/loss sweep) | One sweep point reproduces |
| D23 | P2 | F | DETAILS → SALUTE draft on `/ui/touch` (Size, Activity, Location MGRS, Unit=UNKNOWN, DTG Z, Equipment) | Draft fields populated from a track fixture |

---

## 6. Evaluation

Protocols are in [spec/eval.md](spec/eval.md).

- **G1 (C69):**
  - The **primary number comes from naive study participants**. The B6 team corpus is engineering data, reported separately.
  - Intent success and confident-wrong are pre-registered.
  - SPL is Leq30 dB(A) at the ear.
  - The audio lure suite replaces text-only evidence for "0 executions".
- **G2 (C70):**
  - Missions are composed real-footage timelines at pre-registered duty cycles of 5/10/20%.
  - A scripted operator model holds the inset for R = 6 s (3 s and 10 s also reported).
  - FA/h counts real seconds only, each unique segment once; the decision rule is a point estimate ≤6/h with exposure hours reported. Synthetic seconds are charged at the real-seconds FA rate (upper CI) × R inside AFS_E (C100).
  - Replay recall is matched in image space, and replay geo is `pseudo` (tracked in a motion-compensated image plane, C95). An entity boxed in an inset during watched seconds within 10 s of onset also counts as recalled.
  - The alert budget is a measured target, reported as a secondary outcome.
  - CEP90 is synthetic-only, with nav noise.
  - The person missions fly at 45–50 m and −45° pitch.
- **Edge vs offload (C71):** P2 sends the same detector input as P1. Energy is measured over Wi-Fi adb with USB unplugged.
- **G3 (C72):**
  - The baseline is a **phone-native layout** of the same `HudState`, frozen at W5.
  - Both arms use the same BT PTT button, earbud and earcon, with a haptic on the phone.
  - The primary DV is alert onset → PTT-down of a correct response.
  - Lures: ≥192 in total. Wrong-read-back catch rate is also reported.
  - Temple gestures are tested in a separate block.
  - Dusk is a sub-study with n ≥ 6.
  - A spotter accompanies every walking session.
- **G4 (C79):** capex, opex and TCO are reported separately. Software pricing is a willingness-to-pay hypothesis.

---

## 7. Semester plan

Penn Spring 2027 starts **Wed Jan 20**; spring break is Mar 6–14; the last class is May 4 (UNVERIFIED, C23). The final demo is assumed for the week of Apr 26, with feature freeze Apr 16 and demo freeze Apr 23. Thanksgiving removes Nov 25–29, and Dec 10–17 is reading days and finals, so December gates are front-loaded.

**Owners (L23, C73):**

| Person | Owns |
|---|---|
| **Arjun** | Glasses platform (G), companion runtime and **integration lead** (B), SITL host and demo laptop, **Pareto study lead**, mmWave |
| **Anshuman** | Architecture and contracts (A), vision/ML (E), G2, edge vs offload, operating point |
| **Alisha** | HUD (H: hud-core, emulator, alerts, HUD policy), IRB, study, phone-native layout |
| **Om** | Voice/NLP, grammar, **safety FSM and confirmation** (C), noise eval, G1 |
| **Simon** | **Sim and scenarios** (D), CoT/ATAK interop and cost (F), the Dec 12 PX4 gate, interviews/CRM, demo narrative |

### 7.1 Now → December

| Dates | Work | Owner | Gate |
|---|---|---|---|
| Nov 23–29 | Council builds Phase B. **D13a first: the selftest APK + `SHA256SUMS` reach the user and the hash is checked on receipt by Nov 29**; session 1 needs only that APK; D12 dist follows. Draft the IRB request. Buy router, power bank, USB-C data cable, SPL meter, speaker, IR thermometer, BT HID PTT button, forearm phone mount | Council; Alisha; Arjun | — |
| ~Nov 30–Dec 4 | **Glasses arrive.** First 3-hour session: G0-critical T0, T5, T6, T7, T9, T13, T14 from the handed-over APK (no Gradle). IRB request sent Dec 4 | Arjun lead; Om (T9); Alisha (T5) | — |
| Dec 5 | Remaining T-tests and B1–B6 begin; A2 battery/thermal (T14/T15) | Arjun, Om | — |
| Dec 10 | **G0 platform go:** T5/T6/T7/T9/T13 pass or a workaround is chosen (SBS vs mono, PTT hold vs toggle, temple confirm on/off). Native Kotlin confirmed | Arjun + Anshuman | G0 |
| Dec 12 | All T-tests done. A3: mic ASR at ≥85 dB(A). Contracts v0 frozen. **Demo laptop (native Linux) designated and `edith test e2e-px4` green on it** (C78) | Om; Anshuman; **Simon** (gate owner, depends on D15), Arjun supplies the laptop (C108) | PX4 gate |
| by Dec 17 | PLAN, hardware memo, ≥5 interviews; **1-hour handoff per WS owner from `docs/walkthroughs/`** (C83) | All; Simon | — |

**Interview guardrails (C82):**
- Interviews are unclassified and in a personal capacity.
- No TTPs, unit specifics or CUI.
- No ITAR-marked documents.
- Any sponsor agreement goes through Penn Export Compliance (fundamental-research exclusion).

### 7.2 Winter break (Dec 18 – Jan 19)

Arjun holds the glasses; everyone else works on the emulator and `generic`.

| Person | Deliverable |
|---|---|
| Arjun | Walking skeleton on the glasses; T18 on-glasses TFLite numbers; demo laptop PX4 soak |
| Anshuman | VisDrone fine-tune #1; `bench goal2` baseline on composed missions |
| Om | ASR bake-off on synthetic + B6 data; lure suite with AND-agreement |
| Alisha | HUD v1 from T16 data; phone-native layout draft |
| Simon | ATAK-CIV LAN interop (incl. `t-x-d-d` delete and `how` rendering); cost model v0; ≥10 interviews |

**Exit gate G1 (Jan 19):** walking skeleton end to end on the glasses: voice → confirm → SITL → HUD → ATAK.

### 7.3 Spring 2027

| Wk | Dates | Milestones (owner) | Gate |
|---|---|---|---|
| 1 | Jan 20–24 | Skeleton demo to TA; contracts v1 frozen (Anshuman); IRB status (Alisha) | Fri integration #1 (Arjun) |
| 2 | Jan 25–31 | Glasses-mic corpus at 60/75/85/95 dB(A) Leq30 (Om, Arjun); HUD v1 on device (Alisha); on-glasses bench (Arjun, Anshuman) | — |
| 3 | Feb 1–7 | ASR chosen, grammar v1 frozen + Vosk decoys (Om); fine-tuned baseline (Anshuman); CoT→ATAK-CIV live (Simon) | Fri integration #2 |
| 4 | Feb 8–14 | **G2 gate:** WR ≥80% at recall ≥90% at 10% duty, else fallback (D-FINE tier, 576×320, narrower claim) (Anshuman); link profiles (Arjun) | G2 |
| 5 | Feb 15–21 | Touch fallback for every intent (Alisha, Arjun); ranker v1 (Alisha, Anshuman); **phone-native arm frozen** (Alisha); IRB approval target Feb 19 | Fri integration #3 |
| 6 | Feb 22–28 | Pilot, 3–5 users (Alisha); mmWave go/no-go (Arjun); cost review (Simon) | — |
| 7 | Mar 1–5 | **G3 feature-complete v1**; harnesses automated; internal demo; `edith scenario lint --beats scenarios/demo_live.yaml` green (Simon, C92); **no autopilot upgrades after Mar 5** | G3 |
| — | Mar 6–14 | Spring break | — |
| 8 | Mar 15–21 | Operating point frozen (Anshuman); edge-vs-offload (Anshuman) + Pareto (Arjun); study begins (Alisha) | — |
| 9–10 | Mar 22–Apr 4 | Main study (Alisha lead, all run sessions); dusk sub-study | — |
| 11 | Apr 5–11 | G1 results from study utterances + noise curve (Om); G2 report (Anshuman); study analysis (Alisha); cost v1 (Simon) | — |
| 12 | Apr 12–18 | **Feature freeze Apr 16**; dry run #1 | G4 |
| 13 | Apr 19–25 | **Demo freeze Apr 23**; backup video of every live beat, including the SAR re-skin; dry run #2 | G5 |
| 14 | Apr 26–May 2 | **Final demo** (date to confirm) | — |

**Final demo beat sheet (C78):** ~8 min, of which ~4 min is live. Problem → one architecture slide → live beats:

| Beat | Live content | Time |
|---|---|---|
| Scout | "Drone one, scout NAI one" beside 85 dB(A) babble → card → CONFIRM | 45 s |
| Alert | Vehicle alert → WATCH → MARK, visible on stock ATAK-CIV | 40 s |
| False positive | Planted false positive → DISMISS, and it disappears from ATAK | 15 s |
| Lure | Card shown → the operator presses PTT ≥1 s after the card → a judge reads one ≤6 s sentence containing "confirm"/"confirmed" (and no stop word) → release before 8 s → the HUD still shows AWAIT_CONFIRM ("no change" row) and the god-view wire log shows 0 MOTION → the operator says "cancel" (C108) | 30 s |
| Silent task | D2 overwatch tasked silently by touch (temple, or `/ui/touch` on the forearm phone if T7 failed), so D2 is airborne for the jam | 30 s |
| Jam | Jam → degraded → D2 LOITER 5 s → RTL → resync with original timestamps (same `demo_live.yaml`, `COM_DL_LOSS_T: 8` override, disclosed; no scenario switch, C92) | 50 s |
| Stop | "Attack" → Unsupported; triple-tap ALL HOLD | 20 s |

Then evidence slides (G1 curve, G2 WR vs recall curve, G3 A/B, Pareto) → cost model and roadmap, with the same source running on a phone → scope-boundary slide (including the known limit that an unknown person within the association radius of a teammate is masked, C98). A 75 dB(A) fallback is scripted. Speeds are sim-tuned and disclosed.

---

## 8. Long-term direction

| Phase | Scope | TRL | Gate to next |
|---|---|---|---|
| **0 (this year)** | Three core loops in sim; operator-tested HUD; cost model | 4 | May 2027: G1–G3 met or honestly reported; ≥15 interviews (≥3 operators/drone users); ≥1 LOI or pilot conversation; portability proven (same source and hud-core run on a phone via `generic`; `platform-rayneo` Kotlin LOC / all `glasses/` Kotlin LOC <5%); full-time decision; Penn IP policy checked |
| **1 (6–12 mo)** | Trusted-hardware port; companion on Android EUD/ARM64; ATAK plugin v0; first real flights with a Blue UAS drone at a range; retrain on owned data; TLS 8089 + mTLS; wss | 5–6 | SBIR Phase I / DIU CSO + field test |
| **2** | Squad-leader workflows, deep ATAK integration, ATO/RMF (NIST 800-53, FIPS 140-3, STIGs, encryption at rest, signed builds), offline sync at scale | 6–7 | Accreditation sponsor |
| **3** | Multi-asset ISR tasking (every task still human-confirmed), team mesh, lite SKU | 7+ | Program-of-record conversation |

**Trusted hardware path.**
- Only `platform-rayneo` is replaced.
- Candidates: Vuzix, DigiLens ARGO, ThirdEye X2. Audit components against 1260H, not just brands.
- TCL's status is UNVERIFIED.

**ATAK plugin wedge.**
- Phase 1 ships a phone-first voice-tasking and feed-triage plugin on the ATAK-CIV SDK from tak.gov, signed through TAK.gov.
- The glasses become the upgrade.
- Moat candidates:
  - integration breadth;
  - published voice-tasking safety evidence (lure suite, study);
  - the WATCH/DISMISS data loop (if data rights allow);
  - ATO.

**Dual use and buyers.**
- SAR and wildland fire come first; law enforcement last (no ID, published retention, audit logs).
- DIU's drones/autonomy portfolio, **never as a kill-web component**.
- SOFWERX, xTech, SBIR/STTR (foreign-ties screening).

**What not to build:**
- weapons, targeting, fires/CAS hooks or target handoff;
- automatic hostile classification;
- **continuous pursuit of a contact** (L16);
- countermeasure actuation;
- face, biometric or re-ID;
- 6DoF anchoring in Phase 0;
- swarms before Phase 3;
- a free-form LLM as primary control;
- cloud dependence;
- our own drones, radios, glasses or map engine;
- DJI/Autel SDKs.

Staying inside the DoDD 3000.09 exclusions depends on never adding effects.

---

## 9. Risk register

| # | Risk | Owner | L | I | Mitigation |
|---|---|---|---|---|---|
| 1 | RayNeo display/input/mic differs from docs (SBS size, long-press, audio mode, DoubleClick-before-TripleClick) | Arjun | M | H | Runtime stereo mode from the measured window; raw-event InputFsm; toggle-PTT fallback; double-tap hold; G0-critical tests in session 1; G0 Dec 10 |
| 2 | One pair breaks, is lost or is monopolized | Arjun | M | H | `generic` flavor; emulator; sign-out log; budget ask (Q3) |
| 3 | Battery/thermal shorter than a session | Arjun | H | M | Camera off; transient inset; 30 fps cap; power bank; sessions ≤30 min |
| 4 | ASR fails in noise or on written-form output | Om | M | H | PTT + pre-roll; profiles; aliases; real-ASR fixtures; say-again; touch path; BT headset fallback |
| 5 | Unsafe or accidental execution | Om | L | H | `card_shown` + lockout + exact-word confirm; decoy closed grammar; outbound classifier; wire-log invariants I1–I8; audio lure suite; stop = hold only |
| 6 | COCO misses small aerial targets; no GPU | Anshuman | H | M | 576×320 input; ground-plane tracker; fine-tune W1–4; recall by pixel height; G2 gate W4 |
| 7 | IRB delay or no relevant participants | Alisha | M | H | Request Dec 4; floor N=12; civilian pool |
| 8 | Integration slip; no skeleton by Jan 19 | **Arjun** | M | H | Frozen contracts; e2e green in CI; Friday integrations; load rebalanced (C73) |
| 9 | Perceived as weapons, a toy, or China-dependent; export slip | Simon | M | H | Unknown-only, no effect verbs, no pursuit, scope guard, boundary slide, portability, interview guardrails |
| 10 | PX4 misbehaves or never runs here | **Simon** | M | M | Mock carries CI via the shared profile (incl. the `COM_FAIL_ACT_T` delayed hold) + trace diff with a DLL case; Dec 12 demo-laptop gate (Simon; Arjun supplies the laptop); version frozen after Mar 5 (C89, C108) |
| **11** | **The team can't maintain ~20k lines of council-written code** | Anshuman | M | H | One owner per path; per-WS runnable walkthroughs; 1-hour handoffs by Dec 17; tests as documentation; no codegen |

**Watch list:**
- magnetometer heading error;
- venue Wi-Fi jitter;
- NC-data commercialization;
- Compose drawn twice is slow (single GraphicsLayer, View fallback);
- ATAK-CIV `t-x-d-d` semantics;
- the CoT `how` and `ce` interpretation;
- an unknown person within the friendly-association radius of a teammate is masked (I8). P1 option: one-to-one assignment, with CAUTION for the extras (C98).

---

## 10. Open questions for the human team

1. **Workspace approvals (L14):** may the council run the PX4 SIH binary and `apt` here? Everything P0 works without them.
2. **Course logistics:** exact final-demo date, format and required deliverables.
3. **Hardware budget:** a second display device; ~$2k of accessories, now including a BT HID PTT button and a forearm phone mount; Android phones for `generic`, the study's phone arm and ATAK-CIV.
4. **Compute:** Penn GPU access, or Colab? Does anyone have an NVIDIA laptop with native Ubuntu 24.04, and which laptop is the native-Linux demo machine (Dec 12)?
5. **Mentor:** research contribution (Pareto or mmWave) or product demo? Written agreement that SITL + real footage counts for G1/G2? Will he serve as IRB PI?
6. **Vendor terms:** RayNeo SDK redistribution. Until answered, the SDK is fetched by script and never committed; built APKs go only to the team.
7. **Post-May:** full-time intent; Penn IP policy.
8. **Team agreement on the rebalanced ownership (C73).** Simon takes sim and the Dec 12 PX4 gate (C108), Om takes the safety FSM, Arjun takes integration. Confirm at the next team meeting.

Operator-dependent defaults are settled by interviews and the pilot, with values already in config:
- confirm vocabulary;
- MGRS precision;
- TTS on/off;
- the alert budget;
- the disclosed sim speeds.
