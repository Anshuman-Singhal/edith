# R1 — Edge ML / Computer Vision (Goal 2 + edge-vs-offload benchmark)

Author: ML/CV expert. Scope: detection of **person / vehicle (/ drone, later)** only. No faces, no identity, no re-identification, no targeting. Detections are typed *unknown* and feed awareness alerts only (aligned with architect §1.3).

**Measured in this workspace (2-vCPU Xeon @2.1 GHz, ONNX Runtime 1.29 CPU EP, batch 1, p50 over 15 runs).** I fed random tensors for timing, and ran 40 VisDrone-DET val images (960×540) for zero-shot recall at conf>0.35 and IoU≥0.5. Person = `pedestrian`+`people`; vehicle = `car/van/truck/bus`.

| Model (COCO weights) | Input | 1 thr | 2 thr | Person recall | Vehicle recall |
|---|---|---|---|---|---|
| YOLOX-Nano | 416 | 16 ms | 13 ms | 0.05 | 0.17 |
| YOLOX-Tiny | 416 | 62 ms | 40 ms | 0.07 | 0.33 |
| YOLOX-Tiny, 2×2 tiles | 4×416 | ~250 ms | ~160 ms | **0.20** | **0.56** |
| YOLOX-S | 640 | 257 ms | 167 ms | 0.10 | 0.51 |
| D-FINE-N | 640 | 143 ms | 100 ms | 0.04 | 0.20 |
| D-FINE-N | 416 | 71 ms | 50 ms | — | — |
| D-FINE-N int8 (dynamic quant) | 640 | 466 ms | 300 ms | — | — |
| RT-DETRv2-R18 | 640 | 681 ms | 424 ms | 0.29 | 0.67 |

Takeaways: (a) 82% of VisDrone persons in the sample are under 32×32 px. COCO weights are **unusable for people at VisDrone altitudes**. Fine-tuning plus tiling is the lever, not the choice of architecture. (b) Dynamic int8 on x86 is *slower* for DETRs, so quantize with static QDQ per target. (c) A CNN detector is ~2–3× cheaper per accuracy point on this CPU than the DETRs.

---

## 1. Recommendations

### 1.1 Detector
- **Primary: YOLOX (Apache-2.0).** Use Tiny@416 on the companion and Nano@416 as the glasses candidate. It is pure-conv, so it converts cleanly ONNX→TFLite (onnx2tf) and quantizes to int8 for Hexagon/QNN. Official ONNX files exist, PyTorch training code is simple, and it is the fastest here (table). COCO AP: Nano 25.8, Tiny 32.8 at 416 [YOLOX].
- **Fallback / accuracy tier: D-FINE (Apache-2.0)**, N (4 M params, 42.8 AP) / S (10 M params, 48.5 AP). It is NMS-free, supported in HF `transformers`, and ships ONNX on `onnx-community`. A LiteRT export of D-FINE-S already exists, but it splits into two graphs and its Graph B takes ~134–172 ms on a Snapdragon 8 Elite-class phone. That reads as **too heavy for AR1**, so D-FINE is a companion-only tier [D-FINE, LiteRT-DFINE].
- **Semester-2 comparison candidates.** RT-DETRv2-R18 (Apache-2.0): best zero-shot recall here, but 424 ms, so it serves as an offline/teacher/auto-label model. RF-DETR-Nano (Apache-2.0, 48.4 COCO AP, beats D-FINE-N on COCO): its CPU cost is UNVERIFIED (DINOv2 backbone). NanoDet-Plus-m (Apache-2.0, 30.4 AP@416, 1.17 M params, ~20 ms on Kirin 980 via ncnn) is the glasses-CPU fallback if YOLOX-Nano can't get an accelerator. Its last news entry is from 2023, so it is lightly maintained.
- **RTMDet / MMDetection (Apache-2.0):** the mmcv/mmengine stack is painful on Py 3.13/CPU. Skip it.
- **Ultralytics YOLO (AGPL-3.0): do not use in the repo.** AGPL requires open-sourcing the *entire* application, including the weights trained with it, even for SaaS/embedded/internal R&D use. A closed product needs a paid Enterprise license [Ultralytics]. That poisons the startup path. Keep the repo to Apache/MIT/BSD dependencies, tracked in `docs/LICENSES.md`.

