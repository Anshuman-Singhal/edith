# R1: Robotics & Simulation (asset layer for Phase 0)

Author: Robotics & Simulation expert. Status: round 1. Probes were run in this workspace on 2026-11-23. Each one is marked **[probed]**. Anything not tested here is marked **UNVERIFIED**.

## 1. Recommendations

### 1.1 Decision: three tiers behind one interface

| Tier | Autopilot | Camera | Runs where | Use |
|---|---|---|---|---|
| **0 MockVehicle** | Pure-Python kinematic vehicle that speaks MAVLink (pymavlink) | Same synthetic camera as Tier A | Anywhere, CI, 10× real time | Unit, contract and CI e2e tests. Never blocked. |
| **A (default)** | **PX4 v1.18 SIH**: the real PX4 flight stack, headless, no Gazebo | **Synthetic camera**: real NAIP orthophoto projected through the drone's pose, with sprites and ground-truth boxes | This workspace, every laptop (Linux native; Docker on macOS and Windows) | Development, e2e, user studies, goal-2 metrics, likely the final demo |
| **B (showcase)** | PX4 + **Gazebo Harmonic**, `x500_mono_cam_down` | Rendered gz camera, RTP H.264 on UDP 5600+i | Ubuntu 24.04 laptop with an NVIDIA GPU | 3D visuals, physics-rendered video |

Tier A is the default because it is real PX4, with real modes, failsafes and the mission protocol, for about 6 MB of binary and no rendering. Its imagery is also *more* realistic than a Gazebo world, because it comes from real aerial photos. Tier B is optional polish. The companion cannot tell the tiers apart: every tier exposes MAVLink on 14540+i and video on 5600+i.

