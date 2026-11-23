# R1 — Systems Architect Proposal (Phase 0, extensible to Phases 1–3)

Author: Systems Architect · 2026-11-23 · Status: proposal for council review

## 1. Recommendations

### 1.1 Shape of the system: a "thin glasses, thick companion" star

```
 [Glasses app]  <-- WS (JSON control + binary audio/video) -->  [Companion service]  <-- MAVLink/UDP -->  [PX4 SIH drones x N]
  render+capture                                                 the brain              <-- CoT/UDP mcast, TCP -->  [Team: sim teammates, ATAK-CIV, TAK server]
                                                                                        <-- frames --  [Synthetic drone cameras (sim)]
```

- **Glasses = screen, ears, eyes, never the brain.** Responsibilities: render a semantic `HudState`, apply head-relative transforms locally (compass strip, heading-up mini-map, off-screen bearing arrows) from the native 3DoF rotation vector so the HUD stays responsive with a 0 ms network dependency, capture mic (and camera when needed), touch/temple input, local staleness display. No mission logic, no persistence of mission data on the device (it is untrusted TCL hardware).
- **Companion = everything stateful.** World model, voice→intent, safety gate, proposal/confirmation state machine, asset control, perception, alert ranking, TAK bridge, store-and-forward sync. In Phase 0 it is a laptop. In Phase 1 the same Python service moves to a Linux ARM64 puck (Jetson/RK3588-class), where MAVSDK already ships `manylinux aarch64` wheels.
- **Why the brain is on the companion:**
  - The glasses can't carry it. The AR1 has 4 GB RAM and a 245 mAh battery, so running ASR, the detector, the tracker and the parser on it would cause throttling and drain the battery.
  - The companion owns the radio links (MAVLink, mesh), which must survive the glasses disconnecting.
  - It keeps the glasses swappable. Moving to trusted hardware in Phase 1 means re-implementing only the thin client.
- **HUD policy lives on the companion, layout lives on the glasses.** The companion decides *what* is shown (one ranked alert, whether the inset is visible, which entities are on the mini-map, the pending proposal card). The glasses decide *where/how* pixels go. This makes cognitive-load policy unit-testable in Python and keeps the renderer dumb and portable.

### 1.2 Protocols

**Glasses ↔ companion: one WebSocket connection** (`ws://<companion>:7400/v1/ws`, Ktor client on Kotlin, `websockets`/aiohttp on Python).
- Text frames: JSON envelopes (below).
- Binary frames: `[u32 header_len][JSON header][payload]`, header `{stream, seq, ts_ms, codec, w, h}`.
  - **Audio up:** `pcm_s16le`, 16 kHz mono, 20 ms chunks (640 B, 256 kbit/s). Only streamed between `voice.session.start/stop` (push-to-talk on temple, or VAD-gated per Voice expert). Opus is a later bandwidth optimization, not needed on a dedicated Wi-Fi link.
  - **Video down (drone inset):** JPEG, 320×240, 10–15 fps, q≈70 (~1.5–2.5 Mbit/s). The inset is ~200 px wide on a 640×480 display, so H.264 buys nothing in Phase 0 and adds decoder/latency risk. Detection boxes are **not** burned in; they arrive as `track` data and are drawn natively (crisp, toggleable).
  - **Video up (glasses camera, benchmark/operator-view only):** JPEG 640×480 at ≤10 fps.
- **Upgrade path (Phase 1+):** MediaMTX (RTSP/WebRTC) as the video hub, with H.264 decoded through `MediaCodec` + `KEY_LOW_LATENCY`. The header's `codec` field makes the switch additive. Adopt it only if inset latency exceeds 250 ms.
- **State delivery = full `HudState` snapshots**, not deltas: on change (debounced, max 10 Hz) plus a 2 Hz heartbeat. Snapshots are small (<4 KB), idempotent, and self-heal after any drop.
- **Up rates:** `head.pose` 10 Hz (companion needs heading for "2 o'clock" phrasing), `input.*` on event, `sys.ping` 1 Hz carrying t0 for NTP-style clock-offset estimation (needed for latency benchmarks across devices).

