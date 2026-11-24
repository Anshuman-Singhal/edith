VERDICT: CHANGES REQUIRED

Reviewer: systems architect, round 2. Severity is either BLOCKER or MAJOR (the build, the demo or a goal proof fails) or MINOR.

1. **BLOCKER: §3.8 Levels, §4.2, D12. The Android build fails as specified.** [probed] The AAR metadata for `androidx.compose.ui:ui-android:1.9.0`, `activity-compose:1.10.1` and `core:1.16.0` all declare `minCompileSdk=35`. Compose Multiplatform 1.9.x pulls these in. With compileSdk 34, `checkDebugAarMetadata` fails and `assembleRayneoDebug` fails with it. **Fix:** "compileSdk **35**, targetSdk 34, minSdk 29. D0 runs `sdkmanager "platforms;android-35" "build-tools;35.0.0"` (Google's repo is reachable), and `edith doctor` checks for both." In §4.2, change the Android SDK row to "platforms 34 + 35, build-tools 34.0.0 + 35.0.0". Also note that `adb` is already at `/opt/android-sdk/platform-tools/adb`, which doctor should add to PATH.

2. **MAJOR: §5.1. File ownership is not conflict-free.**
   - `sim/` is D's exclusively, but E owns `sim/edith_sim/gt_detector.py` and F owns `sim/edith_sim/teammates/`.
   - `scenarios/` is D's, but D6 (WS-B) delivers `scenarios/demo_vignette.yaml`.
   - `fetch_data.py` (E) has to carry NAIP (D7, D) and noise data (D10, C).
   - A uv workspace has **one** root `uv.lock`, so per-package `pyproject.toml` files do not prevent collisions.
   - Several paths have no owner: `companion/pyproject.toml`, `companion/edith_companion/{__init__,__main__,app}.py`, `companion/tests/`, `bench/` root, `tests/lint/`, `tools/edith_tools/commands/<ws>.py`, the `edith up` supervisor and `.github/`.

   **Fix (replacement rules):**
   - "D owns `sim/` **except** `edith_sim/gt_detector.py` (E) and `edith_sim/teammates/` (F)."
   - "D writes `scenarios/demo_vignette.yaml` as part of D2. B may only file requests against it."
   - "`fetch_data.py` is a generic engine (E) that reads per-WS lockfiles: `sim/data.lock.yaml` (D), `ml/models.yaml` (E), `bench/noise.lock.yaml` (C)."
   - "In D0, WS-A declares every §4.2 dependency and is the **sole writer** of `uv.lock`. Packages with UNVERIFIED cp313 wheels (sherpa-onnx, moonshine, vosk, pytak, trackers, av) are optional extras, so a missing wheel never breaks `uv sync`."
   - "B owns `companion/pyproject.toml`, the package root files, `companion/tests/` except `tests/{intent,voice}` (C), `tests/perception` (E) and `tests/tak` (F), and the supervisor at `tools/edith_tools/supervisor/`. A owns `tests/lint/`, `.github/` and `.gitignore`. `commands/<ws>.py` is created as a stub by A in D0 and then owned by that WS."
   - "`tools/fake_glasses.py` moves to `tools/edith_tools/fake_glasses.py` so tests can import it."

3. **MAJOR: §3.6, D6. The `--detector gt` path has no transport, and headless video exceeds 2 CPUs.** `gt_detector` needs truth from the sim process. As written, the companion would have to import `edith_sim`, which breaks the truth lint. Separately, at `--speed 4`, two cameras at 15 fps give 120 encodes/s and 120 decodes/s. With x264 720p at about 8 ms per encode, that alone is about 1.5 cores. **Fix:**
   - "`gt_detector` runs **inside the sim** and publishes `[Detection]` (`infer.placement=offload, model=gt`) on UDP **5800+i**. The companion `OffloadDetector` ingests it, which is the same path as P3."
   - Add 5800+i to §2.5.
   - "Camera `fps` is wall-clock. Under `--headless --detector gt`, cameras run `video: off` by default, sending the FrameMeta sidecar only. D7 owns video-path proof."
   - "`demo_vignette.yaml` uses `mode: synth` for both drones. Replay appears only in `goal2_*` scenarios, so CI never needs `data/`."

4. **MAJOR: §1.4 loop 3, §3.6, D5. CoT jamming and outbox triggering are undefined.**
   - CI cannot use multicast (D5 may skip it).
   - TCP to the fake router cannot pass through linkshaper, which is a UDP proxy.
   - Multicast gives no delivery feedback, so the outbox has no signal for when to queue.

   **Fix:**
   - "Headless runs use `--tak mesh-emu`. CoT goes by UDP unicast through linkshaper channel `tak` to the fake router's UDP fan-out on :18088 (add the port to §2.5)."
   - "`tak.LinkMonitor` sets mesh `lost` after 6 s with no inbound packet. The teammate sim and fake router send `t-x-c-t` every 2 s. TCP mode uses `t-x-c-t` ping/pong with a 6 s timeout."
   - "On the transition from `lost` to `ok`, the outbox replays everything queued plus anything sent in the 6 s detection gap, in original order with original `time`."

