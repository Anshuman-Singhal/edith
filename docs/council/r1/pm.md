# R1 — Product Lead / Red Team (scope, sequencing, direction)

Stance: the deck says a lot. The demo has to prove it. Every claim below comes with the artifact that would back it in front of a judge.

## 1. Recommendations

### 1.1 Red-team objections and what we must *demonstrate*

| Objection | What we show (evidence, not slides) |
|---|---|
| **"Why glasses instead of a chest phone and an earbud?"** | A within-subject A/B test: the same software on a chest phone with an earbud vs on the glasses. We measure head-down seconds, alert response time, missed alerts and NASA-TLX. If the glasses don't win, we say so. The voice/triage layer runs on the phone too, which is also the business hedge (1.9). |
| **"RayNeo is a Chinese device."** | Agreed; it's a prototype screen. We prove portability: every RayNeo call sits behind a device HAL, we report RayNeo-specific LOC (target <5%), and the same APK runs on a stock Android phone as a "HUD." FY24 NDAA §805 bars DoD from buying from 1260H-listed firms from 30 Jun 2026 ([MoFo](https://www.mofo.com/resources/insights/260626-dod-expands-the-section-1260h-chinese-military-companies-list)). The June 2026 additions include display makers BOE and Tianma ([WilmerHale](https://www.wilmerhale.com/en/insights/client-alerts/20260611-pentagon-adds-65-new-entities-to-the-1260h-list-of-chinese-military-companies)), so "trusted" has to cover components, not just brands. Whether TCL is listed is UNVERIFIED. |
| **"Anduril EagleEye / Meta already exist."** | EagleEye is a Lattice-based family that includes a glasses variant ([TechCrunch](https://techcrunch.com/2025/10/13/andurils-new-eagleeye-mr-helmet-sees-palmer-luckey-return-to-his-vr-roots)). SBMC went to Anduril-Meta and to Palantir-backed Rivet ($195M, 470 devices) ([Breaking Defense](https://breakingdefense.com/2025/09/ivas-anduril-meta-rivet-virtual-reality-goggle-army-sbmc/)). **Don't compete on headsets.** Show vendor neutrality instead: our detections and drone tracks appear live in **unmodified ATAK-CIV** over standard CoT, and drone control uses open MAVLink/PX4. |
| **"Voice in combat is loud and gives you away."** | Voice is one input. The demo does the same tasking **silently** by temple touch or companion touchscreen, timed. We show a noise curve (command accuracy at 60/75/85/95 dB(A), recorded *through the glasses' mics*) and a false-activation count over hours of replayed radio chatter (target: 0 executions). Push-to-talk is the default; no always-on wake word. |
| **"Students can't sell to DoD."** | True; Phase 0 sells nothing. We name the transition path: SBIR/STTR (Penn as research institution), DIU CSOs, xTech, and Hacking for Defense, which now sits under DIU ([NSIN](https://www.nsin.mil/hacking-for-defense)). Evidence: a log of ≥15 discovery interviews, ≥3 with operators or drone users. |
| **"Simulation proves nothing."** | Simulate as little as possible: real glasses, real mics in real noise, real camera, real study participants. Triage is evaluated on **real aerial footage** (VisDrone-class; check license). The sim drone uses the same MAVLink path as a real PX4 vehicle, and link loss uses real packet impairment. Optional: one **real non-drone asset**, a TI mmWave "ground sensor" (1.2). |
| **Judge language trap** | "Threats," "amber diamonds" and the voice word **"track"** sound like fire control. Use **"watch"** (keep sensor on it) and **"contacts/unknown,"** plus an explicit scope-boundary slide. |

### 1.2 What would impress Mingmin Zhao
Zhao's WAVES Lab does RF/radar sensing plus ML: PanoRadar (MobiCom'24; near-LiDAR 3D from radio, through smoke and fog, at a fraction of LiDAR cost) ([Penn](https://www.engineering.upenn.edu/stories/giving-robots-superhuman-vision-using-radio-signals/)) and HoloRadar (NeurIPS'25; RF around corners) ([Penn](https://www.engineering.upenn.edu/stories/robots-that-can-see-around-corners-using-radio-signals-and-ai/)). His culture is measured systems with ablations, not demos. Give him:
1. **One crisp systems result:** a Pareto curve of alert latency and event recall vs link bandwidth/loss (50 kbps–5 Mbps, 0–30%) for stream-video vs detections+thumbnails vs edge-on-companion. This makes "edge vs offload" quantitative.
2. **Real-sensor characterization** of the glasses: battery/thermal, mic SNR, camera-to-HUD latency.
3. **Stretch:** an mmWave "ground sensor" asset. It speaks to his field and covers camera triage's dark/smoke weak spot. 2-week time-box; go/no-go at W6.

### 1.3 Scope

**Must-have:** G1 push-to-talk → constrained grammar (≤20 intents) → readback + explicit confirm → MAVLink task to SITL drone → HUD status, with touch fallback for every intent. G2 triage on real aerial clips → ranked alerts. G3 HUD v1 on the real glasses (mini-map, compass, one alert at a time, inset only when tasked, voice state) plus the user study. CoT out to stock ATAK-CIV. Degraded-link mode with resync. G4 cost model and roadmap.

**Nice-to-have:** mmWave asset; two-node shared picture; detection on the glasses' own camera; Gazebo-rendered FPV.

**Cut:** 6DoF world anchoring (3DoF heading + mini-map suffices); swarms; free-form LLM as primary control; cloud dependence; real flights; any engagement or counter-UAS actuation; face/biometric ID; own map engine or radio stack.

**Honest sim call:** 2 CPU and no GPU can't render Gazebo cameras in real time. The "drone feed" should be **real recorded aerial video time-synced to the SITL trajectory**.

**Critical path:** glasses bring-up → walking skeleton (voice → confirm → SITL → HUD → ATAK) → noise-robust voice → triage on real footage → HUD v1 on device → IRB-cleared user study → evaluation write-up → demo freeze.

### 1.4 Riskiest assumptions, retired in this order

| # | Assumption | Retire by | How |
|---|---|---|---|
| A1 | Glasses-native app can draw the HUD and read camera, mic and IMU via standard Android APIs | Days 1–3 after arrival | Bring-up APK: sideload, `com.rayneo.mercury.app` flag, per-eye vs side-by-side test pattern, CameraX frame, AudioRecord WAV, heading |
| A2 | Battery/thermal last a 10-min demo + 20-min study session | Dec 5 | Log drain/temperature for display-only, +mic, +camera+Wi-Fi; test USB-C passthrough (UNVERIFIED) |
| A3 | Glasses mics give usable ASR at ≥85 dB(A) | Dec 12 | 20 commands × 5 noise levels × 3 speakers; offline ASR + grammar |
| A4 | Glasses↔companion link supports p95 ≤2.5 s voice→HUD | Dec 12 | Ping and frame round-trip tests |
| A5 | We can study relevant users | Ask IRB **this week**; pool by Jan 31 | Penn IRB determination; ROTC, student veterans, fire/SAR |
| A6 | Triage: ≥80% less video at ≥90% event recall | W4 | Pretrained detector, event-level scoring |

### 1.5 Calendar (verify)
Penn Spring 2027: classes start **Wed Jan 20**, spring break **Mar 6–14**, last class **May 4** ([Penn English](https://www.english.upenn.edu/events/2027/01/20/first-day-spring-2027-classes); [third-party calendar](https://acadcalendar.com/upenn-academic-calendar/), UNVERIFIED against Almanac). The brief's Jan 13 start is wrong. The SEAS Senior Design competition finals were **May 2** in 2025 ([Penn](https://www.engineering.upenn.edu/stories/designing-the-future-penn-engineerings-2025-senior-design-project-competition/)), so the course demo date needs confirming with staff. **Planning assumption: final demo week of Apr 26. Feature freeze Apr 16. Demo freeze Apr 23.**

**Now → semester end (Nov 23 – ~Dec 17):** council builds the pre-arrival repo (section 3); request the IRB determination and draft the interview list now. On arrival, run A1–A4 and write a **hardware characterization memo** (for Zhao). Decide native Android vs Unity by Dec 10 (PM preference: native, since Unity can't be built here and 6DoF is unstable). Freeze contracts v0. Semester-1 deliverable: system design plus measured hardware data.

**Winter break (Dec 18 – Jan 19):** one 1-page spike per person. Arjun holds the glasses; others use the emulator. Exit target: **walking skeleton running end-to-end on the glasses by Jan 19.**

**Semester 2:**

| Wk | Dates | Milestone (owner) | Integration point |
|---|---|---|---|
| 1 | Jan 20–24 | Skeleton demo to TA; contracts v1 frozen (Anshuman) | Fri integration #1 |
| 2 | Jan 25–31 | Noise corpus v1 on glasses mics (Om); HUD v1 layout on device (Alisha); IRB cleared (Alisha) | |
| 3 | Feb 1–7 | Grammar of 20 intents and confirm protocol (Om); triage baseline on VisDrone (Anshuman); CoT→ATAK-CIV live (Simon) | Fri integration #2 |
| 4 | Feb 8–14 | **A6 gate**; link-degradation harness (Arjun) | |
| 5 | Feb 15–21 | Touch fallback for every intent (Alisha/Arjun); alert ranking v1 (Anshuman/Alisha) | Fri integration #3 |
| 6 | Feb 22–28 | Pilot study with 3 friendly users; **mmWave go/no-go** (Arjun) | |
| 7 | Mar 1–5 | **Feature-complete v1**; eval harness automated (all) | Internal demo |
| — | Mar 6–14 | Spring break: no dependencies scheduled | |
| 8 | Mar 15–21 | Fixes from the pilot; edge-vs-offload Pareto runs (Anshuman/Arjun) | |
| 9–10 | Mar 22–Apr 4 | **Main user study, N=10–12, A/B phone vs glasses** (Alisha lead, all run sessions) | |
| 11 | Apr 5–11 | Noise-curve and false-activation results (Om); cost model v1 (Simon) | |
| 12 | Apr 12–16 | **Feature freeze**; demo dry run #1 in front of mentor/TA | |
| 13 | Apr 19–23 | **Demo freeze**; backup video of every live segment; poster/report | Dry run #2 |
| 14 | Apr 26–May 2 | Final demo | |

Roles: **Arjun** owns the glasses/companion platform, HAL, power, network emulation, SITL host and mmWave. **Anshuman** owns the architecture, integration lead role, triage/detection and the edge-vs-offload benchmarks. **Alisha** owns HUD v1, alert policy, IRB and the study. **Om** owns ASR, grammar, confirmation safety and the noise eval. **Simon** owns CoT/ATAK interop, the cost model, the roadmap, interviews and the demo narrative.

### 1.6 Final demo script (~8 min) and the evidence behind each beat
1. **0:00–0:45 Problem:** photo of today's operator kit; "look down to see the map."
2. **0:45–1:30 Architecture, one slide:** "screen and ears, not the brain."
3. **1:30–4:30 Live.** Operator in glasses beside a speaker playing **85 dB(A)** babble (SPL meter visible): "Drone two, search grid Alpha." HUD readback, "Confirm," and the SITL drone moves on the big screen *and* in stock ATAK-CIV mirrored from a phone. Alert: "VEHICLE · 2 o'clock · ~400 m — Drone 2 · say 'watch' or 'dismiss'"; inset appears. A **judge reads a paragraph full of "confirm/drone/go"** and nothing executes. Comms silence: same task by touch. Cut the link (netem): the HUD degrades to detections + thumbnails, then **resyncs**. → G1, G3 live.
4. **4:30–6:30 Evidence:** G1 noise curve (accuracy, p95 latency, 0 unconfirmed executions); G2 watch-time reduction vs event recall; G3 A/B (head-down time, missed alerts, TLX, SUS); edge-vs-offload Pareto.
5. **6:30–7:30 Cost and roadmap,** with the same APK on a second device as portability proof.
6. **7:30–8:00 Boundary and ask:** ISR/navigation/awareness only, human confirmation on every asset command, no weapons, no face ID.

**Targets:** G1 ≥90% intent success at 85 dB(A), p95 ≤2.5 s end-of-speech→readback, 0 unconfirmed executions, <1 false confirm prompt per hour of chatter. G2 ≥80% fewer video-seconds at ≥90% event recall. G3: a significant difference *or an honestly reported null* vs phone on alert response and head-down time, with 0 accidental confirms.

### 1.7 Goal 4: cost model outline and sanity check
- **Anchors (fix the deck).** IVAS was worth up to $22B for ~120k headsets ([TechCrunch](https://techcrunch.com/?p=2132814)). That's ~$180k per soldier of **lifecycle program value**, not unit price. Hardware was ~**$80k/unit**, and the Army demanded it drop ([Bloomberg](https://www.bloomberg.com/news/articles/2024-10-19/microsoft-goggles-cost-must-drop-from-80-000-each-army-says); [CRS](https://www.everycrsreport.com/files/2025-06-06_IF13022_ccafd0f9898ef2fc4401177e88145f3b9004494a.html)). Compare unit to unit and lifecycle to lifecycle.
- **BOM lines per kit:** glasses, companion EUD, radio, software (per seat per year), power/cables, training/sustainment, amortized accreditation. Drones are listed separately: Skydio's $52M for 2,500+ X10D ≈ $21k/system ([Skydio](https://skydio.com/blog/u-s-army-usd52-million-order-skydio-x10d)).
- **Full kit ~$25k:** plausible only with a MANET radio (Silvus/MPU5 priced by quote, ~$10–20k UNVERIFIED). Since we sit on existing systems, the **radio is usually already owned**. Incremental kit = trusted glasses (~$2–5k, UNVERIFIED) + EUD (~$1.5–2.5k, UNVERIFIED) + software (~$3–5k/seat/yr) ≈ **$7–12k**.
- **Lite kit ~$8k:** plausible. goTenna Pro X is **$849** with ATAK support ([Officer](https://www.officer.com/command-hq/technology/communications/radios-accessories/product/21081906/gotenna-gotenna-pro-x-tactical-mesh-radio)), plus glasses, phone and software.
- **Unit economics:** revenue is software ARR per seat; hardware is pass-through at 15–25% margin. Model price sensitivity, seats per pilot (≈30–100) and sales-cycle cash needs.
- **Phase 0 spend:** RayNeo $1,099–1,399 ([Tom's Hardware](https://www.tomshardware.com/peripherals/wearable-tech/rayneo-x3-pro-ar-glasses-review)), plus SPL meter, speaker, optional TI mmWave EVM, used Android companion. Target <$2k beyond the glasses.

### 1.8 Roadmap and gates
- **Phase 0→1 gate (May 2027):** G1–G3 targets hit; ≥15 interviews; ≥1 LOI or pilot conversation (DIU, SOFWERX, fire/SAR agency); portability proven; full-time decision; Penn IP policy checked.
- **Phase 1 (6–12 mo):** trusted-hardware port. **Vuzix** (Rochester NY) builds waveguide engines for a Collins dismounted-soldier/drone-control display, with LRIP from Q1 2026 ([Vuzix](https://ir.vuzix.com/news-events/press-releases/detail/2157/vuzix-and-collins-aerospace-announce-strategic)). **DigiLens ARGO** (US; XR2, 30° FOV, >3,500 nits, ~200 g; build location UNVERIFIED) ([DigiLens](https://www.digilens.com/wp-content/uploads/2024/08/DL-ARGO-Tech-FAQ-v2.pdf)). **ThirdEye X2** (NJ; TAA statement, which is not the same as US-made) ([ThirdEye](https://www.thirdeyegen.com/taa-compliance-statement)). Audit components against 1260H. Ship the ATAK plugin via TAK.gov **third-party signing**, open to anyone not on the Denied Parties List ([TAK.gov](https://tak.gov/pages/our-process)). First real flights with a Blue UAS drone at a range. Gate: SBIR I/CSO award plus field test.
- **Phase 2:** squad-leader workflows, deep ATAK, ATO/RMF path, offline sync. Gate: accreditation sponsor.
- **Phase 3:** multi-asset ISR tasking (human-confirmed), team mesh, lite SKU.
- **Dual-use order:** SAR and wildland fire first (fast buyers, clean ethics); law enforcement last, with guardrails (no persistent surveillance, no ID).

### 1.9 Startup direction
"An operator layer on top of existing systems" is **only weakly defensible**: ATAK is free and government-owned, and Lattice/Palantir are moving to the edge. Moat candidates: (a) **integration breadth** (Blue UAS adapters, CoT, MAVLink); (b) **validated safety**, i.e. a voice-tasking protocol with published noise and false-activation evidence, which accreditation reviewers want; (c) an **operator-feedback data loop**, where every "watch/dismiss" is a triage label (the real moat if data rights allow); (d) **ATO accreditation** once earned.

**Wedge:** a voice-tasking and feed-triage **ATAK plugin that works on the phone first**, with glasses as the upgrade. It has the lowest adoption friction and survives losing the glasses A/B test. **Do not build:** weapons/targeting/fires hooks, autonomous engagement, face ID, our own drones/radios/glasses/map engine, or a general chatbot.

## 2. Interfaces and needs from other experts
- **Architect:** device HAL boundary plus portability metric; versioned, CoT-mappable schemas (Intent, TaskRequest/Confirm, AssetState, Detection/Alert); per-hop latency budget; native-vs-Unity call.
- **Voice/NLP:** intent list; confirm state machine (readback, timeout, no execution on ambiguity); noise-mix harness with license-clean noise; false-activation suite.
- **Vision/ML:** event-level triage metrics; dataset licenses; CPU-sized models; bandwidth-strategy experiment.
- **HUD/UX:** device-faithful 640×480 emulator; alert ranking; study protocol and IRB text.
- **Platform/Sim:** headless PX4 SITL (or minimal MAVLink sim) on 2 CPU; trajectory-synced video replay; netem profiles.

## 3. Pre-arrival builds by the council, and how we verify them

| Build | Verify |
|---|---|
| Repo, schemas, contract tests | CI green; schema and CoT XML round-trip |
| 640×480 HUD emulator on the bus | Snapshot tests of alert, inset and degraded states |
| CPU voice pipeline + noise harness | Intent accuracy on TTS+noise at SNR levels (synthetic; replaced by glasses-mic data in Dec) |
| Confirm-gated SITL/MAVLink adapter | Scripted mission; test that no MAVLink goes out without Confirm |
| Triage on real aerial clips | Event recall and watch reduction on a labeled clip |
| CoT bridge | Parses in an open CoT library; live ATAK check on device |
| Android bring-up APK (A1) + HUD skeleton | Gradle build, unit tests, manifest flag |
| Link-degradation shim (app-level if no root `tc`) | Golden run under 3 link profiles |
| Cost model (CSV + script), every number sourced | Totals reproduce; UNVERIFIED flagged |
| Golden demo replay | End-to-end sim run in CI |

## 4. Risk register (top 10)

| # | Risk | Owner | L | I | Mitigation |
|---|---|---|---|---|---|
| 1 | RayNeo blocks camera/mic access or a custom display path | Hardware | M | H | Day-1 bring-up; HAL; phone-mirrored mode; emulator |
| 2 | Single pair of glasses breaks or is lost | Hardware | M | H | Handling log; Android phone as backup HUD; budget for a second unit |
| 3 | Battery/thermal shorter than demo/session (reviewers saw ~1 h) | Hardware | H | M | External power; display-only mode; compute offloaded to the companion |
| 4 | ASR fails in noise | Voice | M | H | Push-to-talk; constrained grammar; companion/close-talk mic fallback; touch path |
| 5 | Unsafe or accidental command execution | Voice+UX | L | H | Readback plus explicit confirm; timeouts; adversarial suite; a test that blocks any unconfirmed MAVLink |
| 6 | Triage doesn't generalize; no GPU for training | ML | M | M | Pretrained models plus light fine-tuning on external GPU (Colab/Penn, UNVERIFIED); report on real footage |
| 7 | IRB delay or no relevant participants | UX | M | H | Request the determination now; ROTC/veterans/fire-SAR pool; civilian dual-task fallback |
| 8 | Integration slip; no skeleton by Jan 19 | Integration (Anshuman) | M | H | Frozen contracts; Friday integrations; skeleton is the winter-break exit criterion |
| 9 | Scope creep (6DoF, swarm, LLM, real flights) | PM/Simon | H | M | Cut list; change requires mentor sign-off |
| 10 | Read as weapons, a toy, or a China-dependent product; export-control slip | Commercial | M | H | Boundary slide; "watch" not "track"; portability proof; public/fundamental-research data only, no CUI/ITAR tech data |

## 5. Open questions
1. What is the exact course demo date, and what are the deliverables (report, poster, video)? Is it the SEAS-wide competition or the department's own?
2. Is the companion an Android phone (preferred, matching the ATAK EUD story) or a laptop for Phase 0?
3. Is there budget for a second display device (backup and portability proof)?
4. Does Zhao want a research contribution (the Pareto study, or mmWave) or a product demo? Ask at the next mentor meeting.
5. Does the team accept "SITL plus real recorded footage" as proof of G1/G2? Get mentor agreement in writing before Jan 20.
6. Who wants to go full-time after May, and what does Penn's IP policy say about student projects?