**Companion ↔ drones:** MAVSDK-Python (v4.2.0, Nov 12 2026, bundles `mavsdk_server`; one `System()` and one `mavsdk_server` port per vehicle) against **PX4 SIH SITL** (`make px4_sitl sihsim_quadx`; no Gazebo, no GPU). PX4 instance *i* on UDP 14540+i. pymavlink is used only for diagnostics and test fakes. Everything sits behind an `AssetAdapter` interface (`connect, telemetry stream, takeoff, goto, orbit, hold, rtl, land`) with a `MockAssetAdapter` for fast tests; a later Anduril/Skydio/other vendor adapter plugs in here. Enable PX4 data-link-loss failsafe (`NAV_DLL_ACT`=RTL) so the drone's behavior on our link loss is defined by the autopilot, not by us.

**Companion ↔ team:** Cursor-on-Target XML (TAK Protocol v0) via **PyTAK 7.x** (Apache-2.0; `takproto` adds protobuf v1 later).
- **Serverless mesh (default, offline-first):** UDP multicast SA `239.2.3.1:6969` — ATAK's default. Any ATAK-CIV phone on the same Wi-Fi sees our teammates, drones and tracks with zero infrastructure (strong credibility demo).
- **Server mode (optional):** TCP to a TAK server on 8087 (TLS 8089 later). Recommend **OpenTAKServer** (GPLv3, active 2026 releases, Python ≥3.10) for the lab demo; it needs RabbitMQ + nginx, so it is **not** a CI dependency. CI uses an in-repo minimal CoT router fake.
- Mapping: self `a-f-G-U-C`; teammates as received; drones `a-f-A-M-H-Q` (friendly air, military rotary UAV — SME to confirm exact 2525 string); detections as **unknown** `a-u-G` (the AI never asserts "hostile"; only an operator may reclassify). `stale` = 3× send interval. `<detail>` carries `contact/callsign`, `__group`, `track`, `remarks`, and an `<edith v="1" .../>` extension element for our IDs.

### 1.3 Core data types (versioned JSON; source of truth = JSON Schema 2020-12 in `schemas/`)

Envelope: `{ "v": 1, "type": "<domain.name>", "id": "uuid", "ts_ms": 0, "src": "companion-01", "seq": 0, "body": {...} }`. Major `v` bump = breaking; additive fields are minor and must be ignored by older readers. `sys.hello` exchanges supported versions and capabilities (`display: {w:640,h:480,eyes:"mono|sbs"}`, `inference: ["companion","glasses"]`).

```
AssetState      asset_id, callsign, kind(quad|fixed_wing|ugs), link{state:ok|degraded|lost, last_heard_ms},
                pos{lat,lon,alt_msl_m,alt_agl_m}, att{yaw,pitch,roll}, vel_ned{n,e,d}, battery_pct,
                mode, armed, task{proposal_id,verb,status}, sensors[{sensor_id,kind:eo|ir,hfov_deg,stream}]
Detection       det_id, frame_ts_ms, source{asset_id,sensor_id}, cls(person|vehicle|drone|other), conf,
                bbox_norm[x,y,w,h], infer{location:glasses|companion|cloud, model, t_capture,t_start,t_end}
Track           track_id, cls, conf, geo{lat,lon,ce_m}, vel?, first_seen_ms, last_seen_ms,
                source_assets[], status(new|tracked|lost|dismissed), operator_label?, det_ids[-N:]
Alert           alert_id, priority(0-100), severity(info|caution|warning), kind(new_track|link_lost|
                battery_low|geofence|teammate_status), title, detail, ref{track_id|asset_id|uid},
                bearing_deg, range_m, clock, actions[{verb:"track"|"dismiss"|..., say:["track"]}], expires_ms
CommandIntent   intent_id, utterance{text,asr_conf}, parsed{verb, asset_ref, target{kind:track|point|
                bearing_range|teammate|area, ...}, params{alt_m,radius_m}}, parser{method:grammar|llm, conf}
CommandProposal proposal_id, intent_id, asset_id, verb, resolved_target{lat,lon,alt_m}, readback,
                checks[{name,pass,msg}], confirm_with[voice|touch], nonce, expires_ms, state
Confirmation    proposal_id, nonce, method(voice|touch|voice+touch), operator_id, ts_ms
Execution       exec_id, proposal_id, status(sent|accepted|in_progress|completed|failed|aborted), detail
TeammatePosition uid, callsign, team, role, pos{lat,lon,hae}, course, speed, ts_ms, stale_ms, source(mesh|server|sim)
HudState        seq, operator{lat,lon,heading_deg}, minimap{range_m, entities[{ref,kind,rel_e_m,rel_n_m,style}]},
                alert?{...Alert subset}, proposal?{readback,expires_ms}, inset?{stream,label}, voice{state,partial},
                status{link,battery,gps,staleness_ms}
```

