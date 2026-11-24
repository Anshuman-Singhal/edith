# R1: Glasses Platform (Android/XR), RayNeo X3 Pro

Owner: Arjun (Hardware & Platform). Status: round 1.

Labels used below:
- **DOC**: RayNeo's docs say so.
- **SDK**: I read it in the vendor AAR or sample, both downloaded and inspected in this workspace.
- **UNVERIFIED**: must be confirmed on the device.

## Key new facts

- **The vendor SDK is public, so we can compile against it before the glasses arrive.**
  - The ARDK page links `MercuryAndroidSDK-v0.2.6-20260310143142_94a01a90.aar` (211 KB, sha256 `5d408e2c…2676`) and `MercuryAndroidSample_v0.2.6.zip` (6.4 MB, `1c78e3c4…1f47`) [ARDK].
  - The sample bundles `RayNeoIPCSDK-For-Android-V0.1.0…aar` (`15dc0613…b214`).
  - Neither ships license text. Treat them as proprietary: fetch them with a script, pin the hashes, never commit them (the xg-glass approach [XG]).
- **Android 12 is very likely.**
  - AAR manifests: minSdk 26 / targetSdk 32 (Mercury), minSdk 29 (IPC).
  - The X3 sample uses compileSdk 32, min and target 31, AGP 7.2.1, Kotlin 1.7.
  - The docs say "a complete Android 12" [DEV, FEISHU].
- **Binocular output is side-by-side (SBS), drawn by the app, not mirrored by the OS.**
  - The SDK API reference says `BaseMirrorActivity` puts left and right bindings "into a horizontally equal-split root layout".
  - The sample `VideoPlayActivity` is a *plain* Activity: a horizontal `LinearLayout` with `TextureView` (left eye) and `MirroringView` (right eye), weight 1 each.
  - Feishu says: "Android exposes a single logical screen, so UI must be rendered once per eye" [FEISHU].
  - So the logical display is probably 1280×480, with the left half going to the left eye. The exact size is UNVERIFIED (check with `wm size`).
  - This **refines hud.md §1**. Authoring one 640×480 eye canvas is right, but SBS duplication is the *primary* RayNeo path, not a fallback.
- **Signing.** The sample signs debug builds with a bundled platform keystore (`xr2-platform.jks`). Sideloaders install normally signed APKs fine [SUB, SKG], so we use the standard debug key.

## 1. Recommendations

### 1.1 App model: native Kotlin, no Unity in Phase 0

Unity can't run here, its 6DoF mode was reported unstable [SKG], and the HUD only needs screen-fixed plus compass-registered (3DoF). I endorse the architect's Kotlin + Compose Multiplatform `hud-core`.

- **Host Activity.** Extend `com.ffalcon.mercury.android.sdk.ui.activity.BaseEventActivity`.
  - Its chain is `AppCompatActivity → BaseActivity → BaseTouchActivity → BaseEventActivity` (SDK), so Compose `setContent` works.
  - We get `templeActionViewModel.state` (a Flow of `TempleAction`) and `motionEventDispatcher`.