### 1.2 Data and training plan
| Dataset | Content | License | Use |
|---|---|---|---|
| VisDrone2019-DET/VID/MOT | 6,471/548/1,610 img (DET) + video with track IDs; 10 classes | **CC BY-NC-SA 3.0** | research fine-tune + eval |
| Okutama-Action | 43 × ~1 min 4K/720p, 10–45 m AGL, 45°/90° pitch, person tracks; **2 drones film the same scenario simultaneously** | none stated (research, cite) | cross-drone dedupe test, person eval |
| UAVDT | ~80k frames 1080×540, car/truck/bus, 10–70+ m | research only | vehicle eval |
| Stanford Drone | campus nadir, 6 classes, 69 GB | CC BY-NC-SA 3.0 | optional |
| DOTA | satellite/aerial OBB | academic only, no commercial | **skip** (wrong viewpoint) |
| Sim frames (ours) | auto-labeled boxes | ours | train + eval, the commercial path |

Every real aerial set is **non-commercial/research-only**. Weights fine-tuned on them are fine for Phase 0 research and demos. Before any commercial pilot (Phase 1), retrain on synthetic + licensed/owned data. Flag this to Simon for the cost model. (Not legal advice.)

**Plan.**
- **Phase 0 bring-up (now, CPU):** COCO weights, mapped `person→person`, `car/bus/truck(/motorcycle)→vehicle`. The filtering pipeline and metrics must work with weak recall.
- **Semester 2, weeks 1–4:** fine-tune YOLOX-Tiny/Nano on VisDrone-DET with a 2-class head, at 640 and on sliced 416 tiles. SAHI-style slicing plus slice fine-tuning added +12.7 to +14.5 AP on VisDrone/xView in the SAHI paper [SAHI]. Run on Colab T4 / Penn cluster. Budget is UNVERIFIED: ~2–4 GPU-h per run.
- **Weeks 4–7:** add sim frames at a 1:1 mix, plus a `drone` class if counter-UAS stays in scope (COCO has none). Sim-only training reached 97.0 AP50 on MAV-Vid but only 49.8 on Drone-vs-Bird, so expect a gap [SynthDrone].
- **Here, pre-arrival:** run a CPU smoke fine-tune (YOLOX, ~100 images, 1 epoch) only to prove the training/export pipeline end to end.

### 1.3 Pipeline (companion, per feed)
`FrameSource → Scheduler → Detector(tiles) → Tracker → GeoProjector → EntityFusion → AlertRanker`

- **Scheduler.** Always process the *latest* frame and drop stale ones, so latency stays bounded and never queues. Default rate is 2 Hz per feed with 2×2 tiles (1 thread, ≈0.5 core per feed). The tasked/inset feed gets 4 Hz; feeds with no tracks for 30 s drop to 1 Hz.
- **Tracker: ByteTrack** (MIT). Use it via Roboflow `trackers` (Apache-2.0, Py≥3.10; also has OC-SORT/SORT). ByteTrack keeps low-confidence boxes for association, which matters for tiny aerial targets. OC-SORT handles camera motion better, so A/B them on VisDrone-MOT. Tracking at 2–4 Hz is feasible because tracks are confirmed in *image* space and then smoothed in *ground* space.
- **Confirmation (persistence):** track confirmed after ≥3 hits in a 5-detection window (≈1.5 s at 2 Hz), and mean conf ≥ τ_c. τ_c is swept per class (start: person 0.30, vehicle 0.35).
- **Geolocation (flat-earth ray cast).**
  - Pixel → normalized ray via intrinsics K. Rotate by the camera→body transform (gimbal) and body→NED (drone attitude).
  - Intersect with the plane z = ground elevation. Use the home altitude in Phase 0, or a DEM later.
  - Report `ce_m` from first-order error propagation. Range error ≈ h·δθ/sin²θ: at h = 60 m, 30° depression and 1° attitude error that is ≈4.2 m. Altitude error contributes Δh/tanθ.
  - Use the box bottom-center for persons/vehicles. Reject rays above −5° depression (horizon).
