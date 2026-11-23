# E.D.I.T.H. Council Brief (read fully before working)

Date: 2026-11-23. You are one expert on a council planning and then building the software for a Penn senior design project. The lead (Claude) coordinates; the human client is Anshuman Singhal (team member, Vision & ML role).

## 1. The product (from the team's midpoint deck, the source of truth)

**E.D.I.T.H. — "the intelligence hub for the battlefield operator."** Lightweight AR glasses that bring comms, maps, drones and AI analysis into one voice-driven heads-up interface. The glasses are the screen and microphone (+ camera); the intelligence lives across a companion device, the network and the assets.

Problem (slide 3): operators carry a radio, a chest-mounted computer (ATAK phone), drone controllers (often one pilot/screen per drone) and video feeds (more footage than anyone can watch, not linked to the map). Checking the map means looking down. Result: fragmented info, high cognitive load, fewer hands free.

Four layers (slide 14):
1. **Glasses · interface** — HUD, mic, camera. "The screen and the ears, not the brain."
2. **Companion · compute** — rugged on-body device: runs AI, works offline, touch backup when voice can't be used.
3. **Mesh · network** — links teammates, assets, HQ; syncs when connection returns after jamming.
4. **Assets · "exoskeleton"** — drones/swarms, ground sensors, analysis tools, directed by intent.

Hard problems the team committed to (slide 5): voice-to-asset commands (noisy speech → safe structured drone tasking); edge video inference on drone feeds within power/thermal budgets, glasses vs companion offload; offline-first; HUD under cognitive load (ranked alerts, confirmation flows hard to trigger by accident).

Goals for the year (slide 7):
1. Prove one operator can direct a drone by voice from the glasses.
2. Show AI filtering cuts how much video the operator must watch.
3. Design a HUD that stays readable and safe under stress.
4. Deliver a cost model and roadmap to a real product.

Milestones: Semester 1 (now, ending Dec 2026) = research, users, stack, system design. Semester 2 weeks 1–7 = build voice tasking, inference training, HUD v1. Weeks 8–14 = test with operators, cost model, final demo (~late April 2027). Roadmap Phase 0 (this year) = "three core features in simulation; operator-tested HUD; cost model." Phase 1 pilot on trusted hardware with SOF/DIU; Phase 2 squad leaders, ATAK integration, accreditation, offline sync; Phase 3 swarm, team mesh, lite version.

HUD wireframe v0 (slide 15): top-left mini-map (teammates blue, threats amber diamonds); top-right inset with drone feed appears only when tasked ("DRONE 2 · LIVE"), compass strip "N · NE · E"; center kept clear; one ranked alert banner at a time with voice options ("VEHICLE · 2 o'clock · about 400 m — Flagged by Drone 2 · say 'track' or 'dismiss'"); bottom-left voice state ("● Listening").

Users (slide 6): initial = SOF teams and unit drone operators; core = Army/USMC squad & team leaders; expansion = counter-drone teams, forward observers, EW.

Market gap (slide 11): ATAK (phone, look down); IVAS/SBMC (heavy, Anduril-led); asset-control software like Lattice (command-post, not wearable); single-vendor drone controllers; consumer glasses (not secure); Anduril EagleEye (vertically integrated). Target: "a lightweight, voice-first operator layer that sits on top of existing systems instead of replacing them." ATAK integration is key to credibility.

Team (slide 10 roles): Arjun — Hardware & Platform; Anshuman — Vision & ML (ML systems, detection model survey, edge vs offload, system architecture); Alisha — Product & HUD UX; Om — Voice & NLP; Simon — Systems & Commercial (competitors, milestones, cost model). Faculty mentor Mingmin Zhao; TA Zitong Lan.

