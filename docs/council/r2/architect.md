VERDICT: CHANGES REQUIRED

1. **BLOCKER: §3.8 Levels, §4.2, D12. The Android build fails.**
   - [probed] The AARs for `androidx.compose.ui:ui-android:1.9.0`, `activity-compose:1.10.1` and `core:1.16.0` declare `minCompileSdk=35`. Compose Multiplatform 1.9 pulls them in.
   - With compileSdk 34, `checkDebugAarMetadata` fails, and so does `assembleRayneoDebug`.
   - **Fix:** use compileSdk **35**, targetSdk 34 and minSdk 29. D0 runs `sdkmanager "platforms;android-35" "build-tools;35.0.0"`, and `edith doctor` checks for both. In §4.2, the SDK row becomes "platforms 34+35, build-tools 34.0.0+35.0.0". `adb` already exists at `/opt/android-sdk/platform-tools/adb`; doctor should put it on PATH.

2. **MAJOR: §5.1. File ownership has conflicts.**
   - Three paths have two owners:
     - D owns `sim/`, but E owns `sim/edith_sim/gt_detector.py` and F owns `sim/edith_sim/teammates/`.
     - D owns `scenarios/`, but D6 (B) delivers `demo_vignette.yaml`.
     - `fetch_data.py` belongs to E, but it must also serve NAIP (D) and noise (C).
   - A uv workspace has **one** root `uv.lock`, so per-package pyproject files do not prevent collisions.
   - Several paths have no owner: the companion pyproject, package root and `companion/tests/`; the `bench/` root; `tests/lint/`; `commands/<ws>.py`; the supervisor; `.github/`.
   - **Fix (replacement rules):**
     - D owns `sim/` except `gt_detector.py` (E) and `teammates/` (F).
     - D writes `demo_vignette.yaml` in D2.
     - `fetch_data.py` (E) becomes a generic engine that reads per-WS lockfiles: `sim/data.lock.yaml` (D), `ml/models.yaml` (E), `bench/noise.lock.yaml` (C).
     - WS-A declares every §4.2 dependency in D0 and is the sole writer of `uv.lock`. Packages whose cp313 wheels are UNVERIFIED (sherpa-onnx, moonshine, vosk, pytak, trackers) are optional extras.
     - B owns the companion pyproject, the package root, `companion/tests/` (minus `intent`/`voice` for C, `perception` for E and `tak` for F) and `tools/edith_tools/supervisor/`.
     - A owns `tests/lint/`, `.github/` and `.gitignore`.
     - A creates the `commands/<ws>.py` stubs; each WS then owns its own file.
     - `fake_glasses.py` moves to `tools/edith_tools/`.

3. **MAJOR: §3.6, D6. The `--detector gt` path has no transport, and headless video overruns 2 CPUs.**
   - The companion importing `edith_sim` to get truth breaks the truth-import lint.
   - At `--speed 4`, two 15 fps cameras mean about 120 x264 encodes/s plus decodes. That is roughly 1.5 cores before the companion runs.
   - **Fix:**
     - `gt_detector` runs inside the sim and publishes `[Detection]` (`infer.placement=offload, model=gt`) on UDP **5800+i** to a companion `OffloadDetector`. This is the same path as P3. Add the port to §2.5.
     - Camera `fps` is wall-clock. `--headless --detector gt` defaults to `video: off`, so only the sidecar is sent; D7 proves the video path.
     - `demo_vignette` uses `mode: synth` on both drones. Replay appears only in `goal2_*` scenarios, so CI never needs `data/`.

4. **MAJOR: loop 3, D5. The jam path and the outbox trigger are undefined.**
   - Multicast may not work in CI.
   - TCP to the fake router cannot pass through a UDP-only linkshaper.
   - Multicast gives no delivery signal, so the outbox never knows when to queue.
   - **Fix:**
     - Headless runs use `--tak mesh-emu`: UDP unicast through linkshaper channel `tak` to the fake router's UDP fan-out on :18088.
     - `tak.LinkMonitor` sets the link to `lost` after 6 s with no inbound packet. The teammate sim and fake router send `t-x-c-t` every 2 s; TCP mode uses `t-x-c-t` ping/pong.
     - When the link returns, the outbox replays the queue plus everything sent during the 6 s detection gap, in order, with the original `time`.