**Verb allowlist is structural:** `takeoff, goto, orbit, observe(track|point), search(area), follow(track, standoff≥X), hold, rtl, land`. There is no field, enum value or adapter method for weapons, payload release, or countermeasures, so out-of-scope tasking cannot be represented, not merely "blocked".

**Lifecycle (companion-owned state machine):** `PROPOSED → CONFIRMED | REJECTED | EXPIRED(10 s) | SUPERSEDED → EXECUTING → COMPLETED | FAILED | ABORTED`. Rules: one live proposal at a time; confirmation must echo the current `nonce`; a confirmation arriving after expiry or after any link drop is rejected; the safety gate (geofence polygon, altitude band, battery reserve, asset link ok, target age < N s) runs at proposal time **and** again immediately before execution. Commands are never queued across disconnects. Every transition is appended to the event log.

### 1.4 Inference placement & benchmark support

Perception is a pipeline `FrameSource → Detector → Tracker → GeoProjector → AlertRanker`, each behind an interface. `Detector` has three placements emitting identical `Detection` messages with timing fields: **companion** (default; ONNX Runtime CPU), **glasses** (LiteRT/ONNX Runtime Mobile on AR1 — NPU/QNN access through AIOS is UNVERIFIED), **cloud** (optional HTTP service with the same API; in Phase 0 "cloud" can be a second laptop). For the glasses placement, the companion relays a drone stream to the glasses (or uses the glasses camera), the glasses run the model and upload only Detections. A `bench/` harness replays fixed clips through each placement and records end-to-end latency, fps, accuracy vs. sim ground truth, uplink bytes, and glasses battery/thermal (Android `BatteryManager`, `PowerManager` thermal status). Model licensing (Ultralytics YOLO is AGPL) is the ML expert's call; the interface is model-agnostic.

### 1.5 HUD rendering decision: native Kotlin + Compose Multiplatform

| Option | Buildable here | Portability | 6DoF | Student speed | Verdict |
|---|---|---|---|---|---|
| Unity ARDK | **No** (no Unity) | Unity-to-OpenXR devices | Yes (reportedly unstable) | Slow, heavy | Reject for Phase 0 |
| WebView HUD | Yes | Any browser | No | Fast | Viable fallback; needs native shell anyway; headless browser download for tests UNVERIFIED here |
| **Kotlin + Compose Multiplatform** | **Yes** (Gradle + Maven + Google Maven reachable; Android SDK installable) | Android + JVM desktop (+iOS) | Not needed | Good | **Recommend** |

Rationale: the HUD is screen-fixed plus compass-registered, so 3DoF from `TYPE_ROTATION_VECTOR`/`TYPE_GAME_ROTATION_VECTOR` suffices; we do not need SLAM. One `hud-core` module (Kotlin `commonMain`: protocol client, models, layout math, Compose `Canvas`/`DrawScope` renderer) is shared by the Android glasses app and a **desktop emulator**, so there is exactly one renderer and no drift. Layout math is kept in pure Kotlin so that, if Compose misbehaves on AIOS, a plain `android.view.View`/`Canvas` backend can be swapped in within a day. A `DisplayAdapter` renders a 640×480 logical viewport and, if the device needs it (UNVERIFIED), duplicates it side-by-side per eye with an optional per-eye offset. Visual rule set for additive MicroLED: black = transparent, no filled panels, ≥16 px text, high-saturation green/amber/cyan.

### 1.6 HUD emulator

`glasses/emulator-desktop` (Compose Desktop, JVM 21) runs the same `hud-core` at 640×480 over the same WS protocol.
- **Inputs:** mouse/arrows for head yaw/pitch, space for PTT (laptop mic or an injected WAV), keys for temple gestures.
- **"See-through" mode:** composites the HUD additively over a background video to approximate outdoor readability.
- **Headless mode:** renders fixtures to PNG via `ImageComposeScene` (headless operation verified by a day-1 spike).
- **Python `fake_glasses` client:** used for e2e tests without the JVM.

### 1.7 Offline-first