- **Avoid `BaseMirrorActivity`/`BindingPair`.** They are ViewBinding-only and run UI code twice [BINO].
- **Our own `StereoCompositor`** (inside the architect's `DisplayAdapter`):
  - A full-screen `Row` of two 640×480 slots draws the same `HudState` with the same `DrawScope` renderer.
  - Each eye has an offset `dxL`/`dxR`, the same idea as RayNeo's `make3DEffect` parallax [3D].
  - Modes: `SBS_DUPLICATE` (RayNeo), `MONO` (phones and glasses that mirror in the OS), and `SBS_LEFT_ONLY` (debug).
  - Video is decoded once into an `ImageBitmap` and drawn in both slots. We skip `MirroringView`: it is a `View` that redraws its source on `postInvalidateDelayed` (SDK bytecode), so its latency and CPU cost are unknown.
- **Manifest.**
  - `<meta-data android:name="com.rayneo.mercury.app" android:value="true"/>`. Without it the app gets no launcher icon [QS].
  - `MercurySDK.init(this)` in `Application.onCreate`, landscape orientation, `keepScreenOn`.
  - Permissions: `CAMERA`, `RECORD_AUDIO`, `INTERNET`, `CHANGE_WIFI_MULTICAST_STATE`, `WRITE_SETTINGS`.
- **Levels.** compileSdk 34 (installed at `/opt/android-sdk`), minSdk 29 (the IPC floor; team phones also qualify), targetSdk 34. JVM target 17, AGP 8.13.x, Kotlin 2.2.x, Gradle 8.14.3, JDK 21.
- **Flavors.**
  - `rayneo`: the AARs, the meta-data and `RayNeoPlatform`.
  - `generic`: pure AOSP for any landscape Android phone, so teammates can test camera, mic, network and decode before arrival and while the single pair is checked out.

### 1.2 Input

- **Temple touchpad.**
  - It delivers raw `MotionEvent`s with X only [TP].
  - `TouchDispatcherX3` maps them to `TempleAction.Click/DoubleClick/TripleClick/LongClick/SlideForward/SlideBackward/SlideUpwards/SlideDownwards/TpSlideContinuous`, plus two-finger click and long-press callbacks (X3 only).
  - `TouchDispatcher.onKeyEvent` exists (SDK), so some input arrives as `KeyEvent`. Which keycodes is UNVERIFIED.
  - Swipe direction follows a user "natural" setting, so treat slides as semantic ±1 and offer an invert option.
- **Push-to-talk (PTT).**
  - `LongClick` has no release event, so hold-to-talk reads `ACTION_DOWN`/`ACTION_UP` from `motionEventDispatcher`.
  - Start after ≥300 ms held with |Δx| < 50 px (the SDK's `IGNORE_DELTA`). End on UP plus a 150 ms tail (voice.md).
  - The system may own right-temple long-press (quick actions) and left-temple long-press (assistant) [SKG]. If so, fall back to tap-to-toggle with an 8 s cap, or two-finger click. Test T7 decides.
- **Confirmation.** Follow hud.md: double-tap means dismiss. No single gesture commands an asset. Confirming requires voice plus a nonce.
- **Ring.** `RingIPCHelper` is documented for X2 rings only [RING]. Its separated button sends KeyEvent 336, and `setRingLongClick(false)` suppresses the dock. The ring is Phase 1; the companion's touchscreen is the backup.
- **Voice.** ASR runs on the companion. The IPC AAR has `ipc.speech.SpeechResult` (system ASR, SDK), but it is likely cloud-tied, so don't use it.

### 1.3 Sensors, network, power

- **Heading.**
  - A magnetometer exists [DEV]. RayNeo recommends `TYPE_GAME_ROTATION_VECTOR`, which has no magnetometer, so yaw is relative and drifts [IMU].
  - Use `TYPE_ROTATION_VECTOR` if it is present (UNVERIFIED).
  - Otherwise fuse GAME_RV yaw with tilt-compensated magnetic heading in a complementary filter (α≈0.98). Publish heading accuracy so the HUD can grey out the compass.
- **Camera (Camera2) [CAM].**
  - ID 0 is the RGB camera. The sample uses a 1920×1080 YUV `ImageReader` with AE range **5–10 fps**, which is a warning sign for throughput.
  - ID 1 is the VGA SLAM camera (640×480 down to 176×144).
  - Benchmark default: 1280×720 or 640×480 YUV at 10–15 fps.
- **Mic.** `AudioRecord` at 16 kHz mono in X3 `VOICE_RECOGNITION` mode (3 mics, wearer only), selected with `AudioManager.setParameters("audio_source_record=…")` and set to `=off` on release [AUDIO]. The exact X3 value is UNVERIFIED. This matches voice.md.
- **Network.**
  - Wi-Fi 6 radio (the doc lists a/b/g/n/ac) [DEV].
  - Use a dedicated travel router (~$35); AirPennNet may isolate clients (UNVERIFIED). A phone hotspot is the field fallback.
  - Discovery via mDNS `_edith._tcp` (`NsdManager`) plus a manual-IP override.
  - The architect's WebSocket on port 7400.
- **Power and screen.**
  - `FLAG_KEEP_SCREEN_ON`.
  - Brightness via `Settings.System.SCREEN_BRIGHTNESS` 0–255. The doc warns high values may reboot the device [BRIGHT], so the self-test clamps at 200.
  - Wear detection (SDK 0.2.6) may blank the display (UNVERIFIED).
  - Telemetry: `BatteryManager` `CURRENT_NOW`/`CHARGE_COUNTER`, `ACTION_BATTERY_CHANGED` (temperature, voltage), `PowerManager.getCurrentThermalStatus()` plus a listener, `getThermalHeadroom()`, and `dumpsys thermalservice`.

### 1.4 Video inset

- Agree with architect §1.2: MJPEG at 320×240, 10–15 fps, on the existing WebSocket.
- Decode with `BitmapFactory` on one worker; expect ~2–5 ms (UNVERIFIED). Keep only the latest frame, never buffer.
- Reject RTSP (Media3 buffering is typically 0.5–2 s) and WebRTC (too heavy for students).
- Phase 1 option: H.264 → `MediaCodec` with `KEY_LOW_LATENCY` (API 30) and Qualcomm's `vendor.qti-ext-dec-low-latency.enable` (UNVERIFIED on AR1). Adopt it only if T13 is over 250 ms.
- Measure latency from the companion `ts_ms`, a ping/pong clock offset, and a `Choreographer` draw timestamp.

### 1.5 On-glasses inference (benchmark only)

- LiteRT's QNN NPU support lists Snapdragon 8 Gen 1 through 8 Elite, **not AR1** [LRT].
- Try, in order (as in ml.md):
  1. LiteRT CPU (1/2/4 threads)
  2. LiteRT GPU delegate (fp16)
  3. NNAPI. It is still present on Android 12 and is the cheapest possible Hexagon path.
  4. QNN, only if its libraries load.
- Day 1: run `benchmark_model` via `adb shell`. Week 2: a `bench` screen that writes the same JSONL.
- Hypothesis: only YOLOX-Nano-class models at ≤2–5 Hz are viable on the glasses.

### 1.6 Portability: `GlassesPlatform`

| Sub-interface | Contract | RayNeo | Generic / desktop |
|---|---|---|---|
| `DisplaySink` | `eyeSize` 640×480, `stereoMode`, `eyeOffsetPx`, `setBrightness`, `keepOn` | SBS compositor | MONO / window |
| `InputSource` | `Flow<InputEvent>`: Tap, DoubleTap, TripleTap, SlideFwd/Back/Up/Down, PttDown, PttUp, TwoFingerTap, Back | TempleAction + raw DOWN/UP | keys / touchscreen |
| `MicSource` | `open(ASR\|AMBIENT\|STEREO)` → 20 ms PCM16 16 kHz frames | AudioRecord + `audio_source_record` | `VOICE_RECOGNITION` / javax.sound |
| `PoseSource` | yaw/pitch/roll, headingAccuracy, source; 20–50 Hz | RV or fused | phone RV / scripted |
| `CameraSource` | `frames(w, h, fps, YUV\|JPEG)` | Camera2 ID 0/1 | Camera2 / file replay |
| `PowerMonitor` | battery%, µA, V, °C, thermalStatus, headroom | BatteryManager / PowerManager | same / stub |
| `DeviceInfo` | model, fingerprint, SDK level, capabilities → `sys.hello` | getprop | — |

- Only the `platform-rayneo` module imports `com.ffalcon.*`, so the Phase 1 trusted-hardware port means replacing one module.
- `sys.hello` should carry `display.eyes = sbs|mono` and `input.ptt = hold|toggle`.

## 2. Interfaces and needs from other experts

- **Architect.** I accept the WebSocket envelope, the binary header and port 7400. Please add:
  - `glasses.telemetry` (1 Hz: battery, current, thermal, fps, decode ms, RTT)
  - `pose` (10 Hz, glasses→companion)
  - `input.event`
  - `clock.ping`/`clock.pong`
  - Also: keep the per-eye hot path as `DrawScope` drawing, so two renders per frame stay cheap.
- **HUD (Alisha).**
  - The safe area x30–610 / y20–460 applies **per eye**.
  - Constraints: black is transparent, text ≥16 px, lines ≥2 px, persistent APL ≤13%, ≤30 fps [DESIGN].
  - Please flag any element that must differ per eye.
  - Daylight font and colour choices come from T16.
- **Voice (Om).**
  - `PttDown`/`PttUp` carry monotonic timestamps. Audio is `pcm_s16le`, 16 kHz, 20 ms frames.
  - Mic upload is muted while `audio.down` plays.
  - T7 decides hold vs. toggle.
- **ML (Anshuman).**
  - Please send `.tflite` files (fp32/fp16/int8) with sha256, input size and where NMS runs.
  - I provide camera and pose sources and a `bench` screen that writes JSONL to app files; collect it with `adb pull`.
- **Sim.** A 320×240, 15 fps JPEG inset source with a visible frame counter.
- **PM/Hardware purchases and logistics.**
  - Travel router, 20 W USB-C power bank, a USB-C *data* cable, an IR thermometer.
  - A sign-out log for the glasses.
  - A Mac or Linux laptop for ADB, because Windows 11 needs a Zadig driver downgrade [ADBFIX].

## 3. What can be built pre-arrival, and how to verify it here

There is no `/dev/kvm`, so there is **no emulator and no instrumented tests**. Robolectric's API 31 jar (143 MB) is reachable on Maven Central, and the Android SDK is already at `/opt/android-sdk`.

1. **`scripts/fetch_rayneo_sdk`.** Download the AARs and sample, check the hashes, and place them in a git-ignored `glasses/platform-rayneo/libs/`.
   - Verify: hashes match, and `classes.jar` contains `BaseEventActivity` and `TempleAction`.
2. **Gradle project `glasses/`.** Modules: `hud-core` (KMP), `platform-api`, `platform-rayneo`, `platform-generic`, `app-android` (flavors `rayneo`/`generic`), `emulator-desktop`.
   - Settings for this machine (2 CPU / 7 GB): `org.gradle.jvmargs=-Xmx3g`, Kotlin daemon 1.5 GB, no parallel.
   - Verify: `assembleRayneoDebug` and `assembleGenericDebug` both succeed.
3. **APK assertions** (a Gradle check task using `aapt2 dump badging`):
   - the meta-data flag is `true`
   - minSdk is 29
   - landscape orientation
   - required permissions are present
   - Mercury classes appear only in the `rayneo` APK
4. **JVM unit tests:**
   - PTT state machine and gesture→intent map
   - heading fusion: synthetic quaternion/mag streams, drift, 0/360° wrap
   - compositor geometry for 1280×480, 640×480 and phone sizes
   - latest-frame queue
   - clock-offset estimator
   - telemetry vs. schema fixtures
5. **Robolectric (SDK 31):**
   - the Activity starts with `MercurySDK.init`
   - injected `MotionEvent`s yield `PttDown`/`PttUp`
   - camera and mic are released, and `audio_source_record=off` is set, on pause
6. **`SelfTestActivity`.** Screens T0–T18 from §5, each writing `selftest/<ts>.json`. The logic is JVM-tested; the screens only run for real on the device.
7. **Desktop SBS.** `emulator-desktop --sbs` renders 1280×480 exactly as the glasses do and produces golden PNGs headlessly.
8. **Optional:** pre-flight the `generic` flavor on a teammate's Android phone. This is the only real-device evidence possible before arrival.

## 4. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Display isn't 1280×480 SBS | `stereoMode` is a runtime switch, set from T5 in about an hour |
| Battery is 245 mAh: ~30 min of continuous video [NBC], "just over an hour" mixed [SKG] | Camera off by default, inset transient, 30 fps cap. Sessions ≤30 min, power bank between runs. Run-while-charging is UNVERIFIED (T14) |
| Thermal throttling | At `MODERATE`: inset to 5 fps, camera off. At `SEVERE`: HUD only |
| System steals long-press; touchpad over-sensitive [SKG] | Toggle-PTT fallback; confirm needs voice + nonce; false-trigger test T7 |
| Magnetometer bias on the head | Calibration prompt, accuracy flag, companion GPS-course fallback |
| Firmware/SDK drift (0.2.5 changed the swipe direction) | Record `ro.build.fingerprint`, avoid OTA, pin SDK hashes |
| One device for five people | `generic` flavor, desktop SBS emulator, scripted device tests, sign-out sheet |
| Vendor provenance (TCL) and proprietary AARs | SDK confined to `platform-rayneo`, LAN-only, no RayNeo cloud or speech; Phase 1 swaps the module |
| Drawing Compose twice is too slow on AR1 | `View`/`Canvas` backend, or render once offscreen and blit twice |

## 5. Day-one bring-up checklist

Run the self-test APK plus the RayNeo sample APK as a known-good baseline. Log results with the build fingerprint to `docs/bringup/<date>.json`.

| # | Test | Procedure | Pass |
|---|---|---|---|
| T0 | Identity | `getprop` release/sdk/model/board/fingerprint; `dumpsys sensorservice` | Recorded; API 31–32 confirmed or flagged |
| T1 | ADB (USB) | Settings → General → swipe left ×10 on About Device; enable App Lab [ADBCMD, SUB]; `adb devices` | Device listed |
| T2 | ADB (Wi-Fi) | `adb tcpip 5555`, then `adb connect ip:5555`, then `install -r` | Works, or USB-only noted |
| T3 | Install | Install sample + ours | Both in the launcher; no crash in 5 min |
| T4 | Screen mirror | `scrcpy --display 0`; if black, set multi-pass [ADBSCR] | Mirror usable for demos |
| T5 | Binocular | `wm size`; L/R test pattern with grid and safe-area box; right-eye offset ±10 px | Size recorded; one fused image, no double vision; corners visible; ≤5% janky frames at 30 fps (`gfxinfo`) |
| T6 | Touch | Log raw events + `TempleAction`, 20 trials per gesture | ≥19/20 each; keycodes recorded |
| T7 | PTT | Hold right temple 1 s, left temple 1 s, two-finger hold; 5 min of normal wear and frame adjusting | Our app gets DOWN/UP (or choose toggle); touch→"Listening" <100 ms; **0** confirm-class false triggers |
| T8 | Heading | List sensors; N/E/S/W vs. a phone compass after figure-8 calibration; 5 min still | Error ≤15°; drift ≤5°/5 min (target) |
| T9 | Mic | 10 s in each RayNeo mode and each stock source; bystander at 1 m; 20 commands through the companion ASR | Rate and channels as requested; wearer ≥10 dB above bystander; quiet WER ≤10% |
| T10 | Camera | Enumerate IDs/sizes/fps; preview 640×480 and 1280×720 for 5 min | ≥10 fps sustained at 720p; no session errors |
| T11 | Wi-Fi | In-app TCP up/down to the companion; 2.4 vs. 5 GHz; router and hotspot | ≥10 Mbit/s each way; RTT p95 <30 ms (router) |
| T12 | WS soak | 30 min, then kill the companion | Reconnect <3 s; HUD shows staleness |
| T13 | Inset | 320×240 MJPEG at 15 fps with a frame counter; list H.264 codecs | Latency p95 ≤150 ms, drops <2%, decode p95 <10 ms |
| T14 | Battery | 100→20% at full load (HUD + mic + inset + camera at 10 fps) and HUD-only; log every 10 s; also try while charging | Full load ≥30 min, HUD-only ≥60 min (targets); `CURRENT_NOW` readable |
| T15 | Thermals | Same runs plus thermal status, headroom, IR temperature | No `MODERATE` within 20 min of HUD + audio; camera onset time recorded |
| T16 | Daylight | In sun: brightness 50–200, fonts 16–32, green/cyan/amber/white; 3 viewers | Banner read in <1 s by 3/3; no reboot |
| T17 | Wear/sleep | Remove, replace, idle 10 min | Behaviour documented; clean resume |
| T18 | Inference | `benchmark_model` CPU/GPU/NNAPI/QNN on YOLOX-Nano fp32/fp16/int8 | p50/p95 ms, mJ/inference, thermal status recorded |

## 6. Open questions

1. What are the true logical display size and stereo pipeline? Is there a per-unit binocular offset? (T5)
2. Can a foreground app receive or suppress long-press and two-finger gestures? Which KeyEvents arrive? (T6, T7)
3. What is the exact X3 `audio_source_record` value, and does it apply hidden noise suppression or AGC? (T9, with Om)
4. Is `TYPE_ROTATION_VECTOR` exposed, and how accurate is the magnetometer on the head? (T8)
5. Can the glasses run while charging? Does wear detection blank the display during benchmark runs? (T14, T17)
6. Is there an NNAPI→Hexagon path or any usable QNN path on AR1? (T18)
7. What are the redistribution terms for MercuryAndroidSDK? Ask RayNeo; until then, fetch it with the script and don't commit it.
8. Does a teammate own an Android phone for the `generic` pre-flight?

## Sources

- [QS] https://rayneo.gitbook.io/rayneo-devdoc/x-xi-lie/android-kai-fa/kuai-su-kai-shi
- [ARDK] https://rayneo.gitbook.io/rayneo-devdoc/x-xi-lie/android-kai-fa/ardk-xia-zai
- [BINO] https://rayneo.gitbook.io/rayneo-devdoc/x-xi-lie/android-kai-fa/neng-li-jie-shao/he-mu-chu-li
- [TP] https://rayneo.gitbook.io/rayneo-devdoc/x-xi-lie/android-kai-fa/neng-li-jie-shao/chu-kong-ban-guan-li
- [3D] https://rayneo.gitbook.io/rayneo-devdoc/x-xi-lie/android-kai-fa/neng-li-jie-shao/3d-xiao-guo-shi-xian
- [IMU] https://rayneo.gitbook.io/rayneo-devdoc/x-xi-lie/android-kai-fa/neng-li-jie-shao/imu-shu-ju-huo-qu
- [CAM] https://rayneo.gitbook.io/rayneo-devdoc/x-xi-lie/android-kai-fa/neng-li-jie-shao/camera-kai-fa
- [AUDIO] https://rayneo.gitbook.io/rayneo-devdoc/x-xi-lie/android-kai-fa/neng-li-jie-shao/yin-pin-kai-fa
- [RING] https://rayneo.gitbook.io/rayneo-devdoc/x-xi-lie/android-kai-fa/ipc-sdk/jie-zhi-shi-yong
- [DEV] https://rayneo.gitbook.io/rayneo-devdoc/x-xi-lie/she-bei-jie-shao
- [DESIGN] https://rayneo.gitbook.io/rayneo-devdoc/x-xi-lie/she-ji-gui-fan
- [BRIGHT] https://rayneo.gitbook.io/rayneo-devdoc/chang-jian-wen-ti/faq/x-xi-lie-she-zhi-ping-mu-liang-du
- [ADBCMD] https://rayneo.gitbook.io/rayneo-devdoc/chang-jian-wen-ti/adb-tiao-shi/adb-zhi-ling
- [ADBSCR] https://rayneo.gitbook.io/rayneo-devdoc/chang-jian-wen-ti/adb-tiao-shi/adb-lian-jie-ji-tou-ping
- [ADBFIX] https://rayneo.gitbook.io/rayneo-devdoc/chang-jian-wen-ti/faq/x3pro-adb-wu-fa-shi-bie-jie-jue-fang-fa
- [FEISHU] https://leiniao-ibg.feishu.cn/wiki/FJ5ow2TCri336zkwLpuciIiJn5d
- [XG] https://github.com/hkust-spark/xg-glass-sdk (Apache-2.0; RayNeo X2 validated, X3 Pro "untested"; host minSdk 29 / target 34; JPEG-only Camera2 stream ≤15 fps)
- MentraOS: the only RayNeo reference in the current repo is an X2 image asset; no driver. https://github.com/Mentra-Community/MentraOS
- [SUB] https://biggthed.substack.com/p/rayneo-x3pro-sideload-apps-using
- [SKG] https://skarredghost.com/2025/12/17/rayneo-x3-pro-review/
- [NBC] https://www.notebookcheck.net/Rayneo-X3-Pro-review-Promising-AR-smart-glasses-with-one-big-limitation.1190970.0.html
- [LRT] https://developers.google.com/edge/litert/android/npu/qualcomm
- Qualcomm, "Get Started with RayNeo X3 Pro AR Development". The page needs JavaScript and could not be read here (UNVERIFIED): https://www.qualcomm.com/developer/project/get-started-with-rayneo-x3-pro-ar-development