- **Entity fusion / cross-drone dedupe.** Gate on same class, Mahalanobis distance on (ce₁²+ce₂²), and |Δt| < 5 s. Fuse by inverse-variance weighting. One `Track` lists `source_assets[]`, which is why architect §1.3 schema has `source_assets[]`. Test it on the Okutama drone pairs.
- **Novelty:** an entity is "new" if no track of the same class sat within max(15 m, 2·ce) in the past 120 s. Operator `dismiss` adds a 10-min suppression disc (15 m radius); `track` pins it.
- **Ranking signals → `Alert.priority` (0–100):** class weight (vehicle > person, configurable by mission) × confirmed conf × novelty × proximity to operator/route (1/(1+r/300 m)) × in-AOI flag × motion (ground speed > 1 m/s ↑) × freshness decay. Add hysteresis so the top alert holds ≥4 s unless a new one beats it by >15 points. Only one banner is shown (HUD slide 15). Bearing/clock/range are computed relative to operator heading.

### 1.4 Goal-2 metric design
**Definition of what the operator must watch.** **Attended feed-seconds (AFS)** = Σ over feeds of seconds the feed is visible to the operator.
- Baseline condition (B0): all N feeds are shown in a grid for the whole mission, so AFS = N·T.
- E.D.I.T.H. condition (E): feeds are hidden. The inset appears only on alert or on voice request ("show drone 2"). The HUD logs every inset open/close event, so AFS is measured, not estimated.

**Primary metric:** **Watch reduction WR = 1 − AFS_E / AFS_B0**, reported *jointly* with event recall. A trivial "show nothing" scores WR = 100%. Target (proposed): **WR ≥ 80% at system event recall ≥ 90%, FA/h ≤ 6 per drone**, on sim scenarios at operating altitude.

**Secondary metrics:**
- **Event recall (system-level):** a GT event (entity of class c first becomes *detectable*, i.e. in-FOV, ≥12 px tall at detector input, unoccluded ≥1 s) is recalled if a matching alert (same class, ≤20 m, or ≤2·ce) fires within 10 s. Also report recall vs. target pixel height (8/12/16/24/32 px) so altitude effects are explicit.
- **Human-in-loop recall:** fraction of GT events the operator reports, B0 vs. E (user study).
- **False alerts per hour (FA/h)** per drone: alerts matching no GT entity. **Duplicate rate:** alerts per GT entity (dedupe quality).
- **Time-to-detection (TTD):** alert_ts − first_detectable_ts, median/p90. The budget is ≤3 s at 2 Hz.
- **Geolocation error:** CEP50/CEP90 in metres.
- **Operating curves:** sweep τ_c and persistence N to get recall vs. FA/h. Pick the operating point before the user study and freeze it.

