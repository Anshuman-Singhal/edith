# WS-E walkthrough: ML & perception (D8)

1. Fetch models (hash-pinned, gitignored `models/`):
   `./edith fetch models` (or `--from <dir of pre-downloaded .onnx>`).
2. Timing (quiet machine): `./edith bench placement` → YOLOX-Tiny@416 1-thread p50 (target
   62 ms ±25%) and 2×2 tiled frame p95 (≤350 ms). Same check as a test:
   `uv run pytest -m slow companion/tests/perception/test_perception_latency_slow.py -s`.
3. Unit suite (≈20 s, no `data/`):
   `uv run pytest companion/tests/perception sim/tests/gt_detector -m "not slow" -s`.
   Prints the Monte-Carlo CE90 coverage, confirm latencies, IDF1, duplicate rate and motion
   estimator stats (ORB vs ECC).

## Pipeline (companion/edith_companion/perception)
`frame_source` (RTP+SEI, PyAV decode) / `offload` (UDP 5800+i) → `scheduler` → `detector`
(YOLOX-Tiny 416², 2×2 tiles, IOS merge) → `geo` (pixel→ground, Jacobian CE90) → `tracker`
(ENU Kalman; image-plane for pseudo with `motion` ORB/ECC homography) → `fusion` → `novelty`
→ `friendly` → `pipeline` (Track dicts, `alert_eligible`, `cot_eligible`) and `inset` (JPEG
320×240, night green). `sim/edith_sim/gt_detector.py` is the sim-side GT detector.

## Pinned choices (D8)
- Friendly PLI ages: dead-reckoning and radius growth use the true PLI age capped at 30 s
  (ml nb1; L26 conservative); the <30 s freshness check (first association only) measures age
  from the moment `status.tak` went `lost` (C98, defense r4 nit 1).
- CE90 is the exact 90% radius of the propagated 2×2 covariance (pitch, horizon-roll, yaw,
  height, pixel+box term); it reduces to PLAN's circular formula when isotropic.
- Gating: Mahalanobis d² < 9.21 plus an absolute cap (40 m ground / 250 px image; fusion 25 m)
  so long-coasting tracks cannot swallow unrelated detections; the low-confidence second pass
  only extends tracks hit in the last 1.5 s.
- Pseudo tracks skip friendly association and metric novelty (ml nb3); their geo is display-only.