- **Principle: state syncs, commands don't queue.**
- No internet required anywhere in the core loop: local ASR, local parser, local detector, vector mini-map (relative positions plus range rings; no map tiles in Phase 0), mesh over LAN multicast.
- **Glasses↔companion loss:** glasses keep the last `HudState`, age-badge everything, grey it out after 3 s, show "LINK LOST", and keep compass/heading live; the companion expires any pending proposal. On reconnect: `sys.hello`, then a full snapshot.
- **Companion↔drone loss:** `AssetState.link=lost`, an alert, and the autopilot failsafe (RTL) takes over.
- **Companion↔team loss (jamming):** an outbox in SQLite (WAL). Position-type CoT is compacted to the latest per `uid` (stale ones dropped). Track/alert events are kept with their original `time` and replayed on reconnect. Inbound merge is last-writer-wins on `(uid, time)` and honors `stale`.
- **Event log:** an append-only SQLite log of every message and transition. It gives replay for debugging, the after-action review, and benchmark ground truth.
- Jamming is simulated with an in-repo application-level **impairment proxy** (drop/latency/partition, scriptable). This avoids needing root `tc netem`.

### 1.8 Repo layout, languages, run, test

```
edith/
  schemas/            JSON Schemas + fixtures/ (golden messages shared by all languages)
  companion/          Python pkg edith_companion: gateway, world, voice, intent, safety, proposals,
                      assets(mavsdk|mock), perception, alerts, tak, sync, eventlog, bench
  glasses/            Gradle: hud-core (KMP), app-android (RayNeo shell + generic Android), emulator-desktop
  sim/                scenarios (YAML), px4 launch, synthetic camera, teammate CoT sim, impairment proxy, ground truth
  ml/                 training/export scripts, model registry (sha256 + HF URLs; no weights in git), eval
  tools/              `edith` CLI, install_android_sdk.sh, install_px4.sh
  tests/e2e/          headless end-to-end scenarios
  docs/
```

- **Languages:** only two, Python 3.13 (uv workspace) and Kotlin 2.x (Gradle 8.14, JDK 21).
- **One command:** `./edith up [--scenario demo.yaml] [--emulator] [--tak] [--assets mock|px4]`. It is a Python supervisor (there is no Docker). It starts PX4 SIH ×N, the sims, the companion and the optional emulator/TAK server, then waits on `/healthz` and multiplexes logs. `--headless` is the CI form.
- **Ports:** 7400 WS, 7401 HTTP (health plus a debug "god view"), 14540+i MAVLink, 239.2.3.1:6969 CoT.
- **Tests (`./edith test [unit|contract|golden|integration|e2e]`):**
  - Unit (pytest + Hypothesis): parser, safety gate, state machine (property: *no Execution without a matching, unexpired Confirmation*), ranker, geo-projection, CoT round-trip. Kotlin: JUnit for layout and protocol.
  - Contract: every fixture in `schemas/fixtures` validates with `jsonschema` and round-trips through Python models and Kotlin `kotlinx.serialization`.
  - Golden: HUD PNGs at 640×480 with pixel tolerance. These PNGs double as Alisha's review artifacts.
  - Integration: companion + MockAsset + fake_glasses + CoT loopback.
  - E2E (slow): PX4 SIH + synthetic video with known targets + scripted utterances (text injection, plus a WAV path through real ASR). Assert: proposal shown → confirm → drone reaches orbit within T s → track alert ranked #1 → CoT emitted. Negative cases: no confirm means no motion; a stale nonce is rejected; a link drop mid-proposal expires the proposal.
  - Android: `assembleDebug` + Robolectric unit tests here (no device or emulator; KVM is unlikely).

### 1.9 Security posture (prototype)

- No secrets needed or stored. LAN-only bind. A per-run pairing token (printed as a QR code) goes in `sys.hello` to stop lab cross-talk; this is not real security.
- Glasses are treated as untrusted: no mission data at rest and no RayNeo cloud services. Disabling vendor telemetry is UNVERIFIED.
- No PII or biometrics. Generate a CycloneDX SBOM now. Stretch goal: MAVLink 2 signing in sim.
- **Later accreditation needs:** RMF/ATO (NIST SP 800-53), FIPS 140-3 crypto, TAK mTLS (8089), data-link encryption, STIGs, encryption at rest, trusted-hardware supply chain, signed builds.

## 2. Interfaces / needs from other experts