5. **MAJOR: §2.4 vs §3.4 vs §3.6. The proposal schema contradicts the FSM and the `expect` block.**
   - The `CommandProposal.state` enum lacks `in_progress|completed|failed|aborted`.
   - The proposal has `steps[]` but no `verb`, yet `expect` asserts `proposal: {verb: search}`.
   - **Fix:**
     - Proposal states end at `dispatched`. After that, one `Execution` per step (add `step_idx`) carries the lifecycle.
     - `HudState.proposal.state` adds `sent|acked|no_ack`.
     - The `expect` entry becomes `proposal: {steps: [takeoff, search], state: dispatched}`.

6. **MAJOR: §3.4 I1/I2. The invariants can't be implemented as written, and the zero-command check has no independent witness.**
   - The GCS heartbeat, `SET_MESSAGE_INTERVAL`, scenario `PARAM_SET` and the fence upload are unconfirmed by necessity, which breaks "the only unconfirmed command is hold".
   - **Fix:**
     - The adapter's outbound filter classifies every message:
       - **MOTION**: arm, takeoff, reposition, orbit, mission upload+start, rtl, land, speed, set_mode other than LOITER. Needs a DISPATCHED proposal.
       - **SAFE**: set_mode LOITER.
       - **CONFIG**: heartbeat, message intervals, params and fence at connect.
       - Anything else is dropped and logged.
     - I2 becomes "no MOTION without confirmation".
     - MockVehicle logs `runs/<ts>/mav_rx_<id>.jsonl`, and `mavlink_commands_since` counts from that vehicle-side log.

7. **MAJOR: §3.6 example scenario. The timing is infeasible, and D6 fails if the example is copied.**
   - Drone 1 is about 880 m from NAI 1. At 5 m/s (PX4 default cruise) it arrives around t≈200.
   - At a 60° depression the camera sees only about 80 m ahead.
   - veh-7 leaves NAI 1 at t=60.
   - So the `alert by_t: 90` expect cannot pass.
   - **Fix:**
     - Add `scenario.mock.cruise_mps: 10`.
     - Add `edith scenario lint`, which fails any `expect` that comes before its kinematic lower bound.
     - In the example, spawn drone 1 at (200, 150) and set `by_t: 120`.

8. **MAJOR: C24, FrameMeta. Frame-to-pose matching is undefined.**
   - ffmpeg's RTP demuxer rebases pts to the first packet it receives, so joining on `pts` fails if the companion connects mid-stream.
   - Tier B (Gazebo) emits no sidecar.
   - **Fix:**
     - The synth/replay encoder prepends an SEI `user_data_unregistered` NAL with `frame_id`, using `tune=zerolatency` and no B-frames. The companion parses it from packet bytes before decoding.
     - The supervisor writes `runs/<ts>/sdp/drone<i>.sdp`.
     - Tier B uses `pose: telemetry_interp`, interpolating ATTITUDE/GLOBAL_POSITION_INT.

9. **MINOR: §2.1. The clock must scale across processes.**
   - **Fix:** the supervisor exports `EDITH_T0_MS` and `EDITH_SPEED`, and every process uses `ScaledClock`. The glasses compute countdowns as `expires_ms − hud.ts_ms` at receipt. `--assets px4` forces `--speed 1`.

10. **MINOR: §2.4 HudState.** **Fix:** add `alert.ce_m` (needed for row-1 rounding) and `entities[].marked: bool` (needed for the filled quatrefoil). Make `carets[].style` an enum.

11. **MINOR: §3.2/§3.4.** The confirm rule has two owners. **Fix:** the predicate lives only in `safety/confirm_rule.py` (B). D3 tests it with a recording FakeAdapter, so D3 does not depend on D2.

12. **MINOR: §2.5/§4.4.** **Fix:** `edith test unit` runs Python only. Gradle gets `-Xmx2g` and `workers.max=2`. Tests take `--port-base`. §2.5 states which side binds each port and which side sends to it.