**Rejected:**
- **jMAVSim**: Java, has no camera, and is legacy. Its only use is as a 3D viewer for SIH (port 19410+i).
- **ArduPilot SITL**: kept only as an emergency fallback. A prebuilt `arducopter` SITL binary (stable, built Nov 14 2026) is published on firmware.ardupilot.org **[probed]**. However, ArduPilot does not implement `MAV_CMD_DO_ORBIT`, and its mode semantics differ from PX4's, so supporting both would double the adapter work.
- **Native Gazebo on macOS**: sensor rendering crashes under Metal (gz-sim #2877).

### 1.2 PX4 install: no source build needed

PX4 now ships **prebuilt SITL `.deb` packages and containers**. `px4` (SIH, about 10 MB) and `px4-gazebo` are built for noble and jammy on amd64 and arm64. The images are `px4io/px4-sitl` (45 MB compressed) and `px4io/px4-sitl-gazebo` (683 MB). Facts checked here:

- The packaging workflow `build_deb_package.yml` exists at tag `v1.18.0-rc2` (2026-11-17) and does **not** exist at `v1.17.0` **[probed]**. The packages are therefore new as of v1.18, which is still a release candidate.
- I pulled the `px4io/px4-sitl:v1.18.0-rc2-amd64` layers from Docker Hub with curl (no daemon needed) and found `px4_1.18.0~rc2-noble_amd64.deb` (12 MB) inside. `/opt/px4` is 5.7 MB and contains the `10040_sihsim_quadx`, `10044_sihsim_hex`, `10041_sihsim_airplane` and `10043_sihsim_standard_vtol` airframes **[probed]**.
- Port logic read from the packaged `px4-rc.mavlink` and `rcS` **[probed]**. For instance *i*:
  - API link: PX4 binds 14580+i and sends to **14540+i**.
  - GCS link: 18570+i, sent to 14550.
  - SIH viewer: 19410+i.
  - `MAV_SYS_ID = i+1`.
  - `PX4_HOME_LAT/LON/ALT` set the SIH origin.
  - `PX4_SIM_SPEED_FACTOR` scales time, and rcS scales `COM_DL_LOSS_T` with it.
- **Not executed:** the workspace permission policy blocked running the extracted PX4 binary. Installing `gz-harmonic` via apt was also blocked. Running either here needs the user's approval (see §5).

Run commands (Tier A, two drones). Separate working directories keep the parameter files apart, and different homes stop the two vehicles spawning on top of each other:
```
sudo apt install ./px4_1.18.0~rc2-noble_amd64.deb      # <1 min, no build
PX4_SIM_MODEL=sihsim_quadx PX4_HOME_LAT=40.0700 PX4_HOME_LON=-88.6300 PX4_HOME_ALT=210 px4 -i 0 -d
PX4_SIM_MODEL=sihsim_quadx PX4_HOME_LAT=40.0702 PX4_HOME_LON=-88.6300 PX4_HOME_ALT=210 px4 -i 1 -d
```
- **macOS (Apple silicon) and Windows:** `docker run -p 14540:14540/udp ... px4io/px4-sitl` (arm64 and amd64 tags exist **[probed]**). Run the Python synthetic camera natively.
- **Fallback if the packages misbehave:** build from source with `make px4_sitl_sih` on a laptop. On these 2 cores that would take an estimated 30–45 min plus about 10 min of toolchain setup (UNVERIFIED), so it is not done here.

**Tier B install (Ubuntu 24.04 laptop):**
- Add the OSRF repo and run `apt install gz-harmonic`. A simulated install resolved **355 packages, 160 MB download [probed]**, estimated 5–10 min. Then run `apt install ./px4-gazebo_*.deb`.
- Run with `HEADLESS=1 PX4_SIM_MODEL=gz_x500_mono_cam_down px4 -i 0`. Additional vehicles add `PX4_GZ_STANDALONE=1 PX4_GZ_MODEL_POSE="0,5"`.
- Video is RTP H.264 on UDP 5600+i by default.
- If OGRE2 misbehaves, set `PX4_GZ_SIM_RENDER_ENGINE=ogre`.
- **WSL2/WSLg** is not officially tested. Black renders have been reported on the D3D12 path, so treat it as best effort.
- **On this workspace (llvmpipe):** EGL `--headless-rendering` falls back to software rendering. My estimate is 1–5 fps per 640×480 camera. Because PX4 and gz run in lockstep, slow rendering also slows the real-time factor. This is UNVERIFIED and needs a 10-minute probe if apt is approved. It is not a demo path either way.

### 1.3 Control library: pymavlink behind `AssetAdapter`

**Correction to architect.md §1.2:** MAVSDK-Python **4.x is a rewrite.**
- Since 4.0.0 (2026-09-22) the `mavsdk` package is a ctypes binding to `libcmavsdk.so`. It has no `mavsdk_server` and a different API (`mavsdk.asyncio.Mavsdk`, `add_any_connection("udp://:14540")`, `first_autopilot()`).
- The old gRPC API moved to `mavsdk-grpc`. Nine releases shipped in 8 weeks **[probed: installed 4.2.1 and read its `_legacy.py`]**.
- Most tutorials, and LLM recall, target 3.x.

**Recommendation:** implement the PX4 adapter with **pymavlink 2.4.50**. It is stable and has wheels for cp39–cp314 on Linux, macOS and Windows **[probed]**. MockVehicle uses the same message code, so one codec serves both sides. MAVSDK 4.x `mavsdk.asyncio`, pinned to `==4.2.1`, remains an allowed alternative behind the same interface if the team prefers its mission plugin.

Primitive → MAVLink (PX4):

| Verb | Message |
|---|---|
| arm | `COMMAND_LONG` 400 `COMPONENT_ARM_DISARM` p1=1 |
| takeoff | 22 `NAV_TAKEOFF` (p7 = AMSL) |
| goto | `COMMAND_INT` 192 `DO_REPOSITION` (p2 = 1 change-mode, x/y = lat/lon·1e7, z AMSL). The vehicle ends in Hold at the point. |
| orbit / observe(point) | `COMMAND_INT` 34 `DO_ORBIT` (radius, velocity, yaw-to-center, center, alt) |
| search(area) | Companion builds a lawnmower path from the polygon. Track spacing = footprint width × (1 − 0.3 overlap). Upload with `MISSION_COUNT` / `MISSION_ITEM_INT` (16 `NAV_WAYPOINT`), then 300 `MISSION_START`. |
| observe/follow(track) | Re-issue `DO_ORBIT` / `DO_REPOSITION` at ≤1 Hz on the track estimate, at a standoff of at least X. Do **not** use PX4 Follow-Me, which is meant for following the operator. |
| hold | 176 `DO_SET_MODE`, custom main 4 / sub 3 (AUTO.LOITER) |
| rtl / land | 20 `NAV_RETURN_TO_LAUNCH` / 21 `NAV_LAND` |
| speed | 178 `DO_CHANGE_SPEED` |
| geofence | `MISSION_TYPE_FENCE` polygon upload. The companion also checks the fence itself (defense in depth). |

Telemetry used:
- `HEARTBEAT`: mode and armed state, plus link liveness. Link is degraded after 1.5 s of silence and lost after `COM_DL_LOSS_T`.
- `GLOBAL_POSITION_INT`, `ATTITUDE`, `BATTERY_STATUS`/`SYS_STATUS`, `EXTENDED_SYS_STATE` (landed state), `MISSION_CURRENT`, `STATUSTEXT`.
- `COMMAND_ACK` drives `Execution.status`.
- The companion sends `HEARTBEAT` as `MAV_TYPE_GCS` at 1 Hz. **This matters:** PX4's data-link-loss failsafe watches GCS heartbeats.

### 1.4 Synthetic camera (Tier 0/A)

- **Input:** the true vehicle pose (lat, lon, AGL, attitude), tapped at the link proxy *before* any impairment, plus gimbal pitch (default −60° oblique, −90° nadir available).
- **Model:** a pinhole camera, 1280×720, HFOV 70°. The orthophoto is warped onto the image with a ground-plane homography `H = K[r1 r2 t]`. This is a flat-earth model, so the site is chosen to be flat. Pixels beyond the horizon or outside the tile get a haze gradient.
- **Entities:** RGBA sprites at true metric size (person 0.5 m footprint / 1.7 m standing billboard, car 4.5×1.8 m, truck), oriented by heading, with a drop shadow, then blur, sensor noise and encode artifacts. Randomness is seeded.
- **Ground truth per frame:** `{frame_id, t_sim, asset_id, cam_pose, objects:[{entity_id, cls, bbox_xyxy, visible_frac, range_m, lat, lon}]}`. Boxes are exact because the projection is known.
- **Cost:**
  - Rendering, warp plus 10 sprites **[probed, OpenCV 5.1 headless]**:
    - 1280×720: 4.0 ms/frame (6.7 ms on a single thread)
    - 640×480: 1.6 ms/frame
  - Encoding **[probed, ffmpeg 6.1]**: libx264 `ultrafast -tune zerolatency -g 30`, 720p30, takes **~0.13 core per stream**.

  Two drones at 720p30 therefore cost about 0.5 core in total, which fits on 2 CPUs alongside two SIH instances.
- **Output:**
  - Video: RTP H.264 to `udp://127.0.0.1:5600+i`, matching Tier B's convention so companion ingest is identical. The SDP file is generated per stream and read with PyAV, or with GStreamer `udpsrc ! rtph264depay`.
  - Sidecar: JSON on UDP **5700+i** with `{frame_id, pts, cam_pose}`. This is the Phase-0 stand-in for MISB ST 0601 KLV. It lets the GeoProjector turn boxes into lat/lon without guessing timing.
- **`replay` mode** (architect.md §1.4): the same interface plays real annotated aerial clips with their ground-truth boxes. Sprites will not convince a COCO/VisDrone-trained detector, so **goal-2 accuracy numbers must come from replay or real imagery**. The ortho mode supplies geometry, geolocation and alert-flow numbers.
- **`gt_detector` bypass:** emits Detections straight from ground truth, with configurable Pd, false-alarm rate, latency and position noise. The whole pipeline can then run with no ML at all.

### 1.5 Jamming and link impairment

`linkshaper` is an in-repo asyncio UDP proxy. It is the same component as architect.md's impairment proxy.
- It sits between PX4 (14540+i) and the companion (14740+i) for MAVLink.
- It is scriptable for drop, latency and partition windows. In a jam window it drops both directions.
- It also taps the true pose for the simulator, and that tap is never impaired.
- The same tool impairs the companion's CoT/TAK sockets.

Autopilot behavior during a jam is set by PX4 parameters per scenario:
- `NAV_DLL_ACT`: Disabled, Hold, Return, Land, Disarm or Terminate.
- `COM_DL_LOSS_T`.
- `COM_DLL_EXCEPT`: a bitmask that exempts modes (e.g., Mission) from the failsafe. Exact bit values are UNVERIFIED.

Caveat: QGroundControl must also be routed through the shaper, or must not be running. Otherwise its GCS heartbeats on 14550 keep the link "alive" and the failsafe never fires.

### 1.6 Scenarios: deterministic, seeded YAML

```yaml
version: 1
seed: 1234
origin: {lat: 40.0700, lon: -88.6300, alt_msl: 210}   # rural flat farmland, central Illinois
basemap: {source: naip, item: il_m_4008859_ne_16_030_20230813_20240214, extent_m: 2000, gsd_m: 0.5}
ao: [[-800,-800],[800,-800],[800,800],[-800,800]]       # ENU metres; also the geofence
operator: {id: op1, path: [{t: 0, e: -300, n: -300, heading: 45}]}
teammates: [{uid: tm-2, callsign: BRAVO, path: [{t: 0, e: -320, n: -290}, {t: 300, e: -100, n: 0}]}]
assets:
  - {id: drone1, callsign: "DRONE 1", px4_instance: 0, spawn: {e: -300, n: -280}, camera: {w: 1280, h: 720, hfov: 70, pitch: -60}}
  - {id: drone2, callsign: "DRONE 2", px4_instance: 1, spawn: {e: -280, n: -280}, camera: {w: 1280, h: 720, hfov: 70, pitch: -60}}
entities:
  - {id: veh-7, cls: vehicle, sprite: pickup_tan, path: [{t: 60, e: 400, n: 250}, {t: 180, e: 150, n: 420}], speed_jitter: 0.1}
  - {id: per-3, cls: person, sprite: person_dark, path: [{t: 0, e: 380, n: -120}], loiter_radius_m: 15}
events:
  - {t: 120, type: jam, duration_s: 25, links: [mavlink:drone2, tak:*]}
  - {t: 200, type: battery_drain, asset: drone1, pct_per_min: 8}
gazetteer: [{name: "the barn", e: 410, n: 260}, {name: "north treeline", e: 0, n: 700}]
```

- **Clock:** there is one simulator clock. Entity positions are pure functions of `(seed, t)`.
- **Determinism limit:** PX4 is not bit-deterministic. The ground-truth log therefore records *flown* poses, and tests assert tolerances (e.g., "within 5 m of the orbit radius within 30 s") rather than exact equality.
- **Ground-truth event log:** `gt_events.jsonl`. Records:
  - `entity_spawn/despawn`
  - `entity_in_fov{asset, entity, t_enter, t_exit, min_range}`
  - `jam_start/end`
  - `asset_mode`
  - `battery`

  Goal-2 metrics follow directly from it: alert recall against in-FOV intervals, time-to-alert, false alerts per hour, and the fraction of feed-seconds the operator had to watch.
- **Isolation:** ground truth goes on a `sim.truth.*` channel that only `bench/` and `tests/` may import. A lint test enforces this.

### 1.7 Coordinates and location

- **Origin:** 40.0700 N, 88.6300 W, about 210 m MSL. This is flat, rural row-crop farmland in Piatt County, Illinois. **MGRS 16TCK 61002 36799 [probed]**. The NAIP thumbnail **[probed]** shows field grids, roads and a small town about 3 km away. There is no active military facility nearby (the former Chanute AFB, closed 1993, is about 35 km away).
- **Rejected sites:** the PX4 gz `baylands` world, which sits next to Moffett Federal Airfield, and any range or base.
- **Imagery:** NAIP 2023 at 0.3 m GSD, public domain, found via the Planetary Computer STAC **[probed]**. The source is a 1.97 GB COG. Fetch only a 2×2 km window with HTTP range reads (rasterio), resample to 0.5 m, and store a JPEG of about 8 MB.
- **Libraries:** `pymap3d` 3.2.0 (ENU↔geodetic) and `mgrs` 1.7.1 (wheels up to cp315).
  - ENU→MGRS→ENU round trip error: 0.4 m **[probed]**.
  - MGRS truncates (it does not round), so use lat/lon internally and MGRS only for display and voice.
  - All tiers use one `common/geo` module.

## 2. Interfaces / needs from other experts

- **Architect:**
  - Adopt the tier-agnostic port map: MAVLink 14540+i direct, or 14740+i via linkshaper; RTP 5600+i; pose sidecar 5700+i; SIH viewer 19410+i.
  - `AssetState.sensors[].stream` should be the SDP path or URL.
  - Fix the MAVSDK 4.x description, or switch to pymavlink.
  - Decide whether `NAV_DLL_ACT` is RTL (your proposal) or Hold, with `COM_DLL_EXCEPT` set so a scout mission continues during a jam. This is also a product question.
- **Vision/ML (Anshuman):**
  - Is ortho+sprite acceptable for pipeline and geolocation tests, with goal-2 accuracy taken from `replay` clips? Which clips, and under what licenses (VisDrone and Okutama are research-only)?
  - What detector input do you need (resolution and fps)?
  - Should sprites be cut from a dataset or drawn by us?
- **Voice/NLP:** use the scenario `gazetteer`, MGRS, and "bearing/range from me" as target forms. Every verb maps to the table in §1.3. Area search needs a polygon or a named area.
- **Defense SME:**
  - Default altitude band (proposed 30–120 m AGL), standoff distance for `follow`, and fence policy.
  - A realistic jam duration and the failsafe expectation.
  - Plausible entity behaviors.
- **HUD:** operator pose comes from the scenario `operator` path in the simulator. On the glasses, heading comes from IMU fusion.
- **PM/Systems:**
  - Which laptop runs the demo? Tier B needs NVIDIA plus native Ubuntu 24.04.
  - Approval to run PX4 and install apt packages here.

## 3. Pre-arrival build and how to verify it here

| # | Deliverable | Verification in this workspace |
|---|---|---|
| 1 | `common/geo` (ENU/LLA/MGRS, bearing/clock-position) | pytest round trips < 1 m; Hypothesis property tests |
| 2 | Scenario schema (pydantic + JSON Schema), loader, entity mover, GT logger | Same seed → byte-identical `gt_events.jsonl` (hash); golden-file tests |
| 3 | `MockVehicle` (pymavlink, about 500 LOC: heartbeat, telemetry 10 Hz, commands in §1.3, mission and fence protocol, battery model) | Shared **adapter contract suite**: arm → takeoff → goto → orbit → mission → hold → rtl, at 10× speed. Target under 60 s in CI. |
| 4 | Synthetic camera + encoder + sidecar; NAIP fetch script; 6 sprites | PyAV receives N frames; sidecar `frame_id` and pts match; PNG snapshot test with GT boxes overlaid; ≥25 fps at 720p measured |
| 5 | `linkshaper` | During the window, 0 packets pass; heartbeat age crosses the threshold; resync within 2 s of window end |
| 6 | PX4 SIH launcher (`edith up --assets px4`) | **After approval:** the same contract suite against 2 SIH instances; jam scenario triggers the configured `NAV_DLL_ACT`; `PX4_SIM_SPEED_FACTOR=2` CI run |
| 7 | Tier B scripts + world SDF template from the scenario origin | Lint and render the SDF here. Real test on a GPU laptop. Optional llvmpipe smoke test if apt is approved. |
| 8 | E2E smoke: 3-minute `demo_scout.yaml` + companion + `fake_glasses` | Headless CI run under 5 min; asserts in architect.md §1.8 |

Rough CPU budget here at the same time: 2 × SIH (estimated 0.2–0.3 core each, UNVERIFIED) + 2 × camera/encoder (0.5) + companion. That leaves about 0.8 core, so run the detector at 2–5 fps on sampled frames in this workspace.

## 4. Risks and mitigations

| Risk | Mitigation |
|---|---|
| PX4 binaries and apt installs are blocked in this workspace by permission policy | Tier 0 mock carries CI. Ask the user once for approval (§5). Pin the deb by sha256. |
| v1.18 packages are new and still RC | Pin `1.18.0~rc2`, bump when 1.18.0 ships, keep the source-build recipe as fallback |
| MAVSDK 4 API churn | pymavlink adapter; if MAVSDK is used, pin and keep it behind `AssetAdapter` |
| Sprites inflate detector metrics | Accuracy only from replay or real clips; sprites only for flow and geometry |
| Flat-earth homography | Flat site (relief of a few metres); document the error bound (< 1 % range error at 100 m AGL for ±3 m relief) |
| PX4 non-determinism | Tolerance-based assertions; ground truth logs flown poses |
| A team member on macOS or Windows | Tier A via Docker plus native Python; mock needs nothing |
| Tier B fails on the demo laptop (drivers, lockstep RTF) | `HEADLESS=1`, OGRE1 fallback, 640×480@15; Tier A stays the demo default |
| A QGC instance masks the jam | Route QGC through the shaper; the scenario runner warns if a foreign GCS heartbeat is seen |
| Scope creep toward weapons | No payload or strike model in the simulator; the verb allowlist is mirrored in the mock; fence plus confirmation in the contract tests |

## 5. Open questions

1. **Approval:** may this workspace (a) `apt install` the PX4 SIH `.deb` (or run it from a scratch extraction) and (b) add the OSRF repo and install `gz-harmonic` for a 10-minute llvmpipe probe? Both were blocked by the permission policy this round.
2. Does any team laptop have an NVIDIA GPU and can it boot Ubuntu 24.04 natively? How many team members use Apple silicon?
3. pymavlink (my pick) or MAVSDK 4.x for the adapter? The architect and I need to converge.
4. Link-loss doctrine: during a jam, should the drone continue its scout mission, hold, or RTL?
5. Vision: which replay datasets and licenses are acceptable for goal-2 metrics?
6. Should one asset be fixed-wing or standard VTOL (both supported by SIH) for a more realistic wide-area scout?
7. Confirm the site, or name another flat, non-sensitive area with NAIP coverage.

## Sources

- PX4 SIH: https://docs.px4.io/main/en/sim_sih/
- PX4 prebuilt SITL packages: https://docs.px4.io/main/en/simulation/px4_sitl_prebuilt_packages
- PX4 Gazebo (video 5600+i, `PX4_GZ_SIM_RENDER_ENGINE`, worlds): https://docs.px4.io/main/en/sim_gazebo_gz/index
- PX4 gz multi-vehicle: https://docs.px4.io/main/en/sim_gazebo_gz/multi_vehicle_simulation
- PX4 safety / data-link loss: https://docs.px4.io/main/en/config/safety.html
- PX4 v1.17.0 release: https://github.com/PX4/PX4-Autopilot/releases/tag/v1.17.0
- PX4 source (tag v1.18.0-rc2): `Tools/packaging/`, `.github/workflows/build_deb_package.yml`, `ROMFS/.../init.d-posix/`, `airframes/4014_gz_x500_mono_cam_down`
- Docker Hub `px4io/px4-sitl`, `px4io/px4-sitl-gazebo` tag listings
- OSRF apt repo, noble: `gz-harmonic`, `libgz-sim8` 8.15.0
- Gazebo headless rendering: https://gazebosim.org/api/sim/8/headless_rendering.html
- gz-sim macOS Metal crash: https://github.com/gazebosim/gz-sim/issues/2877
- WSLg + Gazebo: https://discourse.openrobotics.org/t/wslg-with-gpu-support-available-on-latest-version-of-gazebo-garden-and-harmonic/48128
- Low RTF report: https://discuss.ardupilot.org/t/low-rtf-in-gazebo-harmonic-simulation/141525
- gz camera to UDP 5600 thread: https://discuss.px4.io/t/px4-sitl-video-stream-unavailable-on-udp-5600/43155
- PyPI: mavsdk 4.2.1 (and its `_legacy.py` migration note), mavsdk-grpc, pymavlink 2.4.50, pymap3d 3.2.0, mgrs 1.7.1
- ArduPilot SITL binaries: https://firmware.ardupilot.org/Copter/stable/SITL_x86_64_linux_gnu/
- NAIP via Microsoft Planetary Computer STAC, item `il_m_4008859_ne_16_030_20230813_20240214`