- **HUD/UX (Alisha):** design against the `HudState` schema. Needed: the element inventory, sizes in px at 640×480, alert priority tiers, proposal-card copy, and the staleness visual language. I need confirmation that one alert plus one proposal card is the max concurrent load.
- **ML (Anshuman):** the detector I/O contract (input size, classes, ONNX opset), target fps per placement, geo-projection assumptions (flat-earth plus gimbal pitch from `AssetState`), tracker choice, model license, and on-glasses runtime candidates.
- **Voice (Om):** PTT vs. wake-word vs. VAD; ASR engine and CPU budget on 2 cores. Needed: the grammar for verbs and targets, the confirm/cancel vocabulary, a barge-in policy, and whether TTS readback plays on the glasses speakers (it would be a new `audio.down` stream).
- **Sim:** PX4 SIH multi-instance on 2 CPU / 7 GB (build time, `PX4_SIM_SPEED_FACTOR`), the synthetic camera (pose-registered replay of aerial clips with ground-truth boxes), and the scenario YAML format. Needed: the fallback if a PX4 build is infeasible here (MockAsset-only e2e).
- **Defense SME:** CoT type strings for UAVs and unknown detections; whether `hold`/`abort` may execute on a single utterance as a safety stop (see open questions); a realistic geofence and altitude policy; ATAK-CIV interop expectations.
- **Glasses platform (Arjun):** day-1 answers on Android API level, the `com.rayneo.mercury.app` flag, mono vs SBS rendering, rotation-vector/magnetometer quality, Camera2, AudioRecord beamforming source, Wi-Fi RTT, thermal/battery under load, charging-while-running, and NNAPI/QNN.
- **PM (Simon):** demo network (bring a dedicated travel router; never rely on venue Wi-Fi), the hardware list for the cost model (companion puck class), and a scope freeze on the verb allowlist.

## 3. Buildable before the glasses arrive, and how it's verified here

1. **Schemas, fixtures and contract tests** in both languages. Verified by `./edith test contract`.
2. **The companion with MockAsset:** the full lifecycle, safety gate, ranker, HudState projection and event log. Verified by unit and property tests.
3. **The PX4 SIH install script and the MAVSDK adapter.** Verified by a headless e2e run, with MockAsset as the fallback.
4. **The TAK bridge, teammate sim and impairment proxy.** Verified by CoT round-trip and partition/reconnect tests.
5. **CPU perception on synthetic video.** Verified against ground truth; fps here counts as a lower bound.
6. **`hud-core`, the emulator and golden PNGs.** Verified headless.
7. **The Android APK** (`assembleDebug`): manifest flag, WS client, sensor/audio/camera behind interfaces, and a bring-up diagnostics screen showing sensors, RTT, fps, battery and thermal. Verified by compile + Robolectric. On day 1 it goes to the device with `adb install`.
8. **`./edith up --headless`** completing the scripted demo scenario.

## 4. Risks and mitigations

| Risk | Mitigation |
|---|---|
| SBS/per-eye rendering or the manifest flag behaves differently (UNVERIFIED) | `DisplayAdapter` abstraction; day-1 test APK cycles mono/SBS patterns |
| Compose on AIOS slow or broken | Pure-Kotlin layout plus a `View/Canvas` backend swap (≤1 day) |
| Compose Desktop headless fails here | Day-1 spike; fallback Robolectric screenshots or a Java2D backend |
| PX4 build too heavy on 2 CPU | Build once and cache; MockAsset e2e by default, PX4 e2e as a slow tier |
| 2-CPU contention skews benchmarks | Benchmark on team laptops; label workspace numbers lower-bound |
| Glasses battery/thermal (245 mAh) | PTT-gated audio, camera off by default, inset only while tasked, power bank (charge-while-running UNVERIFIED) |
| Magnetometer heading poor indoors | Manual heading trim gesture; sim-provided heading in demo; flag in user study |
| Wi-Fi latency/jitter at the demo | Dedicated router, 5 GHz, latency shown on HUD, snapshots are idempotent |
| Accidental confirmation | Nonce + 10 s expiry, distinct confirm word, optional voice+touch, readback names the asset and verb |
| Scope creep toward strike | Structural verb allowlist, detections typed unknown, SME review of the schema |

## 5. Open questions

1. Does `hold/abort` execute on one utterance (reduces risk) or also need confirmation? The brief says "every asset command"; my default is confirmation for all verbs except an `ABORT→HOLD` safety stop, pending SME/PM sign-off.
2. Do the glasses have GNSS? If not (likely; UNVERIFIED), operator position comes from the companion (laptop: sim-provided).
3. Is the drone video for the glasses-placement benchmark relayed from the companion or taken from the glasses camera? This affects what "on-glasses inference" proves.
4. Will the team commit to Compose Multiplatform (Kotlin skills on the team?), or is web skill depth strong enough to prefer a WebView HUD?
5. Is a real ATAK-CIV Android phone available to the team for the interop demo?
6. Is OpenTAKServer or FreeTAKServer for the lab HQ node, and who hosts it?
