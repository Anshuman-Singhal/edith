VERDICT: CHANGES REQUIRED

Edge ML / CV review. Checked here: the official `yolox_tiny.onnx` input is static `[1,3,416,416]`, and libx264 ultrafast at 720p takes about 2.8 ms per frame on 1 thread (testsrc2, a lower bound).

**1. BLOCKER: §3.5 Tracker, C17, D6, D8. Image-space IoU tracking fails at 2 Hz.**
At 0.5 s between detections, a lawnmower search at 8 m/s and 60 m AGL (about 0.075 m/px) shifts the ground by about 50 px. A stationary 8×20 px person then has IoU 0 with itself in the next detection, and a vehicle at 10 m/s shifts about 67 px. ByteTrack has no camera-motion compensation, so tracks never reach 3 hits in 5. `gt_detector` output goes through the same tracker, so D6's "vehicle alert by t=90 during SEARCH" fails even with perfect detections.
Fix: "Tracker: in-repo **ground-plane** tracker. Geo-project each Detection, then run a constant-velocity Kalman filter in ENU metres. Associate by Mahalanobis distance (σ from `ce_m`), same class, d² < 9.21. Use ByteTrack-style low-confidence second-pass association. Draw inset boxes by reprojecting tracks through the current FrameMeta. IoU is used only for the cross-tile merge." C17 is superseded, and `trackers` becomes an offline A/B. Add a D8 test: during a lawnmower pass at 8 m/s, a stationary target and a 10 m/s target are each confirmed within 2.5 s, and IDF1 ≥0.8.

**2. MAJOR: §6.2, D9. The G2 missions cannot be built from the named data, and AFS is undefined when headless.**
VisDrone-MOT clips are short, dense urban scenes, so "10 min, 4–8 entities, long empty stretches" cannot be made from them. In `bench goal2` nobody closes the inset, and a CAUTION alert expires at 120 s, which makes WR arbitrary.
Fix (replace the Protocol bullet): "Missions are **composed timelines**: real annotated segments (≤60 s each, selected by script for ≤8 GT tracks, from VisDrone-MOT val/test-dev, Okutama and the UAVDT test split) spliced between empty stretches. Overlap between the two drones' views uses Okutama pairs only. The held-out split is frozen in `ml/splits.yaml` before any fine-tune. **FA/h counts real-footage seconds only** and is reported with an exact Poisson 95% CI. The operator model opens the inset on `alert_shown` and closes it after R = 6 s (3 s and 10 s also reported) or on clear. A collapsed alert recalls every GT entity inside its extent." Add AFS per true event as a secondary metric.

**3. MAJOR: §2.4 FrameMeta, §3.5 Geolocation, D8. CEP90 is met trivially, and `ce_m` is inconsistent.**
The sidecar carries the same pose the frame was rendered with, so geolocation error is about 0. Replay GT is projected through the sim pose, so replay geolocation is circular. `ce_m` is tested as CEP50 but targeted as CEP90. The propagation formula has no yaw term, and 3° of yaw at a 120 m slant gives 6.3 m of error.
Fix: "The sidecar carries `pose_est` = true pose + `nav_noise` {σ_rp 1°, σ_yaw 3°, σ_alt 1.5 m, skew U(0, 50 ms)}. `ce_m` is the **CE90** radius: σ_r = (h/sin²θ)·σ_θ ⊕ σ_h/tanθ ⊕ box term; σ_x = R_slant·σ_ψ; ce_m ≈ 2.146·√((σ_r²+σ_x²)/2). Fusion and the tracker use σ = ce_m/2.146. The D8 Monte Carlo test requires 90% ±3% of samples inside `ce_m`. **CEP90 is measured only on synthetic missions with `nav_noise`.** h comes from `GLOBAL_POSITION_INT.relative_alt`."

**4. MAJOR: §3.5 Companion default, §6.2 Event. Persons fall below the detection threshold.**
A 2×2 grid with 15% overlap on 1280×720 gives 692×389 tiles. Letterboxing them into 416² scales by 0.60 and wastes 44% of the input. At the default geometry (60 m AGL, −60° pitch, 70° HFOV) a person is about 11 px tall in the source frame and about 7 px at detector input, and the "≥12 px" rule does not say which of the two it means.
Fix: "Detectable means ≥12 px **at detector input**, and the tile scale is logged." Export YOLOX-Tiny/Nano at **576×320** from the Apache PyTorch weights in the D14 venv. That is 1.07× the pixels of 416², the cost is UNVERIFIED, and it raises the scale to 0.82. The 416² letterbox stays as the fallback. Fly person missions at 45–50 m AGL with a −45° pitch, which puts a person at about 12.7 px at detector input.

**5. MAJOR: §6.3. P2 mixes placement with resolution, and the energy readings will be wrong.**
P2 sends 320×240 or 640×360 frames, while P1 runs on 720p tiles, so the comparison measures resolution rather than placement. With USB adb connected, `CURRENT_NOW` includes the charge current.
Fix: "P2 relays the **same detector input** as P1 (tiles, JPEG q90, at the detector rate, about 2–3 Mbit/s) and also reports its best feasible configuration separately. Energy runs use adb over Wi-Fi with USB unplugged. The idle baseline receives the same JPEG stream without running inference. T18 records the sign, units and update period of `CURRENT_NOW`."

**6. MAJOR: §5 D6, C32, D8. The CPU budget does not hold at `--speed 4`.**
If the cameras run on sim time, 4× speed means 2 × 60 fps of 720p render, encode and decode. That is about 1.7 cores with realistic content, before the companion runs. D8's p95 ≤350 ms does not say under what load it is measured.
Fix: "With `--detector gt`, the RTP cameras are off. `gt_detector` reads FrameMeta and GT, and the inset uses a 320×240 render capped at 5 fps wall-clock. Camera fps is always capped on the wall clock. D8 timing is measured in isolation with 1 ORT thread. One full-stack run (1 feed, real detector, `--speed 1`) is reported without a gate."

**7. MINOR: §3.5 Thresholds.**
The detector floor of 0.25 contradicts the tracker's 0.10 low-confidence association. Set the output floor to 0.10 and start tracks only at ≥0.25. Merge across tiles with intersection-over-smaller (IOS) ≥0.5, as SAHI does, instead of IoU.

**8. MINOR: §3.5 Licenses, §4.2.**
Weights fine-tuned on VisDrone inherit its NC-SA terms. Add `license` and `derived_from` fields to `models.yaml`, and a lint that fails if an NC-derived artifact is packaged into an APK or wheel. Whether the PyAV wheel's bundled FFmpeg includes GPL components is UNVERIFIED. Record `av.library_meta` in `LICENSES.md` and keep encoding in `sim/`.

**9. MINOR: D8, D9, D14.**
Random per-frame false positives never pass 3-of-5 confirmation, so add persistent clutter objects to `gt_detector`. The D8 tracker and fusion tests should use synthetic GT so they pass without NC data. The D14 venv should be created with `uv venv -p 3.12` (TF, onnx2tf, ai-edge-litert).
