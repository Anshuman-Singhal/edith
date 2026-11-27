# WS-E requests

## 2026-11-27 · WS-E → WS-A · `fetch --from` for Hugging Face artifacts
- what: in `tools/edith_tools/fetch`, when `--from <dir>` is given, also look for
  `<dir>/<local_name>` (new optional lockfile key) and `<dir>/<basename(dest)>`, not only
  `basename(url)`. `ml/models.yaml` already carries `local_name` on the three HF rows.
- why: the HF URLs end in `model.onnx` / `model_int8.onnx`, so `--from` cannot match the
  pre-downloaded `dfine_n.onnx` etc. and falls back to the network (works here; hashes match).
- blocking: no.

## 2026-11-27 · WS-E → WS-A · FrameMeta `geo_quality` (optional)
- what: optional `FrameMeta.geo_quality: metric|pseudo` so replay feeds self-describe.
- why: today the companion takes it from config (`FeedConfig.geo_quality`).
- blocking: no.

## 2026-11-27 · WS-E → WS-D (D7 simd) · SEI and sidecar format the FrameSource expects
- SEI: `user_data_unregistered` (payloadType 5) NAL before every access unit; payload =
  16-byte UUID `b"EDITH-FRAMEID-v1"` + frame_id as uint64 big-endian (ASCII digits accepted).
  `edith_companion.perception.frame_source.build_sei_nal(frame_id)` builds it (incl.
  emulation prevention); import or copy it.
- RTP: RFC 6184 (single NAL / STAP-A / FU-A), 90 kHz clock, `rtp_ts = ts0 + frame_id·90000/fps`
  (pts-anchor fallback), marker bit on the last packet of each AU, `repeat-headers=1` so a
  mid-stream join decodes at the next IDR.
- Sidecar: one JSON `FrameMeta` per datagram on 5700+i. Gimbal convention as in
  `perception/geo.py` (stabilized: camera yaw = body yaw + gimbal yaw, pitch vs horizon).
- gt_detector wiring: `GtDetector(GtConfig.from_scenario(sc["gt_detector"]), asset_id,
  instance=i, seed=sc["seed"], origin=..., log_path=runs/<ts>/gt_dets_<i>.jsonl,
  send_host="127.0.0.1")`, then `on_frame(frame_truth, true_frame_meta, now_ms)` per virtual
  frame and `pump(now_ms)` from the loop. Clutter items: `{id, e, n, conf, cls?, h_m?}`.
- blocking: D6 needs this wiring in the runner/simd.

## 2026-11-27 · WS-E → WS-B (D3a/D6) · companion wiring
- `Perception(origin, companion_id)`; per feed `add_feed(FeedConfig(asset_id, geo_quality,
  instance))`; `OffloadDetector(instance)` + a sidecar socket (`FrameSource(..., bind=True)`
  handles 5600+i/5700+i); gate each frame with `perception.scheduler.due(asset, t_ms)` then
  `perception.process(asset, meta, dets[, frame])` → updated Track dicts (`to_wire()` for the
  schema form). Feed `on_teammate(TeammatePosition)`, `on_tak_status(state, t_ms)`,
  `on_ptt(down)`. Use `alert_eligible()` / `cot_eligible()` as the perception-side gates.
- blocking: D6.
