# WS-D requests and replies

## 2026-11-26 · WS-D → WS-B · FakeGlasses / supervisor seams (D2)
- what: `tools/edith_tools/fake_glasses.py` should satisfy `edith_sim.runner.GlassesPort`
  (`say(text)`, `touch(kind, duration_ms=None)`, `on_card_shown(cb)` with the proposal id,
  `on_alert_shown(cb)` with the alert id). The supervisor calls `ScenarioRunner.tick(sim_s)`,
  forwards GT events with `runner.on_gt("asset_mode", asset=, mode=)` /
  `on_gt("entity_in_fov", asset=, entity=, dwell_s=)`, and implements `LinkControl.jam(t_s,
  duration_s, links)` by `Shaper.add(*jam_windows(...))`.
- eventlog: `AlertJoin` expects JSONL records with `type` (or `kind`) and `body` holding
  `alert.created{alert_id, track_id}` and `track.update{track_id, det_ids}`. Tell WS-D if the
  eventlog shape differs.
- `outbound.py` can import `edith_common.px4.classify.classify` (interfaces §6 table).
- blocking: nothing in D2 (tests use a stub).

## 2026-11-26 · WS-D → lead · PX4 .deb sha256
- `tools/install_px4.sh` has `PX4_DEB_SHA256` empty: the v1.18.0-rc2 release asset digest could
  not be fetched from the sandbox (GitHub API not enabled for this session). Pin it before D15.