5. **MAJOR: §2.4 vs §3.4 vs the §3.6 `expect` block. The proposal schema does not match the FSM or the tests.**
   - The `CommandProposal.state` enum has no `in_progress|completed|failed|aborted|rejected`, but the §3.4 FSM uses them.
   - The proposal has `steps[]` but no `verb`, yet the `expect` block asserts `proposal: {verb: search}`.

   **Fix:**
   - "Proposal states end at `dispatched`. The post-dispatch lifecycle lives in one `Execution` per step (`step_idx` added)."
   - "`HudState.proposal.state` adds `sent|acked|no_ack`."
   - "`expect.proposal` matches `{steps: [takeoff, search], state: dispatched}`."

6. **MAJOR: §3.4 I1/I2. The invariants cannot be implemented as written, and the e2e check has no independent witness.**
   - "The only unconfirmed command is hold" is contradicted by traffic that must go out unconfirmed: the GCS `HEARTBEAT`, `SET_MESSAGE_INTERVAL`, the `PARAM_SET` of scenario params, and the fence upload.
   - `mavlink_commands_since` has no data source.

   **Fix:**
   - "The adapter's outbound filter classifies every message as MOTION (arm, takeoff, reposition, orbit, mission upload+start, rtl, land, speed, any set_mode other than LOITER: needs a DISPATCHED proposal), SAFE (set_mode LOITER) or CONFIG (heartbeat, message intervals, scenario params and fence at connect). Anything else is dropped and logged."
   - "I2 is restated as: no MOTION without confirmation."
   - "MockVehicle writes `runs/<ts>/mav_rx_<id>.jsonl`, and `expect` counts commands from that log, not from the companion's own log."

7. **MAJOR: §3.6 example scenario. The timing cannot be met, and D6 will fail if this example is copied.**
   - Drone 1 is roughly 880 m from NAI 1. At PX4's default cruise (`MPC_XY_CRUISE` 5 m/s), it arrives at about t=200.
   - The camera, at a 60° depression, sees only about 80 m ahead.
   - veh-7 leaves NAI 1 from t=60.
   - So `alert by_t: 90` is not achievable.

   **Fix:**
   - "MockVehicle cruise is 10 m/s, from `scenario.mock.cruise_mps`."
   - "Add `edith scenario lint`, which fails any `expect` that is earlier than the kinematic lower bound."
   - Correct the example to spawn drone 1 at (200, 150) and set `by_t: 120`.

8. **MAJOR: §2.4 FrameMeta, C24. How a decoded frame is matched to its pose is undefined, and Tier B has no sidecar.** ffmpeg's RTP demuxer rebases pts to the first packet it receives, so joining on `pts` fails if the companion connects mid-stream. Gazebo emits no sidecar at all. **Fix:**
   - "The synth/replay encoder prepends an H.264 SEI `user_data_unregistered` NAL carrying `frame_id` to each packet, encoded with `tune=zerolatency` and no B-frames. The companion reads it from packet bytes before decoding."
   - "The supervisor writes `runs/<ts>/sdp/drone<i>.sdp` for PyAV."
   - "Tier B uses `pose: telemetry_interp` (ATTITUDE/GLOBAL_POSITION_INT interpolated at receive time minus a calibrated latency) instead of the sidecar."

9. **MINOR: §2.1 Clock.** `--speed` spans processes. **Fix:**
   - "The supervisor exports `EDITH_T0_MS` and `EDITH_SPEED`. Every process uses `ScaledClock`, and all `ts_ms` values are scaled."
   - "The glasses compute countdowns as `expires_ms − hud.ts_ms` at receipt, never against the local wall clock."
   - "PX4 mode forces `--speed 1`."

10. **MINOR: §2.4 HudState.** Add `alert.ce_m`, which row-1 rounding needs. Add `minimap.entities[].marked: bool`, which the filled-quatrefoil symbol needs. Make `tape.carets[].style` an enum: `friend|unknown|hostile|point`.

11. **MINOR: §3.2/§3.4. The confirm rule has two owners.** **Fix:** "`safety/confirm_rule.py` (B) holds the only predicate on normalized text plus conf. `voice` (C) only supplies its inputs. D3 tests the predicate and FSM with a recording FakeAdapter (no D2 dependency). D4 runs the same 10k suite through the normalizer."

12. **MINOR: §4.3/§4.4.** **Fix:**
    - "`edith test unit` is Python only. Kotlin runs under `glasses test`/`test android`."
    - "Set `org.gradle.jvmargs=-Xmx2g`, `kotlin.daemon.jvmargs=-Xmx1536m` and `org.gradle.workers.max=2`. Never run Gradle concurrently with e2e on 7 GB."
    - "Integration and e2e tests take `--port-base` (default 0 = ephemeral) so parallel runs don't collide."
    - "§2.5 states bind vs send: PX4 binds 14580+i and sends to 14540+i; linkshaper binds 14540+i and 14640+i; the companion binds 14740+i."
