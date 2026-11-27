# WS-D walkthrough (Sim) — D2

What exists after D2 and how to use it. Spec: [sim.md](../spec/sim.md).

## Pieces

| Path | What |
|---|---|
| `sim/profiles/quad_sim.yaml` | The one vehicle profile (sim §1). `edith_sim.profile.load_profile(name, overrides)` |
| `common/edith_common/px4/` | `modes` (custom_mode encoding, AUTO.LOITER, POSCTL.ORBIT, …), `encode` (COMMAND_INT builders, mission/fence items, byte-wise int32 params, `completed` helpers), `failsafe.DllFailsafe` (delayed hold), `classify` (MOTION/SAFE/CONFIG table for `outbound.py` and the wire log), `search.plan_search` |
| `sim/edith_sim/mock/` | `MockVehicle` (steppable, deterministic), `InProcLink` (in-process GCS over bytes), `udp.UdpMock` (ScaledClock UDP process) |
| `sim/edith_sim/linkshaper/` | `Shaper` (windows + wire log), `relay.Relay` (UDP wiring of sim §3) |
| `sim/edith_sim/scenario/` | `model` (pydantic YAML v2), `prerun` (deterministic pre-run), `lint` (bound table + rules 1–4) |
| `sim/edith_sim/mover.py`, `gt.py` | Seeded mover; analytic FOV, `GtLogger`, `FovTracker` |
| `sim/edith_sim/runner/` | `ScenarioRunner`, `GlassesPort` / `LinkControl` protocols, `AlertJoin` |
| `scenarios/` | `demo_vignette`, `demo_scout`, `demo_jam`, `demo_live`; `tests/infeasible_vignette.yaml` |

## Commands

```bash
./edith scenario lint scenarios/*.yaml            # 0; prints every expect's LB
./edith scenario lint --beats scenarios/demo_live.yaml
./edith scenario lint scenarios/tests/infeasible_vignette.yaml   # 1, names expect[2]
./edith sim mock --instance 0                     # Mock on UDP 14580 → 14540 (EDITH_PORT_BASE, EDITH_SPEED)
./edith sim linkshaper --asset drone1=0 --asset drone2=1 --wire-log runs/x/mavlink_wire.jsonl
./edith sim record-px4                            # explains the PX4 approval gate (exit 3)
uv run pytest sim common/tests/px4 tools/tests/d -q
```

## Driving the Mock in a test

```python
v = MockVehicle(load_profile(), instance=0, seed=1); L = InProcLink(v)
L.heartbeat(0); L.command(E.arm(L.mav, 1), 0); L.command(E.takeoff(L.mav, 1, 270), 0)
v.advance(30)        # sim seconds, dt 20 ms; v.trace / v.trace_sha256() for determinism
```

## Notes for other workstreams

- WS-B: `edith_common.px4.classify.classify(msg)` is the interfaces §6 table; `encode.*` builds
  every adapter message; the runner needs `fake_glasses` to satisfy `edith_sim.runner.GlassesPort`
  (`say`, `touch`, `on_card_shown(cb(proposal_id))`, `on_alert_shown(cb(alert_id))`) and the
  supervisor to call `runner.tick(sim_s)` and `runner.on_gt(...)`. `AlertJoin` reads eventlog lines
  `{type|kind, body{alert_id, track_id | track_id, det_ids}}` and ignores a partial last line.
- Scenario YAML uses `on:` keys: load it with `edith_sim.scenario.model.load_yaml` (YAML 1.1 would
  turn `on` into `True`).
- PX4 (D15) is approval-gated: `tools/install_px4.sh` refuses without `EDITH_PX4_APPROVED=yes`
  and a pinned sha256.
