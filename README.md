# E.D.I.T.H.

**The intelligence hub for the battlefield operator.** Lightweight AR glasses (RayNeo X3 Pro)
that bring comms, maps, drones and AI analysis into one voice-driven heads-up display. Penn M&T
senior design (Team 76), Phase 0: everything runs in simulation.

Scope is awareness, ISR tasking, navigation and alerting. No weapons employment, targeting,
fire control or autonomous engagement; no facial recognition or biometric identification. Every
asset command needs an explicit human confirmation (safety stop excepted).

## Layout

| Path | What |
|---|---|
| `glasses/` | Kotlin: thin glasses app (render + input + capture), HUD core, desktop emulator, self-test APK |
| `companion/` | Python companion: voice → intent → safety gate → assets; perception; alerts; TAK |
| `sim/`, `scenarios/` | MockVehicle / PX4 SIH, synthetic camera, scenarios |
| `ml/`, `bench/` | Detection models, evaluation for the year goals |
| `common/`, `schemas/` | Shared wire contracts, geo, clock |
| `tools/` | `./edith` CLI, supervisor, fakes, fetch scripts |
| `docs/` | [PLAN.md](docs/PLAN.md) (start here), specs, council record, bring-up |

## Quick start

```bash
uv sync --all-extras
./edith doctor
./edith test lint && ./edith test unit
./edith up --headless --scenario scenarios/demo_vignette.yaml --assets mock --detector gt --speed 4
```

Glasses day one: [docs/bringup/INSTALL.md](docs/bringup/INSTALL.md) and
[docs/bringup/CHECKLIST.md](docs/bringup/CHECKLIST.md).

Ownership: [docs/OWNERS.yaml](docs/OWNERS.yaml). Binaries, models, datasets and the RayNeo SDK
are never committed; `./edith fetch ...` downloads them with pinned hashes.
