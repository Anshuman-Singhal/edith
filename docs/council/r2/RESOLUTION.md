# Round 2 resolution index

This index covers every issue raised in the eight round-2 reviews and records how [PLAN v2](../../PLAN.md) resolves it. Decision IDs refer to [DECISIONS.md](../DECISIONS.md). B = BLOCKER, M = MAJOR, m = MINOR. ADOPTED-MODIFIED means the reviewer's fix was taken, but values or mechanics were changed to reconcile it with another reviewer or a lead ruling; the change is noted in the rationale.

Totals: **93 issues** (5 B, 52 M, 36 m).

| Resolution | Count |
|---|---|
| ADOPTED | 73 |
| ADOPTED-MODIFIED | 20 |
| REJECTED | 0 |

Every BLOCKER and every MAJOR is resolved.

| Reviewer | # | Sev | Resolution | Rationale | PLAN § / spec | ID |
|---|---|---|---|---|---|---|
| architect | 1 | B | ADOPTED-MODIFIED | compileSdk raised to 36, not 35. activity 1.11 and core 1.17 need 36 (L12). adb is put on PATH by doctor. | §3.8, §4.2, D0 | C43 |
| architect | 2 | M | ADOPTED | Ownership is exclusive per path and checked by a lint over `OWNERS.yaml`. The single `uv.lock` writer is A. Lockfiles are per WS. Unowned paths are now assigned. The fetch engine goes to A rather than E (same human owner, generic infra). | §5.1 | C73 |
| architect | 3 | M | ADOPTED | gt_detector runs in the sim and sends Detections on UDP 5800+i to the OffloadDetector. Video is off when headless. The vignette is synthetic only. | §3.6, sim §4 | C59 |
| architect | 4 | M | ADOPTED-MODIFIED | Kept the mesh-emu path and the router fan-out on 18088. Keepalive is 1 Hz with lost after 3 s (sim's values) instead of 2 s / 6 s. | §1.4, interfaces §7 | C54 |
| architect | 5 | M | ADOPTED | Proposal state now ends at `dispatched`, followed by an Execution per `step_idx`. HUD states added. Expects use `steps`. | §2, interfaces §4 | C64 |
| architect | 6 | M | ADOPTED-MODIFIED | Adopted the MOTION/SAFE/CONFIG classifier and the new I2. The witness is the linkshaper wire log rather than a Mock-only log, so it also works for PX4. | §2, §3.4 | C50 |
| architect | 7 | M | ADOPTED-MODIFIED | Added the profile (cruise 10), scenario lint and a re-laid vignette. The geometry is reconciled across four reviewers (NAI 1 at 250 m), and expects are anchored instead of using `by_t: 120`. | §3.6, sim §6–7 | C62, C63 |
| architect | 8 | M | ADOPTED | SEI frame_id, SDP files and Tier B `telemetry_interp`. The pts anchor is kept as a tested fallback. | §3.6, sim §4, D7 | C60 |
| architect | 9 | m | ADOPTED-MODIFIED | ScaledClock is used everywhere, and px4 forces speed 1. The variable is `EDITH_T0_NS`, not `_MS`, for precision. | §2, interfaces §1 | C61 |
| architect | 10 | m | ADOPTED | Added `alert.ce_m`, `entities[].marked`, and an enum for caret style. | interfaces §4 | C64 |
| architect | 11 | m | ADOPTED | The confirm predicate lives only in `safety/confirm_rule.py`. It is owned by C (safety moved to C per pm#9) and tested with a FakeAdapter. | §3.1, D3b | C85 |
| architect | 12 | m | ADOPTED-MODIFIED | Unit tests are Python only, `--port-base` added, and bind/send table added. Gradle heap uses the platform owner's 3g plus serial CI instead of 2g. | §4.4, interfaces §5 | C77 |
| defense_sme | 1 | M | ADOPTED-MODIFIED | Friendly association adopted, with radius max(15 m, ce_m) because ce_m is now CE90. Added I8, the D8 test and the D6 expect. | §3.5, D8, D6 | C52 |
| defense_sme | 2 | M | ADOPTED-MODIFIED | Explicit link states for TCP (3 s ping, 2 misses), mesh (12 s) and mesh-emu (1 Hz / 3 s). Expired events are dropped at flush and latest track states re-sent. The `queued_min: 5` expect is asserted on the router log. | §1.4, interfaces §7 | C54 |
| defense_sme | 3 | M | ADOPTED-MODIFIED | Synthetic on both drones, replay only in goal2, GT-relative alert expect and kinematic lint. Values are reconciled: cruise 10 instead of 8, NAI 1 at (0, 250), and 5 s instead of 10 s with ≥3 s dwell. | §3.6, sim §7 | C62, C63 |
| defense_sme | 4 | M | ADOPTED | Observe contact is frozen at confirm. Follow is limited to "me" or a teammate. `follow(uid_stream)` replaces the track version. D21 acceptance updated. | §2, §3.3, D21 | C51 |
| defense_sme | 5 | M | ADOPTED | `t-x-d-d` with `__forcedelete` on dismiss or loss, plus the uid scheme. D5 and D6 tests added. | §2, interfaces §7, D5, D6 | C53 |
| defense_sme | 6 | m | ADOPTED | `how=m-f` (UNVERIFIED). `ce_m` defined as CE90 and mapped to CoT `ce`. `hae` uses the geoid N constant. | interfaces §1, §7 | C55, C57 |
| defense_sme | 7 | m | ADOPTED | Inbound accepts XML and TAK Protocol v1 via takproto, with fixtures for both. | §2, D5 | C55 |
| defense_sme | 8 | m | ADOPTED | Rejected lexicon extended. "Repeat" is never treated as say-again. | voice §3, D4 | C66 |
| defense_sme | 9 | m | ADOPTED | Alert budget is ≤2 in any 60 s and ≤20/h mission mean. | §3.5 | C81 |
| defense_sme | 10 | m | ADOPTED | Interview guardrails restored. | §7.1 | C82 |
| defense_sme | 11 | m | ADOPTED-MODIFIED | TRL table and IVAS UNVERIFIED tag adopted. The SALUTE draft becomes P2 (D23). | §8, D23 | C80 |
| defense_sme | 12 | m | ADOPTED | Callsigns changed to VIKING 1-1…1-4. EXERCISE remarks and `m-s` for sim entities. | interfaces §7, sim §7 | C55 |
| hud | 1 | M | ADOPTED | Clear zone moved to y326, banner/card fixed at 330–424, 3-row card, hint moved to the voice row. | §3.7, hud §2 | C65 |
| hud | 2 | M | ADOPTED | `readback.rows[2]` measured at ≤490 px. Row 1 ≤400 px at 28 px, with `~` dropped at ≥1 km. Width tests in D4 and bounds lints in D11. | §3.7, hud §3, D4, D11 | C65 |
| hud | 3 | M | ADOPTED | Vector glyphs in `Glyphs.kt`, with a cmap lint. | §3.7, hud §5, D11 | C65 |
| hud | 4 | M | ADOPTED-MODIFIED | 400 ms double-tap hold, no gesture dismiss on WARNING, second pointer cancels PTT, and the tests. Undo is by slide-back rather than tap, because tap is reserved for toggle-PTT. | §3.7, hud §7, D3b, D12 | C46, C47 |
| hud | 5 | M | ADOPTED | Same BT PTT and earbud in both arms, a gesture block, the new primary DV, 6 tasks, ≥192 lures, read-aloud legibility, a dusk sub-study and a spotter. | §6, eval §4 | C72 |
| hud | 6 | m | ADOPTED | Inset label shortened, DATA on its own line, REC moved, head-ellipsized transcript. | hud §2 | C65 |
| hud | 7 | m | ADOPTED | Card-open queueing, bare-response scoping, and declutter never hides critical items. | §3.5, hud §6, D3c | C81 |
| hud | 8 | m | ADOPTED | Night inset is green-mapped, ≤8% transient APL and auto-closes after 10 s. | §3.7, hud §4 | C65 |
| hud | 9 | m | ADOPTED | One GraphicsLayer drawn into both slots with `dx` 0. T5 aspect check and T16 swatches. | §3.7, hud §8, D13b | C65 |
| hud | 10 | m | ADOPTED | APL defined precisely, the golden list expanded, and the contact sheet approved by Alisha. | hud §9, D11 | C65 |
| hud | 11 | m | ADOPTED | Hint is derived from `confirm_with`. If T7 fails, a forearm phone runs `/ui/touch` for the demo. | §1.3, §7.3, hud §2 | C65 |
| ml | 1 | B | ADOPTED | Ground-plane ENU Kalman tracker plus the lawnmower test (supersedes C17). | §3.5, D8 | C56 |
| ml | 2 | M | ADOPTED | Composed timelines, frozen splits, FA/h counted on real seconds with a Poisson CI, the R=6 s operator model, collapsed-alert recall and AFS per event. | §6, eval §2, D9 | C70 |
| ml | 3 | M | ADOPTED | `pose_est` with nav noise, CE90 including a yaw term, Monte Carlo at 90 ±3%, and CEP on synthetic only. | §3.5, sim §4, D8 | C57 |
| ml | 4 | M | ADOPTED | Pixel size measured ≥12 px at detector input. A 576×320 export in D14 (P1) with a 416² fallback. Person missions at 45–50 m and −45°. | §3.5, eval §2, D14 | C58 |
| ml | 5 | M | ADOPTED | P2 receives the same detector input. Energy is measured over Wi-Fi adb with USB unplugged, against an idle baseline. T18 records `CURRENT_NOW` semantics. | §6, eval §3, D16 | C71 |
| ml | 6 | M | ADOPTED | Cameras off with the gt detector, fps capped on wall-clock time, D8 timing measured in isolation, one full-stack run reported without a gate. | §3.6, D8 | C59 |
| ml | 7 | m | ADOPTED | Output floor 0.10, track start 0.25, IOS merge. | §3.5 | C58 |
| ml | 8 | m | ADOPTED | `license` and `derived_from` fields, an NC packaging lint, and the PyAV GPL check recorded. | §3.5, §4.2 | C84 |
| ml | 9 | m | ADOPTED | Clutter objects in gt_detector, synthetic GT for D8, and a Python 3.12 venv for D14. | D8, D14 | C84 |
| voice | 1 | M | ADOPTED | `spoken` and `written` normalizer profiles, plus ≥150 Moonshine-captured fixtures in D4. | §3.2, voice §1, D4 | C66 |
| voice | 2 | M | ADOPTED | Gazetteer aliases, with a D10a check at clean and 10 dB on 3 voices. | voice §1, sim §5, D10a | C66 |
| voice | 3 | M | ADOPTED | Exact "confirm" match, Vosk decoys with AND-agreement in P1, an audio lure suite in D10a (promoted to P0), and null confidence where the engine provides none. | §3.2, voice §5–6, D10a | C48, C74 |
| voice | 4 | M | ADOPTED | `card_shown` required, lockout measured from press start, 1.5 s grace, and the press-outcome table as D3b tests. | §3.4, voice §5, D3b | C48 |
| voice | 5 | M | ADOPTED | Companion holds a double-tap 400 ms, with a D3b test. | §3.7, D3b | C47 |
| voice | 6 | M | ADOPTED | Stop grammar widened, token spotting added, and both covered by D4 fixtures. | §3.3, voice §2, D4 | C49 |
| voice | 7 | M | ADOPTED | Mission upload and clear count as MOTION and are uploaded only after confirmation. | §2, §3.4, D3b | C50 |
| voice | 8 | M | ADOPTED | 500 ms pre-roll from finger DOWN, with a D12 test. | §1.4, §3.2, D12 | C46 |
| voice | 9 | M | ADOPTED | Procedural noise, Kokoro babble, OpenSLR 28 and an ESC-50 git clone. MUSAN and Freesound are opt-in. Range extended to −5 dB. | voice §6, D10b | C67 |
| voice | 10 | m | ADOPTED | Partials capped at ≤2 Hz and the detector at 1 Hz during PTT. Latency reported both idle and under load. | §3.2, §3.5, D10a | C58 |
| voice | 11 | m | ADOPTED-MODIFIED | Pins and the Intel-macOS note adopted. The Moonshine model goes in a WS-C lockfile instead of `ml/models.yaml` to avoid an ownership conflict. | §4.2 | C68 |
| voice | 12 | m | ADOPTED | Pre-registered definitions, its own verbalizer, and ≥100 paraphrases. | eval §1, voice §6 | C69 |
| voice | 13 | m | ADOPTED | Pointer count checked before 300 ms; a two-finger touch never opens a session; D12 test. | hud §7, D12 | C46 |
| sim | 1 | B | ADOPTED-MODIFIED | Adopted the profile values (3/10/60/60), D2 tasked at t40, an unconfirmed timeout case, jam at t300, anchored expects and lint. NAI 1 is at (0, 250) rather than (0, 200), and the timeout moves to t60 so it doesn't collide with alerts. | §3.6, sim §1, §7 | C62, C63 |
| sim | 2 | M | ADOPTED | `edith_common.px4` (POSCTL.ORBIT, ACKs, auto-disarm, mission handshake, battery params), C09 sequences, `completed` definitions, a mock\|px4 contract suite and `record-px4`. | §3.6, interfaces §6, sim §2, D2, D3a, D15 | C62 |
| sim | 3 | M | ADOPTED | `EDITH_T0_NS` with ScaledClock, params applied after boot and read back, camera wall cap. | §2, sim §1, §4 | C61, C59 |
| sim | 4 | M | ADOPTED | I7, with `stop()` cancelling tasks and retries first, tested against the wire log. | §3.4, D3b | C50 |
| sim | 5 | M | ADOPTED-MODIFIED | mesh-emu through linkshaper with a 3 s threshold, asserted on the router log. The replay lookback is lost_after + 2 s instead of 30 s. | §1.4, interfaces §7, D5 | C54 |
| sim | 6 | M | ADOPTED-MODIFIED | (a) FrameTruth is a sim-side JSONL. Detections, not FrameTruth, use 5800+i, which reconciles this with architect#3. (b) Gimbal stabilized, optical frame. | interfaces §4, sim §4 | C57, C59 |
| sim | 7 | M | ADOPTED | Image-space recall on replay, CEP on synthetic only, `geo_quality: pseudo` never triggers contact_close. | §3.5, eval §2 | C70 |
| sim | 8 | m | ADOPTED | Frames and units, fence 5001, GF params, orbit at 5 m/s, spacing ×0.7. | interfaces §6, sim §1 | C62 |
| sim | 9 | m | ADOPTED | Port wiring, truth tap, wire log, sysid 245, liveness on any message, doctor checks 14550, video jam windows. | §2, interfaces §5, sim §3 | C62 |
| sim | 10 | m | ADOPTED-MODIFIED | The pts anchor is kept as a fallback behind SEI, with a ≥99% barcode test. | sim §4, D7 | C60 |
| sim | 11 | m | ADOPTED | Determinism hash covers mover, jam schedule and in-process Mock; socket runs use tolerances. | sim §8, D2 | C62 |
| sim | 12 | m | ADOPTED | Hold is never queued for a lost asset; toast shows `D2 HOLD NOT SENT · LINK`. | §3.4, hud §6 | C50 |
| platform | 1 | B | ADOPTED | compileSdk 36 with the exact pin set. | §3.8, §4.2, D0 | C43 |
| platform | 2 | M | ADOPTED | Sample-zip-only fetch, local m2 repo with POM, conditional include, IPC AAR dropped, keystore deleted, full hashes, `--from`. | §3.8, D13a | C44 |
| platform | 3 | M | ADOPTED | Cleartext network config, AppCompat theme, permission set, `install -r -g`. | §3.8, D12, D13a | C45 |
| platform | 4 | M | ADOPTED | Pre-roll from ACTION_DOWN on `cyttsp5_mt`, click sound off, T7 DOWN→frame ≤100 ms. | §1.4, §3.2, D12, D13b | C46 |
| platform | 5 | M | ADOPTED | `dispatchTouchEvent` → InputFsm, pointer-modifier lint, toggle on confirmed tap, slide-down for the queue, raw-timed two-finger hold, "progress ring" wording. | §3.7, hud §7, D11, D12 | C46 |
| platform | 6 | M | ADOPTED | Provisioning via adb intent extras, mDNS moved to P1 with zeroconf, Robolectric test. | §1.3, §3.8, D12 | C76 |
| platform | 7 | m | ADOPTED | T0–T4 in bringup.sh, T5–T18 in the APK; registry test across both. | D13a, D13b | C74 |
| platform | 8 | m | ADOPTED | gradle.properties memory limits, committed wrapper, serial CI, Linux-only goldens. | §4.4 | C77 |
| platform | 9 | m | ADOPTED | `ptt_down.ctx.proposal_id` must match the live proposal; this is combined with the L18 lockout and `card_shown` checks. | voice §5 | C48 |
| platform | 10 | m | ADOPTED | Compositor slots come from the measured window. | §3.7, hud §8, D12 | C65 |
| pm | 1 | B | ADOPTED-MODIFIED | Resolved by L13: the repo and remote exist, there is one commit per deliverable, `dist` APKs with SHA256SUMS are handed over directly (no GitHub release required), and INSTALL.md is added. | §4.5, D0, D12, D13a | C75 |
| pm | 2 | M | ADOPTED | D13a is first and G0-critical tests are tiered for the first session. Thanksgiving and finals are noted. | §5.2, §7.1 | C74 |
| pm | 3 | M | ADOPTED-MODIFIED | NAI 1 at 250 m, D2 tasked at t40, Mock honors MPC_* and has no DLL while disarmed, lint added. Cruise is 10 m/s instead of 12, and the margin is +2 s with a deterministic pre-run instead of +10 s. | §3.6, sim §6–7 | C62, C63 |
| pm | 4 | M | ADOPTED | compileSdk 36 / targetSdk 34 is achievable (L12), so the CMP 1.7 downgrade is unneeded. | §3.8 | C43 |
| pm | 5 | M | ADOPTED-MODIFIED | Per-entity metrics on real clips; WR curve at 5/10/20% duty; CEP only in sim. Empty stretches are synthetic flyovers because no real empty footage source was found, and FA/h counts real seconds only. | §6, eval §2 | C70 |
| pm | 6 | M | ADOPTED | Primary G1 number from naive participants, B6 separate, Leq30 at the ear. | §0, §6, eval §1 | C69 |
| pm | 7 | M | ADOPTED-MODIFIED | Seeded wrong read-backs added. The lure claim is restated as 0/192 (95% UB 1.6%) per hud#5's count, instead of 0/180. | §0, eval §4 | C72 |
| pm | 8 | M | ADOPTED | Phone-native layout, same earcon plus haptic, same confirm methods, frozen at W5 (supersedes part of C21). | §6, §7.3, eval §4 | C72 |
| pm | 9 | M | ADOPTED | Om owns safety/intent/voice; Alisha alerts/hud; Simon sim/tak/cost; Arjun Pareto and integration. Risk 11 and per-WS walkthroughs with handoffs. | §5.1, §7, §9 | C73, C83 |
| pm | 10 | M | ADOPTED | Dec 12 demo-laptop e2e-px4 gate; PX4 pinned to the final release if available; frozen after Mar 5. | §7.1, §7.3 | C78 |
| pm | 11 | M | ADOPTED | Timed beat sheet, `COM_DL_LOSS_T: 8` disclosed, PTT-held lure, SAR moved to video, 75 dB fallback. | §7.3 | C78 |
| pm | 12 | m | ADOPTED | Capex, opex and TCO split; `basis` column; WTP hypothesis. | §6, eval §5, D19 | C79 |
| pm | 13 | m | ADOPTED | "Same source and hud-core, `generic` flavor", with a defined LOC metric. | §8 | C80 |
| pm | 14 | m | ADOPTED | Boost to 4 Hz for 5 s after an unconfirmed detection; the PTT 1 Hz cap takes precedence. | §3.5, D8 | C58 |

## Notes for the next round

These items still need a human decision or a device test. They are also listed in PLAN §10.

- **Ownership (C73).** PM recommended that Simon own the sim and scenarios, and that Om own the safety FSM. The team should confirm this.
- **PX4 and apt in the workspace (L14).** These remain pending approval. D15 is P1.
- **Disclosed sim tuning.** Cruise is 10 m/s and climb 3 m/s, and the live demo uses `COM_DL_LOSS_T: 8`. The mentor should accept these as disclosed simulation choices.
- **Items that need the device or ATAK-CIV, not a decision:**
  - ATAK-CIV handling of `t-x-d-d`.
  - CoT `how` code `m-f` and the meaning of `ce`.
  - Whether the SDK emits DoubleClick before TripleClick (T7).
  - B612 cmap coverage of `→` and `·` (D11 lint).