**Protocol.**
- 10 scripted sim missions × 10 min × 2 drones, seeded. Long empty stretches are deliberate: realistic ISR is mostly nothing happening, and that is where WR comes from.
- Events per mission: 4–8 entities (persons on foot, moving/parked vehicles), including 1 cross-drone overlap and 2 distractors.
- The sim writes a **GT event log** (`entity_id, cls, world pos/vel per tick, per-camera 2D box + visibility + pixel height`).
- `bench/goal2` replays the missions headless, computes all metrics with bootstrap 95% CIs over missions, and is deterministic given the seed.
- The user study (Alisha's protocol) reuses the same missions, within-subject and counterbalanced B0/E, adding NASA-TLX.

### 1.5 Video sources for Phase 0
1. **Pose-registered replay (recommended for detection realism).** Play a real aerial clip as the drone's camera feed, with the PX4 SIH drone flying a matching straight/orbit track at the clip's nominal altitude/pitch. GT comes from the dataset's track annotations, projected through the *sim* pose. Geolocation is then internally consistent, not physically true. Detection/recall/FA numbers are realistic. Sources: VisDrone-MOT val (HF `Voxel51/visdrone-mot`, reachable here), Okutama sample (540 MB 4K + labels, Dropbox), UAVDT.
2. **Rendered sim camera** (sim expert's choice). Gives perfect GT and closed-loop behavior: voice → drone moves → feed changes. It has a domain gap, so measure COCO recall on it before trusting it.
3. **Demo realism footage:** DVIDS (US-government work, generally public domain). Do not imply DoD endorsement. Respect third-party content and insignia rules [DVIDS].

Never commit dataset media. `tools/fetch_data.py` downloads with SHA256 pins into gitignored `data/`, records the license per file, and keeps NC data out of any shipped artifact.

### 1.6 Edge-vs-offload benchmark
**Placements:**
- **P1 (default):** detector on companion, glasses render only.
- **P2:** detector on glasses AR1. The companion relays drone JPEG 320×240/640×360 to the glasses, which return Detections.
- **P3:** detector on an "offload server" (second laptop / Penn GPU box) over Wi-Fi. This is optional and never required.
- **P4:** glasses-camera detection on-glasses (see below).

**Glasses runtimes to try, in order (all UNVERIFIED on AR1/RayNeo AIOS):**
1. LiteRT + GPU delegate (fp16).
2. LiteRT + Qualcomm QNN delegate (int8 QDQ). Google's LiteRT NPU docs list only Snapdragon 8 Gen 1–8 Elite, **not AR1** [LiteRT-QNN].
3. ORT Mobile + XNNPACK (CPU).
4. ORT QNN EP (HTP needs fixed shapes + quantized model; the Android package must be built from source per the ORT docs) [ORT-QNN].
5. NNAPI. It is deprecated since Android 15 [NNAPI], but may be the only Hexagon path on an older AIOS build. Test it, but don't design around it.

**Measurements (one JSON schema for every placement):**
- Per-frame stage timestamps (`t_capture` set by FrameSource, decode, pre, infer, post, track, geo, fuse, alert_pub, hud_render). Clocks are aligned by a WS ping offset estimate (min-RTT/2).
- **E2E capture→alert latency** p50/p95, sustained fps, drop rate.
- Accuracy vs. the fp32 ORT reference (box-match F1 ≥ 0.95 is the parity gate) and vs. GT.
- Uplink/downlink bytes/s.
- **Glasses energy:** `BatteryManager.BATTERY_PROPERTY_CURRENT_NOW` × `EXTRA_VOLTAGE` at 1 Hz, minus an idle baseline (display on, model off), reported as mJ/inference and %battery/h; cross-check with `dumpsys batterystats`.
- **Thermal:** `PowerManager.getThermalHeadroom(0)` (API 30+, poll ≥10 s or it returns NaN) + `getCurrentThermalStatus()`, plus `/sys/class/thermal/thermal_zone*/temp` via adb if readable.
- **20-min soak** per config to expose throttling (fps vs. time).
- **Laptop:** CPU-seconds/frame via psutil. RAPL is likely unavailable in a VM.

**Harness:** `bench run --placement companion|glasses|offload --model X --clips set.yaml` writes JSONL + `summary.json`. Day 1 on the glasses uses LiteRT's prebuilt `benchmark_model` via `adb shell`. Week 2 adds a glasses-app `bench` activity that emits the same JSONL. Hypothesis: P1 wins on latency and battery for drone feeds, and P2 is viable only for Nano-class models at ≤2 Hz.

**Glasses camera role (P4):**
- (a) **"Mark that":** glasses frame + IMU heading/pitch + companion GPS → line-of-bearing marker. Optionally snap to the nearest detected person/vehicle box at the reticle, and intersect with the ground only when depression > 5° or a drone view confirms.
- (b) A live, real-world source for the on-glasses detection benchmark (point at a monitor replaying aerial clips for repeatability).
- Frames are not stored by default. No face processing.

### 1.7 CPU budget here (2 cores, no GPU)
PX4 SIH ×2 + companion + rendered sim camera compete for the same 2 cores. Software GL rendering is the hog, which is another reason to prefer replay.

| Config | Detector cost | 2 feeds @ |
|---|---|---|
| YOLOX-Tiny full-frame, 1 thr | 62 ms | 5 Hz each = 0.62 core |
| YOLOX-Tiny 2×2 tiles, 1 thr | ~250 ms | 2 Hz each = 1.0 core |
| YOLOX-Nano tiles, 1 thr | ~65 ms | 4 Hz each = 0.5 core |
| D-FINE-N 640, 2 thr | 100 ms | 2 Hz each = 0.4 s/s of both cores |

Default for Phase 0 is **YOLOX-Tiny, 2×2 tiles, 2 Hz/feed, 1 inference thread**. The inset video still streams at 10–15 fps, with Kalman-predicted boxes drawn between detections. Input frames are 1280×720 from the source, tiled to 416. Downscaling a whole 640×360 frame makes a person at 60 m only ~4–8 px tall.

---

## 2. Interfaces / needs from other experts
- **Sim / architect:**
  - FrameSource gives JPEG/raw frames plus per-frame `{frame_id, t_capture_ms (sim+wall), asset pose lat/lon/alt_msl/alt_agl, att, gimbal att, K (fx,fy,cx,cy), w,h}`. The pose must be the pose *at exposure*, not at publish.
  - A GT event log per scenario (schema in §1.4).
  - Replay clips registered to SIH trajectories.
  - If rendering, a bounding-box camera (Gazebo `boundingbox_camera`, UNVERIFIED for our sim choice) for auto-labels.
- **Schema additions (architect §1.3):**
  - `Detection.frame_id`, `Detection.tile`.
  - `Track.geo.ce_m` (present), `Track.hits/window`, `Track.novelty`.
  - `Alert.signals{conf,novelty,proximity,motion,aoi}` for explainability and logging.
  - `HudEvent{inset_open|inset_close, stream, ts}`: required for AFS.
  - `Feedback{track_id, verb: track|dismiss}`.
- **HUD (Alisha):** log inset visibility and alert display/ack times. Confirm the max banner hold and the hysteresis.
- **Voice (Om):** intents `show <asset>`, `hide feed`, `mark that`, `track`, `dismiss` mapped to Feedback.
- **Platform (Arjun):** glasses app needs Camera2 frames + IMU, LiteRT/ORT AARs, a `bench` activity, and adb access to `dumpsys`/thermal zones.
- **Defense SME:** realistic altitudes/standoff (this sets the pixel-size bins) and the class weights for ranking.
- **Systems (Simon):** license register, and the NC-data retraining cost line for Phase 1.

## 3. Buildable pre-arrival, and how to verify
1. **Model fetch, SHA256-pinned:**
   - `yolox_nano.onnx` (3.66 MB, sha256 `c789161ed43c8269…`), `yolox_tiny.onnx` (20.2 MB, `427cc366d34e27ff…`), `yolox_s.onnx` (35.9 MB, `c5c2d13e59ae883e…`) from YOLOX GitHub release `0.1.1rc0`.
   - `onnx-community/dfine_n_coco-ONNX/onnx/model.onnx` (15.3 MB, `0f684f409618ee8a…`).
   - `onnx-community/rtdetr_v2_r18vd-ONNX` (81 MB, `583a236ac21c95a7…`, reference/teacher).
   - Verify: hashes match, and the bench table above reproduces within ±25%.
2. **Detector adapters** (YOLOX letterbox + decode, DETR sigmoid/cxcywh) with the class map. Verify with a golden test: the regression eval on all 548 VisDrone-DET val images, with recall per class/size within ±0.02 of a stored baseline.
3. **TFLite conversion** of YOLOX-Nano/Tiny (fp32, fp16, int8 static with 200 calibration frames) via onnx2tf. Verify: parity F1 ≥ 0.95 vs. ORT using the LiteRT Python interpreter (`ai-edge-litert`; Py 3.13 wheel UNVERIFIED, fall back to a venv with 3.11/3.12). Pre-download LiteRT `benchmark_model` android_aarch64.
4. **Tracker + geolocation + fusion + ranker.** Verify:
   - Geo unit tests: exact pose gives round-trip pixel→ground→pixel error < 0.1 px; Monte Carlo ce_m calibration (≈50% of samples inside CEP50).
   - Tracker MOTA/IDF1 on 3 VisDrone-MOT val sequences using GT boxes + noise.
   - Dedupe on an Okutama drone pair, with duplicate rate < 1.2.
5. **Test clips:** VisDrone-MOT val (3–5 sequences from HF `Voxel51/visdrone-mot`), the Okutama `Sample.zip`, and 2 replay-registered 10-min scenarios with GT logs.
6. **`bench/goal2`** end to end on replayed missions, producing WR/recall/FA/h/TTD/CEP plus CIs. Verify it is deterministic across two runs.
7. **CPU smoke fine-tune** (YOLOX-Tiny, 100 images, 1 epoch) → export → parity test. This proves the pipeline, not accuracy.

**Day-1 on glasses:** `adb push` the `.tflite` files and `benchmark_model`. Run CPU 1/2/4 threads, `--use_gpu`, `--use_nnapi`, and the QNN delegate if libs load. Record `getprop ro.board.platform`, the thermal zones, and BatteryManager current readability.

## 4. Risks and mitigations
| Risk | Mitigation |
|---|---|
| COCO weights miss small aerial targets (measured) | Tiling now; VisDrone fine-tune sem-2 wk 1–4; sim targets ≥12 px; recall by pixel size |
| No accelerator reachable on AR1/AIOS | Nano@320 on CPU ≤2 Hz; "offload to companion" is itself a valid result |
| NC-licensed data blocks commercialization | Provenance tracking; synthetic/owned-data retrain before Phase 1 |
| Sim rendering eats the 2 cores | Replay-first; detect at 2 Hz; slow sim speed factor for bench runs |
| WR gamed by never alerting | WR always paired with recall + FA/h; frozen operating point |
| Geolocation error (attitude/terrain) | ce_m propagation; ce-scaled gates; DEM in sem-2 |
| Glasses thermal throttling | 20-min soak; rate adapts to thermal headroom |
| Scope creep (identity/targeting) | No face/ID classes; detections `unknown`; no targeting path |

## 5. Open questions
1. Operating altitude/HFOV and drone camera resolution in sim (sets everything in §1.7)? I propose 40–60 m AGL, 70° HFOV, 1280×720.
2. Is `drone` in scope for semester 2 (counter-UAS display only)? It needs its own data.
3. Sim camera: replay-only, or also rendered (Gazebo vs. synthetic compositor)?
4. Does RayNeo AIOS expose a GPU delegate / QNN HTP to sideloaded apps? This needs day-1 data.
5. Penn GPU access (cluster name/quota) for sem-2 fine-tuning? Otherwise Colab.
6. User-study B0: grid of all feeds on a laptop screen, or cycled in the HUD inset?

## Sources
- [YOLOX](https://github.com/Megvii-BaseDetection/YOLOX) · [D-FINE](https://github.com/Peterande/D-FINE) · [LiteRT D-FINE-S](https://huggingface.co/litert-community/D-FINE-S-LiteRT) · [onnx-community D-FINE-N](https://huggingface.co/onnx-community/dfine_n_coco-ONNX) · [RF-DETR N/S/M](https://roboflow.com/blog/rf-detr-nano-small-medium) · [NanoDet](https://github.com/RangiLyu/nanodet) · [Ultralytics license](https://www.ultralytics.com/license)
- [VisDrone HF card](https://Huggingface.co/datasets/Voxel51/VisDrone2019-DET) · [VisDrone GitHub](https://github.com/VisDrone/VisDrone-Dataset) · [Okutama-Action](http://okutama-action.org) / [paper](https://arxiv.org/pdf/1706.03038) · [UAVDT](https://datasetninja.com/uavdt) · [Stanford Drone](https://cvgl.stanford.edu/projects/uav_data/) · [DOTA](https://captain-whu.github.io/DOTA/dataset) · [DVIDS copyright](https://dvidshub.net/about/copyright)
- [SAHI](https://arxiv.org/abs/2202.06934v2) · [Synthetic drone detection](https://arxiv.org/pdf/2411.09077) · [ByteTrack](https://github.com/foundationvision/bytetrack) · [Roboflow trackers](https://pypi.org/project/trackers/2.2.0/)
- [LiteRT Qualcomm NPU](https://developers.google.com/edge/litert/android/npu/qualcomm) · [ORT QNN EP](https://onnxruntime.ai/docs/execution-providers/QNN-ExecutionProvider.html) · [NNAPI deprecation](https://developer.android.com/ndk/guides/neuralnetworks/migration-guide) · [Android Thermal API](https://developer.android.com/games/optimize/adpf/thermal) · [Snapdragon AR1](https://www.trustedreviews.com/explainer/what-is-the-snapdragon-ar1-gen-1-4373840)
