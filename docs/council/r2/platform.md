VERDICT: CHANGES REQUIRED

Reviewer: glasses platform (Android/XR) engineer, round 2. [probed] = checked in this workspace today. [SDK] = read from the MercuryAndroidSDK 0.2.6 bytecode.

1. **BLOCKER. §3.8 Levels, §4.2, D0, D12: compileSdk 34 cannot build Compose 1.9.**
   - Problem: CMP 1.9.x pulls `androidx.compose.ui:ui-android` 1.9.x, whose AAR metadata says `minCompileSdk=35`. `activity` 1.11 and `core` 1.17 need 36 [probed]. `checkRayneoDebugAarMetadata` will fail, so D12 cannot pass.
   - Fix: replace the Levels line with: "compileSdk **36**; install `platforms;android-36` and `build-tools;36.0.0` with sdkmanager into `/opt/android-sdk` (writable; repo reachable [probed]); targetSdk 34; minSdk 29; JVM target 17."
   - D0 `doctor` should print "Android SDK 36".
   - Exact pins for `libs.versions.toml`:
     - AGP **8.13.2** (the last 8.x; AGP 9 needs Gradle 9)
     - Kotlin **2.2.21**, CMP **1.9.3**
     - Ktor **3.3.3** (3.4+ is built on Kotlin 2.3 stdlib)
     - kotlinx.serialization **1.9.0** (1.10+ needs Kotlin 2.3)
     - coroutines 1.10.2
     - Robolectric 4.16.1 with `@Config(sdk=[31])`
   - §4.2's unpinned "Ktor 3.x" resolves to 3.6.1 (built on Kotlin 2.3.21) [probed].