## 2. Hardware: RayNeo X3 Pro (one pair purchased, arriving ~1 week)
- Qualcomm Snapdragon AR1, 4 GB RAM, 32 GB; Android-based RayNeo AIOS. Glasses-native apps sideloaded via ADB.
- Binocular full-color MicroLED + etched waveguide, 640×480, ~30° FOV, up to ~6,000 nits peak.
- Sony IMX681 12 MP RGB camera + mono camera for SLAM; 6DoF in Unity "Creator mode" (one reviewer found 3D anchoring unstable); native 3DoF.
- 3 mics with beamforming; speakers; Wi-Fi 5, Bluetooth; touch/temple input + ring optional.
- 245 mAh battery (~5 h claimed; reviewers report much less with camera/display); 76 g.
- SDKs: (a) Android native — camera/audio/IMU through standard Android APIs (Camera2/CameraX, AudioRecord, SensorManager); (b) RayNeo OpenXR Unity ARDK (Unity 2022.3.36f1). Docs partly on Feishu, some Chinese. A glasses-native app needs manifest `<meta-data android:name="com.rayneo.mercury.app" android:value="true"/>` (else it's treated as a phone-mirrored app needing a ring). Binocular display may require rendering per eye / side-by-side — UNVERIFIED, must be confirmed on device.
- Made by TCL/RayNeo (China) — fine for prototype; roadmap Phase 1 moves to trusted hardware, so the software must be hardware-portable.

## 3. Build environment facts (this cloud workspace)
- Linux x86_64, **2 CPU, 7 GB RAM, no GPU, no Docker daemon**, ~30 GB free disk.
- Installed: Python 3.13, Java 21, Gradle 8.14, Node 22, git, cmake, gcc, ffmpeg. Not installed: Android SDK (but dl.google.com/android repository and Google Maven ARE reachable, so sdkmanager/cmdline-tools can be installed), Unity (not feasible here), adb.
- Network reachable: PyPI, Maven Central, Google Maven, Gradle, Hugging Face, GitHub (clone + release assets), Ubuntu apt, OSRF packages (Gazebo), PyTorch CPU wheels.
- No physical glasses or drones are available to us. Nothing can be flight-tested. We can build an emulator of the glasses HUD (e.g., 640×480 desktop/web window) and test everything end-to-end in simulation.
- The client's own computer may be reachable later with approval; do not plan around it.

## 4. Hard constraints (non-negotiable)
- **Scope = awareness, ISR/reconnaissance tasking, navigation, alerting, team picture.** No weapons employment, no strike targeting, no fire-control, no autonomous engagement or kill-chain automation, no "countermeasure" actuation beyond notional status display. Every asset command needs explicit human confirmation.
- **No facial recognition or biometric identification.** Detection classes are things like person/vehicle/drone, never identity.
- **Simulation only** for drones in Phase 0 (no real flights; campus is near PHL airspace).
- Free/open-source tools; no paid APIs required for the core loop (cloud LLM may be an optional offload path to benchmark, never required). Offline-first.
- Must be buildable and maintainable by 5 undergrads over ~14 weeks, with the hardest risks retired first.

## 5. What the council produces
Phase A (planning loop): a single PLAN.md covering (1) architecture, (2) software & build plan (repo layout, components, interfaces/protocols, tech choices with rationale, tests, the week-one glasses bring-up tests, metrics/benchmarks), (3) long-term planning, scope and direction (semester-2 milestones mapped to the 5 people, demo script, evaluation/user-study design, Phase 1–3 roadmap, risks). Loop until all experts approve.
Phase B (execution): build the plan's "pre-arrival" scope in this workspace so the repo is ready to run end-to-end in simulation and ready to deploy to the glasses the day they arrive.

## 6. Working rules
- Ground claims in facts; mark anything unverified as UNVERIFIED (especially RayNeo SDK specifics). Do web research where it matters (you have WebSearch/WebFetch).
- Be concrete: name libraries, versions, message schemas, numbers. Prefer the simplest thing that proves each goal.
- Be honest about what is infeasible in a 2-CPU, no-GPU workspace and propose fallbacks.
- Write your output file in Markdown; keep it tight (aim 1,200–2,500 words). No filler.
