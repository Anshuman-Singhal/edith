# Glasses bring-up tests T0–T18 (normative, PLAN v3)

Owner: WS-G (Arjun). This table is the **normative** definition of the bring-up tests (C104). It is seeded from [council/r1/platform.md §5](../council/r1/platform.md#5-day-one-bring-up-checklist) with the v2/v3 changes applied. The D13a/D13b registry entries and `CHECKLIST.md` are **generated from this file**; edit tests here only.

- **Runners.** T0–T4 run host-side in `tools/bringup.sh`. T5–T18 run in the `:selftest` APK (`SelfTestActivity`), which needs no companion.
- **Host peer.** T9, T11 and T13 talk to `./edith glasses selftest --serve` (aiohttp, no companion dependency, `/v1/selftest` on :7400; do not run the companion at the same time). `bringup.sh` provisions the APK with `--es peer ws://<ip>:7400/v1/selftest`.
- **Results.** Each run writes `runs/bringup/<ts>/results.json` (validated against its schema) plus the build fingerprint. `bringup.sh` pulls it.
- **Tier `g0`** marks the G0-critical tests for session 1 (Dec 10 gate): T0, T5, T6, T7, T9, T13, T14.
- **Prerequisite.** The `rayneo` flavor's `Application.onCreate` calls `MercurySDK.init` (otherwise `BaseEventActivity` throws `UninitializedPropertyAccessException`) [probed by platform r3].

| # | Tier | Owner | Test | Procedure | Pass |
|---|---|---|---|---|---|
| T0 | g0 | Arjun | Identity | `getprop` release/sdk/model/board/fingerprint; `dumpsys sensorservice` | Recorded; API 31–32 confirmed or flagged |
| T1 | — | Arjun | ADB (USB) | Settings → General → swipe left ×10 on About Device; enable App Lab; `adb devices` | Device listed |
| T2 | — | Arjun | ADB (Wi-Fi) | `adb tcpip 5555`, then `adb connect ip:5555`, then `install -r` | Works, or USB-only noted |
| T3 | — | Arjun | Install | Install the vendor sample + ours. On `INSTALL_FAILED_UPDATE_INCOMPATIBLE` (debug key from another machine), `bringup.sh` uninstalls, reinstalls and re-provisions (C106) | Both in the launcher; no crash in 5 min |
| T4 | — | Arjun | Screen mirror | `scrcpy --display 0`; if black, set multi-pass | Mirror usable for demos |
| T5 | g0 | Alisha | Binocular | `wm size`; L/R test pattern with grid and safe-area box; right-eye offset ±10 px; **circle-aspect check**; L-only and R-only glyphs | Size recorded; one fused image, no double vision; circle not squashed (else the stereo mode is wrong); corners visible; ≤5% janky frames at 30 fps (`gfxinfo`) |
| T6 | g0 | Arjun | Touch | Log raw events + `TempleAction`, 20 trials per gesture; record the system "natural mode" slide direction | ≥19/20 each; keycodes and slide direction recorded |
| T7 | g0 | Arjun | PTT | Hold right temple 1 s, left temple 1 s, two-finger hold; 5 min of normal wear and frame adjusting; log the raw event sequence of a triple-tap | Our app gets DOWN/UP (or choose toggle); **DOWN → first captured audio frame ≤100 ms**; **0** confirm-class false triggers |
| T8 | — | Arjun | Heading | List sensors; N/E/S/W vs. a phone compass after figure-8 calibration; 5 min still | Error ≤15°; drift ≤5°/5 min (target) |
| T9 | g0 | Om | Mic | 10 s in each RayNeo mode and each stock source; bystander at 1 m; 20 commands. PCM streams to `selftest --serve`, which writes WAVs to `runs/bringup/<ts>/` for offline ASR scoring | Rate and channels as requested; wearer ≥10 dB above bystander; quiet WER ≤10% (offline) |
| T10 | — | Arjun | Camera | Enumerate IDs/sizes/fps; preview 640×480 and 1280×720 for 5 min | ≥10 fps sustained at 720p; no session errors |
| T11 | — | Arjun | Wi-Fi | TCP up/down against `selftest --serve`; 2.4 vs. 5 GHz; router and hotspot | ≥10 Mbit/s each way; RTT p95 <30 ms (router) |
| T12 | — | Arjun | WS soak | Full app: 30 min, then kill the companion | Reconnect <3 s; HUD shows staleness |
| T13 | g0 | Arjun | Inset | `selftest --serve` sends 320×240 JPEG at 15 fps with `frame_id`; the glasses echo `{frame_id, recv→decoded ms}`. Latency is RTT-based, so no clocks are compared. List H.264 codecs | Latency p95 ≤150 ms, drops <2%, decode p95 <10 ms |
| T14 | g0 | Arjun | Battery | 100→20% at full load (HUD + mic + inset + camera at 10 fps) and HUD-only; log every 10 s; also try while charging | Full load ≥30 min, HUD-only ≥60 min (targets); `CURRENT_NOW` readable |
| T15 | — | Arjun | Thermals | Same runs plus thermal status, headroom, IR temperature | No `MODERATE` within 20 min of HUD + audio; camera onset time recorded |
| T16 | — | Alisha | Daylight | In sun: brightness 50–200, fonts 16–32, swatches `fg` / `friend` / `#FFD400` / `#FF3030`; 3 viewers | Banner read in <1 s by 3/3; no reboot |
| T17 | — | Arjun | Wear/sleep | Remove, replace, idle 10 min | Behaviour documented; clean resume |
| T18 | — | Arjun, Anshuman | Inference | `benchmark_model` CPU/GPU/NNAPI/QNN on YOLOX-Nano fp32/fp16/int8; record `CURRENT_NOW` sign, units and update period | p50/p95 ms, mJ/inference, thermal status, `CURRENT_NOW` semantics recorded |