2. **MAJOR. §3.8 SDK handling, D12: local AAR files break the build and drop dependencies.**
   - (a) AGP rejects direct local `.aar` dependencies in a library module when it bundles an AAR, so `:platform-rayneo:assemble` and `build` fail.
   - (b) A file AAR has no POM. The SDK's runtime dependencies, which I confirmed in its bytecode, would be missing: appcompat, fragment, activity, lifecycle viewmodel/runtime-ktx, recyclerview, viewbinding and kotlinx-coroutines. The result is a `NoClassDefFoundError` in `BaseEventActivity` [SDK].
   - Fix, `fetch_rayneo_sdk.sh`:
     - Download **only the sample zip**. Its `app/libs` Mercury AAR is byte-identical to the standalone one.
     - Write a local Maven repo at `glasses/platform-rayneo/libs/m2/com/ffalcon/mercury-sdk/0.2.6/` with a generated POM that lists those dependencies (versions from the sample's `build.gradle`).
     - In `settings.gradle.kts`, add `maven(uri("platform-rayneo/libs/m2")) { content { includeGroup("com.ffalcon") } }`.
     - Include `:platform-rayneo` and the `rayneo` flavor only when that repo exists. Otherwise print a warning, so `generic` still builds.
   - Drop the IPC AAR from the build. The ring and system speech are out of Phase 0.
   - The gitbook links are tokenized Firebase URLs that change whenever the doc is edited. Add `--from <local zip>`.
   - The script deletes `xr2-platform.jks` (a vendor platform keystore) after extraction.
   - `sdk.lock` full hashes [probed], replacing "recorded on first fetch":
     - sample zip `1c78e3c488d805bf8a1f78edbc40c959a50bb33ee1e8d4d55c64555351341f47`
     - Mercury AAR `5d408e2c5d80e8ae746c42abbda50012b50617005adfeb397661bec9c9be2676`
     - IPC AAR `15dc0613cafbe584699fcb4d0b6412d383bfb54a555b3f79ec50329d0002b214`

3. **MAJOR. §3.8 Manifest: three day-one launch failures.**
   - (a) Targeting API ≥28 blocks `ws://`: OkHttp throws "CLEARTEXT communication not permitted". Add `network_security_config.xml` with `<base-config cleartextTrafficPermitted="true">` (Phase 0 is LAN-only; Phase 1 uses wss). The aapt2 check should assert it.
   - (b) `BaseEventActivity` extends `AppCompatActivity` [SDK], so the activity needs `Theme.AppCompat.NoActionBar` with `windowBackground #000`. Without it the app throws `IllegalStateException` at launch.
   - (c) `WRITE_SETTINGS` is a special app-op that install cannot grant. Remove it and `CHANGE_WIFI_MULTICAST_STATE` (the glasses never multicast). Add `ACCESS_NETWORK_STATE`. In-app brightness uses `window.attributes.screenBrightness`; the T16 sweep uses `adb shell settings put system screen_brightness N`.
   - `bringup.sh` installs with `adb install -r -g`, because permission dialogs on the glasses are impractical.

4. **MAJOR. §1.4 Loop 1, §3.7, §3.8: PTT clips the start of speech.**
   - Problem: `ptt_down` fires only after 300 ms, so the first ≥300 ms of the utterance is lost. That is usually the callsign, which turns into say-again and depresses G1 intent accuracy.
   - Fix, replacing the Loop 1 opening:
     - "On right-temple ACTION_DOWN, open AudioRecord and buffer locally. The right pad is InputDevice `cyttsp5_mt` [SDK `MyTouchUtils.X3_RIGHT_NAME`].
     - At 300 ms held, send `input.event{ptt_down, t_mono_ms = DOWN time}` and flush the buffered frames first.
     - On UP before 300 ms, discard the buffer. Nothing is uploaded and the mic is released."
   - Turn off the SDK click sound (`toggleSoundEffect`) while PTT is armed so it isn't recorded.
   - T7 pass criterion: DOWN → first captured frame ≤100 ms.

5. **MAJOR. §3.7 Temple gestures, §3.8: input routing and gesture conflicts.**
   - (a) `BaseTouchActivity` handles temple input in `onTouchEvent` [SDK]. That runs only if no view consumed the event, so any `pointerInput` or `clickable` in the Compose tree silently swallows the temple.
     - Fix: `HudActivity` overrides `dispatchTouchEvent` to feed our own `InputFsm` first, then calls super.
     - Add a lint: hud-core has no pointer modifiers.
     - The FSM is SDK-independent, so Robolectric tests it in both flavors. Under Robolectric, `DeviceUtil.isX3Device()` is false and the SDK falls back to `TouchDispatcherX2`, so SDK-path tests prove nothing about the X3.
   - (b) The toggle-PTT fallback collides with Tap = show queue and with the first tap of a double or triple tap.
     - In the SDK, Click arrives via `onSingleTapConfirmed`, and DoubleClick is held 450 ms waiting for a third tap [SDK].
     - Fix: toggle = confirmed single `Click`; "show queue" moves to SlideDown; TripleClick = STOP, which fires on the third tap with no delay. Note that CANCEL/DISMISS takes +450 ms.
   - (c) The SDK's `DoubleFingerLongClick` fires at the system long-press timeout, not at 1 s.
     - Fix: time two-finger holds from raw pointer events, send `duration_ms`, and have the companion reject anything under 1000 ms.
     - Rename "with ring" to "with progress ring". The current wording reads as the RayNeo ring accessory.

6. **MAJOR. §1.3, §2.3 `sys.hello.token`: provisioning has no path onto the device.**
   - Problem: the glasses have no keyboard, so the per-run token and the companion IP cannot be entered. mDNS needs python `zeroconf`, which §4.2 does not list.
   - Fix:
     - `./edith glasses install` and `bringup.sh` run `adb shell am start -n <pkg>/.HudActivity --es ws ws://<ip>:7400/v1/ws --es token <t>`, and the app persists both in SharedPreferences.
     - The companion prints this line at startup.
     - mDNS moves to P1, with `zeroconf` (LGPL-2.1) added then.
     - Add a D12 Robolectric test: intent extras → connection config.

7. **MINOR. D13: wrong test location.** T1–T4 (ADB, Wi-Fi ADB, install, scrcpy) run on the host, not in the APK. Fix: "`bringup.sh` runs T0–T4; `SelfTestActivity` runs T5–T18; the registry test asserts 19 tests across both, each with a pass criterion."

8. **MINOR. §5, D11/D12: 7 GB budget.**
   - `glasses/gradle.properties`: `org.gradle.jvmargs=-Xmx3g`, `kotlin.daemon.jvmargs=-Xmx1536m`, `org.gradle.parallel=false`, `org.gradle.workers.max=2`; Robolectric `maxHeapSize=1g`.
   - Commit the Gradle 8.14.3 wrapper.
   - `./edith ci` runs the glasses build serially, never alongside e2e.
   - Goldens are approved on Linux only, because Skia text raster differs by OS; on other OSes `golden` runs lints only.

9. **MINOR. §3.4 voice-confirm rule.** Replace "a press that started after the card appeared" with "a press whose `ptt_down.ctx.proposal_id` equals the live proposal". This uses the existing field and needs no cross-clock comparison.

10. **MINOR. §3.8 Display.** `StereoCompositor` derives each slot from the measured window (`w/2 × h` in SBS, `w × h` in MONO) and scales the 640×480 canvas to fit. Don't hard-code 640.
