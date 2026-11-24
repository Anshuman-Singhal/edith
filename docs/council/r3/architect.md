VERDICT: CHANGES REQUIRED

Round 3, systems architect. One MAJOR remains: the cross-workstream seams of the scenario runner that D6 depends on. Everything else is fixed or a nit.

## r2 issues

| r2 # | Status | Note |
|---|---|---|
| 1 | FIXED | compileSdk 36 set. [probed] `/opt/android-sdk` has platforms 34/35/36, build-tools 34/35/36 and `platform-tools/adb` |
| 2 | FIXED | Ownership is exclusive and lint-checked. Coverage holes in nit 6 |
| 3 | FIXED | gt runs over 5800+i and video is off when headless. Rendering detail in nit 3 |
| 4 | FIXED | mesh-emu through linkshaper with a 1 Hz / 3 s LinkMonitor (C54 values) |
| 5 | FIXED | Proposal state ends at `dispatched`, then `Execution{step_idx}`. Expects use `steps` |
| 6 | FIXED | MOTION/SAFE/CONFIG classifier, new I2, wire-log witness |
| 7 | PARTIAL | Anchors and lint were added, but the lint rule as written rejects the committed vignette (issue 2) |
| 8 | FIXED | SEI, SDP, `telemetry_interp`. [probed] PyAV 19.0.2 wheel has `libx264` and the `rtp` muxer |
| 9 | FIXED | Wording nit in nit 5 |
| 10–12 | FIXED | — |

## Remaining issues

**1. MAJOR: the scenario runner's seams are undefined, and D6 depends on them (sim §5–§7, D2/D3a/D6/D8).**
- Nothing says who executes `say` and `touch`.
- `on: alert_shown{gt_entity}` needs a live join from alert to GT entity that crosses B, E and D, and nothing specifies it.
- The lint pre-run must turn "scout NAI one" into the same lawnmower path the adapter flies. That path is built by `AssetAdapter.search` (B, wave 3), while the lint (D2) is built in parallel.
- Built blind, these pieces won't fit at D6.

Fix:
- **(a) Runner drives fake_glasses.** The runner (D) hosts fake_glasses in-process through a B-owned API:
  - `FakeGlasses.say(text)` sends, in order: `ptt_down{held_ms, ctx from last HudState}`, `voice.session.start{trigger:text}`, `voice.text`, `ptt_up`.
  - The API also offers `touch(kind)`, `on_card_shown` and `on_alert_shown(alert_id)`.
  - The supervisor passes `--allow-text-injection` only with `--headless --assets mock`.
- **(b) Alert-to-entity join.**
  - gt_detector (E) writes `runs/<ts>/gt_dets_<i>.jsonl {det_id, entity_id|null}`.
  - The eventlog (B) records `alert.created{alert_id, track_id}` and `track.update{track_id, det_ids}`.
  - The runner maps alert → entity by majority `det_id`, reading the eventlog read-only. Post-hoc expects use the same join.
  - No truth enters the companion.
- **(c) Shared search planner.**
  - Move the planner to `edith_common.px4.plan_search(polygon, alt, hfov, pitch, overlap)` (D). Both the adapter and the pre-run call it.
  - Each tasking `say` event carries `cmd:{asset, steps, target}` for the pre-run.
  - A D4 test asserts that the parser's output for every vignette `say` equals its `cmd`.

**2. MINOR, must fix in D2: the lint contradicts the vignette.**
- Sim §6 rule 1 is "within_s < lower bound + 2 s → fail". Two committed expects fail it:
  - `after: dism, within_s: 1` has a lower bound of 0, so it needs at least 2.
  - `after: scout, within_s: 5`: card 0.5 + lockout 0.6 + delay 2 + margin 2 = 5.1.
- D2 also requires `lint scenarios/*.yaml → 0`, so D2 cannot pass as written.
- Fix:
  - The lower bound is the time the predicate first holds in the deterministic pre-run, with modeled latencies: card 0.5 s, parse 0.3 s, max(lockout, confirm delay), and mode *entry* rather than arrival.
  - The +2 s margin applies only when that lower bound is above 0.
  - Set scout `within_s: 6`.

**3. MINOR: `video: off` must mean no pixels.**
- With video off, simd produces FrameMeta and FrameTruth analytically, renders nothing and loads no basemap.
- simd falls back to a procedural basemap when `data/naip` is absent, and D7 goldens use that basemap.
- Without this, D6 and CI read `data/` or blow the 170% CPU budget (120 renders/s at speed 4).

**4. MINOR: `router_log.queued_min: 5` is non-deterministic.**
- PLI compaction can reduce the queue to 3 uids (self, D1, D2), and SPI and track output during t300–325 are not scripted.
- Fix: count enqueues before compaction, or list the expected uids.

**5. MINOR: clocks and glasses durations.**
- Write ScaledClock as `now = T0 + (wall − T0)·speed`, so `ts_ms` stays epoch-like.
- `held_ms`, `duration_ms` and the glasses-side countdowns are in wall ms, but lockout and expiry are in scaled ms. The supervisor must refuse `--emulator` or real glasses at speed ≠ 1, or the gateway must scale glasses durations by `EDITH_SPEED`.

**6. MINOR: owners and dependencies.**
- Assign the paths that have no owner:
  - `docs/council/**` (already tracked, so the D0 coverage lint fails today) → A.
  - `tools/pyproject.toml` and `tools/edith_tools/__init__.py` → A.
  - The `sdk.lock` path → G.
- §4.2 omits `kokoro-onnx`, which D4 and D10a need. Add it to the `voice` extra and put the model hash in `voice/models.lock.yaml`.

**7. MINOR: profile params have two appliers (§3.1 `assets` and the sim §1 PX4 launcher).**
- Profile params are applied only by the sim launcher; Mock reads the file directly.
- The companion's `configure()` pushes only the fence and `GF_*`, and D3a's read-back abort applies to those.
- This keeps `SIM_*` and sim-tuned cruise out of a Phase 1 vehicle.

## Phase B feasibility

Phase B can be built here.
- **Glasses build.** The Android toolchain, Gradle, uv, Python 3.13, ffmpeg and PyAV are present [probed]. 2 CPU and 7 GB fit the serial glasses build (3g + 1.5g + 1g).
- **P0 runs on Mock.** Every P0 item runs on MockVehicle, and PX4 stays P1 under L14.
- **Remote.** The git remote is set and `main` tracks `origin/main`.
- **Acceptance.** With issue 1 specified and issue 2 corrected, the D0–D13b acceptance tests prove the §0 claims they cover.
