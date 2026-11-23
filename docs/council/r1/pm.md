# R1 — Product Lead / Red Team (scope, sequencing, direction)

Stance: the deck says a lot. The demo has to prove it. Every claim below comes with the artifact that would back it in front of a judge.

## 1. Recommendations

### 1.1 Red-team objections and what we must *demonstrate*

| Objection | What we show (evidence, not slides) |
|---|---|
| **"Why glasses instead of a chest phone and an earbud?"** | A within-subject A/B test in the user study. Condition A runs the same software on a chest-mounted phone with an earbud. Condition B runs it on the glasses. We measure head-down seconds, alert response time, missed alerts, NASA-TLX and task time. If the glasses don't win, we report that and fall back: the voice/triage layer runs on the phone as well. That fallback is also the business hedge (see 1.6). |
| **"RayNeo is a Chinese device."** | Agreed. It's a prototype screen, nothing more. We prove portability: every RayNeo-specific call sits behind a HUD/Device HAL, and we report the RayNeo-specific LOC as a % of the codebase (target <5%). The same APK runs on a stock Android phone as a "HUD" in the demo. Context for the roadmap: FY24 NDAA §805 bars DoD from buying from 1260H-listed firms as of 30 Jun 2026 ([MoFo](https://www.mofo.com/resources/insights/260626-dod-expands-the-section-1260h-chinese-military-companies-list)). The June 2026 additions include display makers BOE and Tianma ([WilmerHale](https://www.wilmerhale.com/en/insights/client-alerts/20260611-pentagon-adds-65-new-entities-to-the-1260h-list-of-chinese-military-companies)). So "trusted" has to cover components too, not just the brand. Whether TCL itself is listed is UNVERIFIED. |
| **"Anduril EagleEye / Meta already exist."** | EagleEye is a Lattice-based family that already includes a glasses variant ([TechCrunch](https://techcrunch.com/2025/10/13/andurils-new-eagleeye-mr-helmet-sees-palmer-luckey-return-to-his-vr-roots)). SBMC went to Anduril-Meta and to Rivet, which is backed by Palantir; Rivet's award was $195M for 470 devices ([Breaking Defense](https://breakingdefense.com/2025/09/ivas-anduril-meta-rivet-virtual-reality-goggle-army-sbmc/)). **We should not compete on headsets.** We show vendor neutrality instead. Our detections and drone tracks show up live in an **unmodified ATAK-CIV** over standard CoT. Drone control goes through MAVLink/PX4, the open path used by non-Anduril sUAS. |
| **"Voice in combat is loud and gives you away."** | Voice is one input. The demo completes the same tasking **silently** through temple touch or the companion touchscreen, and we time it. We plot a noise curve: command accuracy at 60/75/85/95 dB(A) babble and vehicle noise, recorded *through the glasses' own mics*. We measure a false-activation rate over hours of replayed radio chatter, and the target is 0 executions. Push-to-talk is the default. No always-on wake word in tactical mode. |
| **"Students can't sell to DoD."** | True, and Phase 0 sells nothing. We show a named transition path: SBIR/STTR (Penn as the STTR research institution), DIU CSOs, xTech, and Hacking for Defense, which now sits under DIU ([NSIN](https://www.nsin.mil/hacking-for-defense)). Evidence: a log of ≥15 customer-discovery interviews, ≥3 of them with operators or drone users. |
| **"Simulation proves nothing."** | We minimize what is simulated. Real glasses, real mics in real noise, real camera, real people in the user study. Detection is evaluated on **real aerial footage** (VisDrone-class datasets; check the license). The sim drone uses the same MAVLink path a real PX4 vehicle uses. We emulate link loss with real packet impairment. Optional extra: one **real non-drone asset**, a TI mmWave radar "ground sensor" publishing detections (see 1.4). |
| **Judge language trap** | "Threats," "amber diamonds" and the voice word **"track"** sound like fire control. Rename the voice command "track" to **"watch"** (keep sensor on it) and call the markers **"contacts/unknown"**. Add an explicit scope-boundary slide. |

### 1.2 What would impress Mingmin Zhao
Zhao runs Penn's WAVES Lab, which does RF/radar sensing plus ML. PanoRadar (MobiCom'24) gets near-LiDAR 3D from radio, works through smoke and fog, and costs a fraction of LiDAR ([Penn](https://www.engineering.upenn.edu/stories/giving-robots-superhuman-vision-using-radio-signals/)). HoloRadar (NeurIPS'25) sees around corners with RF ([Penn](https://www.engineering.upenn.edu/stories/robots-that-can-see-around-corners-using-radio-signals-and-ai/)). His culture is measured systems with ablations, not demos. Give him:
1. **One crisp systems result.** A Pareto curve of alert latency and event recall vs link bandwidth/loss (50 kbps–5 Mbps, 0–30% loss) for three strategies: stream video, send detections + thumbnails, and edge-on-companion. This is the "edge vs offload" hard problem made quantitative.
2. **Real-sensor characterization** of the glasses: battery and thermal under load, mic SNR, camera-to-HUD latency.
3. **Stretch:** an mmWave "ground sensor" as a second asset type. It speaks to his field and to the dark/smoke weak spot of camera triage. Time-box it to 2 weeks, with go/no-go at semester-2 W6.

### 1.3 Scope

**Must-have (Phase 0 = goals 1–3 + cost model):**
- G1: push-to-talk voice → constrained grammar (≤20 intents) → readback and explicit confirm → MAVLink task to a SITL drone → status shown on the HUD. Touch fallback for every intent.
- G2: a triage pipeline on real aerial clips that outputs ranked alerts. Measure watch-time reduction vs event recall.
- G3: HUD v1 on the real glasses (mini-map, compass strip, one alert at a time, a drone inset only when tasked, voice state), plus a user study.
- CoT out to stock ATAK-CIV. A degraded-link mode with resync.
- Cost model and roadmap (G4).

**Nice-to-have:** the mmWave asset; two operators on two nodes sharing a picture; on-glasses detection from the glasses' own camera; drone FPV rendered in Gazebo.

**Cut for Phase 0:** 6DoF world-locked anchoring (reported unstable; 3DoF heading plus a mini-map is enough). Swarms and multi-drone autonomy. Free-form LLM chat as the primary control. Cloud dependence. Any real flight. Any engagement or counter-UAS actuation. Face/biometric ID. Our own map engine. Our own radio stack.

**Honest sim call (for the architect):** a 2-CPU, no-GPU box can't render Gazebo camera feeds in real time. The "drone feed" should be **real recorded aerial video, time-synced to the SITL trajectory**. Gazebo rendering is a nice-to-have on a GPU laptop.

**Critical path:** glasses bring-up → walking skeleton (voice → confirm → SITL → HUD → ATAK) → noise-robust voice → triage on real footage → HUD v1 on device → IRB-cleared user study → evaluation write-up → demo freeze.

### 1.4 Riskiest assumptions, retired in this order

| # | Assumption | Retire by | How |
|---|---|---|---|
| A1 | A glasses-native app can draw the HUD and read the camera, mic and IMU through standard Android APIs | Day 1–3 after arrival (~Dec 1) | Bring-up APK: ADB sideload, `com.rayneo.mercury.app` flag, test pattern per eye vs side-by-side, CameraX frame, AudioRecord WAV, rotation-vector heading |
| A2 | Battery and thermal last a 10-minute demo plus a 20-minute study session | Dec 5 | Log drain and temperature for display-only, display+mic and display+camera+Wi-Fi. Test USB-C passthrough power (UNVERIFIED) |
| A3 | The glasses' mics give usable ASR at ≥85 dB(A) | Dec 12 | Record 20 commands × 5 noise levels × 3 speakers; offline ASR plus a grammar parser on a laptop |
| A4 | Glasses ↔ companion latency over Wi-Fi/BT supports the voice→HUD loop with p95 ≤ 2.5 s | Dec 12 | Ping and frame round-trip tests |
| A5 | We can run a study with relevant users | IRB determination requested **this week**; recruit pool by Jan 31 | Penn IRB "not human research" or exempt determination. Recruit from ROTC, student veterans, local fire/SAR |
| A6 | Triage cuts video ≥80% at ≥90% event recall on real aerial clips | Semester-2 W4 | Baseline pretrained detector, event-level scoring |

### 1.5 Calendar (verify)
Penn Spring 2027: classes start **Wed Jan 20**, spring break **Mar 6–14**, last class **May 4** ([Penn English](https://www.english.upenn.edu/events/2027/01/20/first-day-spring-2027-classes); [third-party calendar](https://acadcalendar.com/upenn-academic-calendar/), UNVERIFIED against Almanac). The brief's Jan 13 start is wrong. The SEAS Senior Design competition finals were **May 2** in 2025 ([Penn](https://www.engineering.upenn.edu/stories/designing-the-future-penn-engineerings-2025-senior-design-project-competition/)), so the course demo date needs confirming with staff. **Planning assumption: final demo week of Apr 26. Feature freeze Apr 16. Demo freeze Apr 23.**

**Now → semester end (Nov 23 – ~Dec 17):** council builds the pre-arrival repo (section 3). Request the IRB determination and draft the interview list now. On glasses arrival, run A1–A4 and write a **hardware characterization memo** (for Zhao). Freeze the native-Android vs Unity decision by Dec 10 (PM preference: native Android, because Unity can't be built here and 6DoF is unstable). Freeze the interface contracts v0. Semester-1 deliverable: system design plus measured hardware data.

**Winter break (Dec 18 – Jan 19):** one 1-page spike per person. Arjun keeps the glasses; everyone else works against the HUD emulator. Exit target: **walking skeleton runs end-to-end on the glasses by Jan 19.**

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
1. **0:00–0:45 Problem.** A photo of today's operator kit. "Look down to see the map."
2. **0:45–1:30 Architecture, one slide.** "Glasses are the screen and ears, not the brain."
3. **1:30–4:30 Live.** The operator wears the glasses next to a speaker playing **85 dB(A)** battlefield babble, measured with an SPL meter. Says "Drone two, search grid Alpha." The HUD reads it back, the operator says "Confirm," and the SITL drone moves on the big screen *and* on stock ATAK-CIV mirrored from a phone. An alert appears: "VEHICLE · 2 o'clock · ~400 m — Drone 2 · say 'watch' or 'dismiss'." The inset appears. Next, a **judge reads a paragraph full of "confirm/drone/go"** and nothing executes. Then comms silence: the same task is done by touch. Finally, cut the link (netem). The HUD degrades to detections + thumbnails, then **resyncs** when the link returns. → G1 and G3, live.
4. **4:30–6:30 Evidence.** The G1 noise curve (intent accuracy, p95 latency, 0 unconfirmed executions). The G2 curve of watch-time reduction vs event recall. The G3 A/B results (head-down time, missed alerts, TLX, SUS). The edge-vs-offload Pareto curve.
5. **6:30–7:30 Cost and roadmap.** The same APK running on a second device as the portability proof.
6. **7:30–8:00 Boundary and ask.** ISR, navigation and awareness only. Human confirmation on every asset command. No weapons. No face ID.

**Targets:** G1 ≥90% intent success at 85 dB(A), p95 ≤2.5 s from end of speech to readback, 0 unconfirmed executions, <1 false confirm prompt per hour of chatter. G2 ≥80% fewer video-seconds shown at ≥90% event recall. G3 shows a statistically meaningful *or honestly reported null* difference in alert response time and head-down time vs the phone, with 0 accidental confirms.

### 1.7 Goal 4: cost model outline and sanity check
- **Anchors (fix the deck).** IVAS was a contract worth up to $22B for roughly 120k headsets ([TechCrunch](https://techcrunch.com/?p=2132814)). That is about $180k per soldier of **lifecycle program value**, not unit price. Hardware ran about **$80k per unit**, and the Army demanded it come down ([Bloomberg](https://www.bloomberg.com/news/articles/2024-10-19/microsoft-goggles-cost-must-drop-from-80-000-each-army-says); [CRS](https://www.everycrsreport.com/files/2025-06-06_IF13022_ccafd0f9898ef2fc4401177e88145f3b9004494a.html)). Compare unit to unit and lifecycle to lifecycle.
- **BOM lines per kit.** Glasses; companion EUD; radio; software license per seat per year; batteries and cables; training and sustainment; accreditation amortized. Drones are listed separately: Skydio's $52M order for 2,500+ X10D works out to about $21k per system ([Skydio](https://skydio.com/blog/u-s-army-usd52-million-order-skydio-x10d)).
- **Full kit at ~$25k.** Plausible only if it includes a MANET radio. Silvus or MPU5 prices aren't public and come by quote (UNVERIFIED, roughly $10–20k). Since we "sit on top of existing systems," the **radio is usually already owned**. Our incremental kit is trusted glasses (~$2–5k at low volume, UNVERIFIED) + EUD (~$1.5–2.5k, UNVERIFIED) + software (~$3–5k per seat per year) ≈ **$7–12k**.
- **Lite kit at ~$8k.** Plausible: goTenna Pro X **$849** with ATAK support ([Officer](https://www.officer.com/command-hq/technology/communications/radios-accessories/product/21081906/gotenna-gotenna-pro-x-tactical-mesh-radio)), plus glasses, phone and software.
- **Unit economics.** Revenue is software ARR per seat. Hardware is pass-through at 15–25% margin. Model price sensitivity and seats per pilot (≈30–100), and sales-cycle cash needs.
- **Phase 0 actual spend:** RayNeo at $1,099–1,399 ([Tom's Hardware](https://www.tomshardware.com/peripherals/wearable-tech/rayneo-x3-pro-ar-glasses-review)), plus an SPL meter, speaker, optional TI mmWave EVM, and a used Android companion. Target <$2k beyond the glasses.

### 1.8 Roadmap and gates
- **Phase 0 → 1 gate (May 2027):** G1–G3 targets hit; ≥15 interviews; ≥1 LOI or pilot conversation (DIU, SOFWERX, a fire/SAR agency); portability proven; a decision on who goes full-time; Penn IP policy checked (UNVERIFIED).
- **Phase 1 (pilot, 6–12 months):** port to trusted hardware. Candidates: **Vuzix** (Rochester NY; supplies waveguide engines for a Collins dismounted-soldier/drone-control display, LRIP Q1 2026 ([Vuzix](https://ir.vuzix.com/news-events/press-releases/detail/2157/vuzix-and-collins-aerospace-announce-strategic))); **DigiLens ARGO** (US; XR2, 30° FOV, >3,500 nits, ~200 g ([DigiLens](https://www.digilens.com/wp-content/uploads/2024/08/DL-ARGO-Tech-FAQ-v2.pdf)), manufacturing location UNVERIFIED); **ThirdEye X2** (NJ; publishes a TAA statement, which is not the same as US-made ([ThirdEye](https://www.thirdeyegen.com/taa-compliance-statement))). Audit components against 1260H. Ship an ATAK plugin through TAK.gov's **third-party signing** pipeline, which is open to anyone not on the Denied Parties List and carries a third-party badge ([TAK.gov](https://tak.gov/pages/our-process)). Use a Blue UAS drone for the first real flights at a range. Gate: SBIR Phase I or CSO award plus a field test.
- **Phase 2:** squad-leader workflows, deep ATAK integration, an ATO/RMF path, offline sync. Gate: a government sponsor for accreditation.
- **Phase 3:** multi-asset ISR tasking (still human-confirmed), team mesh, lite SKU.
- **Dual-use order:** SAR and wildland fire first (fast buyers, clean ethics). Law enforcement last, and only with policy guardrails (no persistent surveillance, no ID).

### 1.9 Startup direction
"An operator layer on top of existing systems" is **only weakly defensible**. ATAK is free and government-owned, and Lattice/Palantir are moving down to the edge. The moat candidates:
- (a) **Integration breadth:** Blue UAS vendor adapters, CoT, MAVLink.
- (b) **Validated safety:** a voice-tasking protocol with published noise and false-activation evidence, which is what accreditation reviewers want.
- (c) **An operator-feedback data loop:** every "watch/dismiss" is a label that improves triage. This is the real moat if data rights allow it.
- (d) **ATO accreditation** once earned.

**Wedge:** a voice-tasking and feed-triage **ATAK plugin that works on the phone first**, with glasses as the upgrade. That's the lowest adoption friction, and it survives a loss in the glasses A/B test. **Do not build:** weapons/targeting/fires hooks, autonomous engagement, face ID, our own drones/radios/glasses/map engine, or a general chatbot.

## 2. Interfaces and needs from other experts
- **Architect:** the HAL boundary for the glasses, with a portability metric; versioned schemas for Intent, TaskRequest/Confirm, AssetState, Detection/Alert, all CoT-mappable; a latency budget per hop; and the native-vs-Unity call.
- **Voice/NLP:** the intent list; the confirmation state machine (readback, timeout, no execution on ambiguity); a noise-mix eval harness using license-clean noise; a false-activation suite.
- **Vision/ML:** event-level triage metric definitions; dataset licenses; models sized for a CPU companion; the bandwidth-strategy experiment design.
- **HUD/UX:** a 640×480 emulator that matches the device; alert ranking policy; the study protocol and IRB text.
- **Platform/Sim:** a headless PX4 SITL or minimal MAVLink sim on 2 CPU; video replay synced to the trajectory; netem profiles.

## 3. Pre-arrival builds by the council, and how we verify them

| Build | Verify |
|---|---|
| Repo layout and schemas with contract tests | CI passes; a schema round-trip and CoT XML validated against samples |
| HUD emulator (640×480) driven by the message bus | Snapshot tests of the wireframe states, including alert, inset and degraded |
| Offline voice pipeline (CPU ASR plus grammar) and noise harness | Intent accuracy on TTS commands mixed at SNR levels (flagged synthetic; real glasses-mic data replaces it in Dec) |
| SITL/MAVLink adapter with confirm-gated tasking | A scripted mission test, and a test that no MAVLink command is emitted without a Confirm event |
| Triage pipeline on sample real aerial clips | Event recall and watch-reduction computed on a labeled clip |
| CoT bridge | Packets parse in an open CoT/TAK library; live ATAK check deferred to device |
| Android bring-up APK (A1 checklist) and HUD app skeleton | Gradle build passes; unit tests pass; manifest flag present |
| Link-degradation shim (app-level if no root `tc`) | Golden run under three link profiles |
| Parameterized cost model (CSV plus script) with a source for every number | Totals reproduce; UNVERIFIED cells flagged |
| "Golden demo" replay test | End-to-end in sim, run in CI |

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
