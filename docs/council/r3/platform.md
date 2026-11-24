VERDICT: CHANGES REQUIRED

Reviewer: glasses platform (Android/XR), round 3. [probed] = built or ran in this workspace today. I built a scratch project with the exact v2 pins: AGP 8.13.2, Kotlin 2.2.21, CMP 1.9.3, Ktor 3.3.3, serialization 1.9.0, compileSdk 36 / target 34 / min 29. It included a KMP `hud-core` (jvm + android, `rememberGraphicsLayer`), an app with `rayneo`/`generic` flavors, and Mercury 0.2.6 served from a local m2 repo with a generated POM.
- `assembleRayneoDebug` and `assembleGenericDebug` both succeed, in 3 min from a cold cache, peaking at about 3.7 GB.
- Robolectric 4.16.1 at `sdk=31` passes in both flavors.
- The sample zip and AAR sha256 match `sdk.lock`.

## r2 issues

| # | Status | Note |
|---|---|---|
| 1 | FIXED | Pins and levels build [probed] |
| 2 | FIXED | m2 + POM resolves, and the rayneo APK packages it [probed] |
| 3 | FIXED | |
| 4 | FIXED | |
| 5 | FIXED | |
| 6 | FIXED | Covers HudActivity only. The selftest APK is not covered; see N1 |
| 7–10 | FIXED | |

## Remaining / new issues

**N1. MAJOR (new in v2). D13a: G0-critical T9 and T13 cannot run in session 1.**
- **Problem:**
  - C74 made `:selftest` standalone and earlier than the companion. It has no WS client (no hud-core, no Ktor), no peer to talk to and no provisioning.
  - T13 needs a 15 fps MJPEG source with frame counters. T9 needs audio to go somewhere.
  - The T0–T18 procedures and pass criteria exist only in `council/r1/platform.md §5`. Nothing in PLAN or spec is normative for them, and that copy still says "amber" and lacks the v2 criteria.
  - The registry test checks that criteria exist, not that the tests can run.
- **Fix:**
  - **(a)** Add a `docs/bringup/TESTS.md` (WS-G) as the normative T0–T18 table. Seed it from r1 §5 with the v2 changes:
    - T5 circle-aspect;
    - T7 raw triple-tap log and DOWN→first frame ≤100 ms;
    - T16 swatches `fg/friend/#FFD400/#FF3030`;
    - T18 `CURRENT_NOW`.
    - D13a/D13b registry entries are generated from it.
  - **(b)** Add `./edith glasses selftest --serve` (in `tools/edith_tools/commands/glasses.py`, WS-G; aiohttp, no companion dependency) with `/v1/selftest` on :7400:
    - **T13:** sends 320×240 JPEG at 15 fps with frame_id. The glasses echo `{frame_id, recv→decoded ms}`. Latency is RTT-based, so no clocks are compared.
    - **T9:** receives PCM and writes WAVs to `runs/bringup/<ts>/` for offline ASR scoring.
    - **T11:** TCP throughput.
  - **(c)** `:selftest` may also depend on OkHttp 4.12.
  - **(d)** `bringup.sh` provisions it with `--es peer ws://<ip>:7400/v1/selftest`.
  - **(e)** New D13a acceptance test: a JVM test runs the selftest T13 and T9 clients against `selftest --serve` on localhost, and the result JSON validates.

**N2. MAJOR (interface). The real client's `card_shown` emission is untested.**
- **Problem:** L18/C48 make `hud.event{card_shown}` a precondition for every confirm. Only `fake_glasses.py` (Python) is tested emitting it (D3a, D6, D10a).
  - No D11 or D12 test covers the Kotlin path. On the device, either every confirm fails or the event fires on receipt instead of on draw, so the safety claim is unproven.
- **Fix:** add this to D11, where hud-core owns the WS client and renderer:
  - Emit `card_shown{ref=proposal_id}` exactly once per proposal, from the draw pass of the first frame that contains the card (not on message receipt).
  - Re-emit after reconnect while the card is visible.
  - Emit `card_cleared` on removal.
  - `alert_shown` follows the same rule.
  - Test: the emulator against the real companion with Mock in `./edith test integration`. A CONFIRM WAV is accepted only after the emulator renders. With emission suppressed, the confirm is rejected.

**m3. [probed] `aapt2 dump badging` prints neither application meta-data, the theme nor `networkSecurityConfig`.** The D12/D13a checks would fail as written.
- Use `aapt2 dump xmltree --file AndroidManifest.xml` instead, and resolve the theme parent with `aapt2 dump resources`.
- "Permission set exact" must allow `<pkg>.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION`, which androidx.core adds.

**m4. A D13a acceptance test cannot pass.** "Without the SDK … `assembleGenericDebug` still succeeds" fails because no module has a `generic` flavor until D12. In D13a, assert instead that `./gradlew help :platform-api:assemble` succeeds and prints the warning.

**m5. [probed] `MercurySDK.init` must run in a flavor `Application.onCreate`, as the SDK doc requires.** Without it, `BaseEventActivity`'s constructor throws `UninitializedPropertyAccessException` (from `TouchDispatcherX2`). This applies to `:selftest` too. Note it on the §3.8 `platform-rayneo` line.

**m6. InputFsm does not separate a hold from a slide.**
- PTT should require movement below touch slop for the first 300 ms. Otherwise a slow slide opens PTT and breaks the `slide_back` undo.
- The SDK doc says fwd/back direction follows the system "natural mode" setting. Map it, or record it in T6.
- D12 test: a 400 ms slide emits `slide_*` and no `ptt_down`.

**m7. Debug signing keys differ between machines.** APKs built here and APKs rebuilt on a team laptop are signed with different debug keys, so `install -r` fails with `INSTALL_FAILED_UPDATE_INCOMPATIBLE`. `bringup.sh` and `glasses install` should detect this, uninstall, reinstall and re-provision.

**m8. POM versions.** The sample `build.gradle` pins only appcompat 1.3.0, fragment-ktx 1.5.3 and lifecycle-runtime-ktx 2.5.1. Pin the rest in the fetch script: activity-ktx 1.5.1, lifecycle-viewmodel-ktx 2.5.1, recyclerview 1.2.1, viewbinding 7.2.1, coroutines-android 1.6.4. Gradle upgrades them to the Compose set either way [probed].

## Can WS-G's part of Phase B be built here now?

Yes. It needs no PX4 or apt. Maven Central returned one transient HTTP 429 during the probe, so CI should retry once. With N1, N2, m3 and m4 fixed, the D12/D13a acceptance tests prove their claims. Everything else that depends on the device is correctly deferred to T-tests.
