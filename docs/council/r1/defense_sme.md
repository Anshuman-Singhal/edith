# R1 — Defense Operator / Domain SME

Goal: Phase 0 credible to operators and buyers, inside scope (ISR, awareness, navigation, alerting; human confirms every command; no targeting or facial recognition).

## 1. Recommendations

### 1.1 Workflows the demo should mirror
Build the demo around three real small-unit loops:

1. **Task an sUAS for recon or overwatch.** Today the leader tells a pilot what to look at, then looks down at the pilot's screen or ATAK. E.D.I.T.H. makes it one step: the leader states intent, the system reads it back, the leader confirms, and the drone runs a bounded behavior.
2. **Report a contact.** Units report in SALUTE form (Size, Activity, Location, Unit, Time, Equipment). An AI flag arrives as a draft SALUTE card. The operator **tracks** it (keeps observing), **marks** it (puts it on the team map) or **dismisses** it. Only human-confirmed marks go out to the team.
3. **Maintain the team picture.** Every device broadcasts its position (PLI) as CoT, and contacts carry stale times. The leader always needs to know where people and drones are, what's new and what's stale.

**HUD vs phone (companion):**

| HUD (glanceable, under 2 s) | Phone/companion (look-down, deliberate) |
|---|---|
| Compass strip and own heading | Full map, layers, route and NAI editing |
| Mini-map: teammates, drones, top contacts | Detection history, clip review, scrubbing |
| **One** ranked alert, at most about 8 words plus voice options | Full SALUTE details, confidence, thumbnails |
| Pending-confirmation banner showing the parsed command | Command log and audit trail |
| Drone chips (D1/D2: mode, battery, link state) | Settings, server config, chat |
| Drone inset only while a drone is tasked or an alert is open | Touch backup for confirm, cancel and hold |
| Voice state (PTT active / listening / processing) | After-action metrics |

Keep the center clear. Use MIL-STD-2525 frames: friendly is a blue rectangle, hostile a red diamond, unknown a yellow quatrefoil. **Every AI detection is drawn and published as UNKNOWN, and only a human can change affiliation.** This is the most important credibility and ethics rule in the system. The v0 wireframe's "amber diamonds" imply hostile (a diamond means hostile), so I recommend switching contacts to unknown/yellow framing.

### 1.2 Voice command vocabulary (Phase 0 grammar)
`<ASSET> <VERB> <LOCATION> [<MODIFIER>]`, then read-back, then `CONFIRM` or `CANCEL`.

- **Assets:** "Drone one", "Drone two". Defer "All drones" to Phase 1, except as `ALL DRONES HOLD` (see Open Questions).
- **Verbs (6):** `SCOUT` (fly to a point and run a scan pattern), `ORBIT` (circle a point), `OVERWATCH` (hold a standoff and keep the sensor on a point or on "me"), `HOLD` (stop and hover), `RETURN` (fly home), `FOLLOW` (follow me at an offset).
- **Locations (5 forms):**
  - "my position"
  - clock direction plus distance: "two o'clock, four hundred". Clock is relative to the wearer's heading at the moment of PTT release, and distance is in meters.
  - MGRS: pre-load the grid zone and 100 km square of the operating area (Philadelphia, for example, is 18S), so operators speak only 8–10 digits.
  - named control measures: "checkpoint three", "NAI two", "phase line blue"
  - contact references: "track one", "the vehicle"
- **Modifiers:** "radius two hundred", "altitude one hundred" (units are an open question; read them back explicitly).
- **Alert responses:** `TRACK`, `MARK`, `DISMISS`, `SAY AGAIN` (repeat the alert), `DETAILS` (push the full card to the phone).
- **Control:** `CONFIRM`, `CANCEL`. The ASR must handle radio-style numbers ("niner", "fife", "tree").

**Read-back and confirmation**, e.g. "Drone two, orbit grid one-two-three-four, five-six-seven-eight, radius two hundred. Confirm?"
- The word is `CONFIRM`, never "yes" or "okay", which people say constantly.
- It counts only if spoken **after** the read-back, within 6 s, bound to a displayed command ID. A timeout cancels.
- Grids are read back digit by digit, with a target pin shown on the HUD.
- The read-back states the *parsed* command, not the raw utterance. That is how misrecognitions get caught.
- An unknown verb (e.g. "attack", "engage") gets "Unsupported command", and nothing is sent.

**Push-to-talk, not hot mic.** A hot mic would turn radio traffic and other people's speech into commands. Use temple touch, the ring or a companion button as PTT; a wake word can wait for Phase 1.

### 1.3 ATAK/TAK integration (Phase 0: show our drones and detections on a real TAK client)

**CoT event essentials.** Required attributes are `version="2.0"`, `uid`, `type`, `how`, and `time`/`start`/`stale` as ISO-8601 UTC. Stale defaults to about 60 s. `point` carries `lat`/`lon` (WGS-84), `hae` in meters, and `ce`/`le` as 95% horizontal and vertical error. Useful `detail` children are `contact@callsign`, `__group@name/role`, `track@course/speed`, `remarks` and `takv` ([FTS CoT docs](https://www.mintlify.com/FreeTAKTeam/FreeTakServer/concepts/cot-messages)). Type strings follow `a-<affiliation>-<dimension>-<2525 function>`, where affiliation is f/h/u/n/s and dimension is A/G/S/U/P ([FTS MIL-STD-2525 mapping](https://freetakteam.github.io/FreeTAKServer-User-Docs/About/architecture/mil_std_2525/)).

**Proposed type mapping:**

| Entity | CoT type | how | stale |
|---|---|---|---|
| Teammate PLI | `a-f-G-U-C` (by far the most common type on public TAK servers, ~68% of traffic: [gist](https://gist.github.com/a-f-G-U-C/77fed4e7aea38e27f3c50583e840a35b)) | `m-g` | 2–5 min |
| Our quadcopter | `a-f-A-M-H-Q` (military rotary-wing UAV; `a-f-A-M-F-Q` for fixed-wing) ([cottak types](https://docs.rs/crate/cottak/0.1.1/source/src/cot_types.rs)) | `m-g` | 30 s |
| AI-detected vehicle | `a-u-G-E-V` (unknown ground vehicle) | machine-derived (exact code UNVERIFIED) | 5 min |
| AI-detected person | `a-u-G` with remarks "PERSON". Never a combat-unit type. | same | 5 min |
| Unknown air (drone sighting) | `a-u-A` | same | 2 min |
| Human-marked contact | as marked by the operator | `h-e` | 15 min |
| Camera footprint / where the drone is looking | `b-m-p-s-p-i` (SPI) ([Haivision SPI](https://doc.haivision.com/MakitoXEnc/2.6/sensor-point-of-interest-spi-message)) | `m-g` | 10 s |
| NAI / checkpoint | `b-m-p-w` (waypoint, UNVERIFIED in sources fetched) | `h-e` | long |

- `remarks` carries "Flagged by D2 · conf 0.81 · unconfirmed". Link each detection to its drone (`link` with the parent UID).
- `ce` must honestly reflect geolocation error; ground-plane projection from a drone is easily 20–50 m off. Use `le=9999999` (the usual "unknown" convention) when height is unknown.
- Drone camera FOV (`sensor` fov/azimuth/range) and a `__video` feed URL are attractive, but how ATAK-CIV renders them is **UNVERIFIED**. Test in week 1.
- **Never emit `a-h-*` automatically.**

**Transport:**
- *Mesh SA:* UDP multicast **239.2.3.1:6969**. No server needed: TAK clients on the same LAN see the traffic automatically ([AryaOS ports](https://aryaos.readthedocs.io/en/latest/reference/ports/), [Hydris ATAK](https://projectqai.github.io/docs/integration/atak)).
- *TAK server:* streaming CoT over **TCP 8087** (plaintext) and **TLS 8089** ([FTS services](https://www.mintlify.com/FreeTAKTeam/FreeTakServer/configuration/services), [LearnATAK](https://toyon.github.io/LearnATAK/docs/setup/server)).
- *Library:* **PyTAK** (Apache-2.0) speaks TCP, TLS, UDP multicast and WebSockets ([PyTAK docs](https://pytak.readthedocs.io/en/latest/)). Use it rather than hand-rolling sockets.
- Send XML CoT. Whether ATAK-CIV accepts XML on mesh SA by default or expects TAK protobuf is UNVERIFIED; check in week 1.

**Server choice:**
1. **Demo default: no server.** Publish mesh SA multicast on the demo Wi-Fi, with an ATAK-CIV phone plus a "TOC" laptop. It has zero infrastructure to break.
2. **OpenTAKServer** on a team Ubuntu laptop or Raspberry Pi, for TLS, a web map and **drone video through MediaMTX** (viewable in ATAK, a browser or VLC). It has installer scripts for Ubuntu and RPi and needs Python ≥3.10, RabbitMQ and OpenSSL ([OTS docs](https://docs.opentakserver.io/)). Ports: 8089 SSL CoT, 8080 web UI, 8446 certificate enrollment (per a [community guide](https://hamradio.my/self-host-opentakserver-docker-tak-server/); verify).
3. **FreeTAKServer** as the fallback: `pip install FreeTAKServer[ui]`, with Ubuntu 22.04 the primary supported OS ([FTS install](https://freetakteam.github.io/FreeTAKServer-User-Docs/Installation/Linux/Installation/)). It is easiest to stand up for plain TCP 8087, but its docs are inconsistent about port defaults.

**Clients:** ATAK-CIV is free on Google Play and classed EAR99 ([CivTAK](https://civtak.org/download-atak)); iTAK runs on iOS; WinTAK-CIV comes from tak.gov, which is limited to US IPs (whether an account is needed is UNVERIFIED). The deptofdefense ATAK-CIV repo was **archived May 2, 2025**; current SDKs live on tak.gov ([repo](https://github.com/deptofdefense/AndroidTacticalAssaultKit-CIV)). Phase 0 needs **no ATAK plugin**, only CoT in and out.

### 1.4 Demo vignette (about 7 min, simulated)
**Setting:** fictional rural terrain built from public elevation and OSM data. It has a road junction (NAI 1), a farm compound (NAI 2), a ridge, and a checkpoint. Do not model a real installation.

**Team:** 4-person recon element, callsigns RAVEN 1–4. The wearer is RAVEN 1. Two quadcopters, D1 and D2. A TOC laptop runs WinTAK or the OTS web map; one ATAK-CIV phone.

| Time | Event | Goal exercised |
|---|---|---|
| 0:00 | Team at the checkpoint. HUD shows teammates, both drones (STANDBY) and compass. TOC sees all PLI. | 3 |
| 0:30 | "Drone one, scout NAI one" → read-back → `CONFIRM`. D1 transits; its inset appears. | 1 |
| 1:15 | "Drone two, overwatch my position, radius one-fifty" → `CONFIRM`. | 1 |
| 2:00 | A vehicle arrives at NAI 1. Detector flags it. HUD: "VEHICLE · 2 o'clock · ~400 m · D1 · track / dismiss". `TRACK` keeps it under observation; `MARK` makes it appear on ATAK as an unknown vehicle. | 2, 3 |
| 3:00 | Two persons appear near the compound, plus a deer flagged as a person (a planted false positive). The operator `MARK`s the real persons and `DISMISS`es the deer. Alerts queue by rank, one at a time. | 2, 3 |
| 4:00 | **Jamming.** D2 link drops: HUD greys the chip, "D2 LINK LOST · holding · 0:20". D2 runs lost-link behavior (hold, then return home). TOC backhaul drops and CoT queues on the companion; voice and detection keep working on-device. | 3 + offline |
| 5:00 | A misrecognized grid in the read-back is caught: `CANCEL`, then reissued. "Drone one, attack…" gets "Unsupported command". | 1, safety |
| 5:45 | Link restored. Queued events reach the TOC carrying their original `time` stamps. "Drone two, return" → `CONFIRM`. | offline sync |
| 6:30 | After-action on the phone: video minutes recorded vs seconds the operator had to watch, command-to-execution latency, false alerts dismissed. | 2, 4 |

For dual-use credibility, also script a **"missing hiker" SAR re-skin** of the same mission.

### 1.5 Operator interview plan (target 15–25 by week 8 of S2; H4D-style)
**Who to reach:**
- **Penn NROTC**, on campus, including Marine-option midshipmen and cadre ([Penn NROTC](https://nrotc.universitylife.upenn.edu/about/)).
- **Army ROTC**, hosted at Drexel ([Penn Today, 2012; re-verify](https://penntoday.upenn.edu/2012-01-19/ask-benny/there-rotc-program-university), [Drexel ROTC](https://drexel.edu/provost/offices/undergrad-education/rotc)).
- **Wharton Veterans Club** ([link](https://groups.wharton.upenn.edu/Veterans/)): ex-infantry, SOF and aviation MBAs. **Highest-yield channel.**
- **Wharton Aerospace & Defense Club** ([link](https://groups.wharton.upenn.edu/ADC)) for the buyer view; **Drone Club at Penn** ([DP](https://www.thedp.com/article/2023/11/penn-drone-club-newly-founded-students-technology)) for piloting realism; **Penn Carey Law National Security Society** for ethics review; local fire and SAR teams for dual use.

**H4D:** I found **no Penn H4D course** on upenn.edu. The university H4D program moved from NSIN to **DIU** ([NSIN redirect](https://www.nsin.mil/hacking-for-defense); [DIU educator forum, Jan 2027](https://www.commonmission.us/h4d-diu)). Columbia and Pitt run it nearby. Ask Prof. Zhao whether Penn would host it.

**Protocol:** about 30 min each, unclassified only (no TTPs, unit specifics or CUI), personal capacity, consent before recording. Ask Penn IRB whether the S2 user study needs a determination.

**Questions:**
- Elicit natural phrasing **before** showing our grammar: "Tell your drone to watch that road."
- Walk me through the last time you tasked a drone. How did the picture reach you?
- When do you look down at ATAK, and when *can't* you? When is speaking unacceptable? What is your PTT habit?
- How many false alerts per hour before you'd ignore the system?
- What would make you take the glasses off (eye-pro fit, NVG, night brightness, weight)?
- What must never be automated? What would make your S6 or commander reject it?

**What to show:** the 640×480 HUD emulator running the vignette, two HUD variants for A/B comparison, and a Wizard-of-Oz voice session.

### 1.6 Credibility and buyer path
- **DIU** reorganized in July 2026 into three portfolios: drones & autonomous warfare, kill webs, and "10x" ([DefenseScoop](https://defensescoop.com/?p=129528)). Pitch E.D.I.T.H. as the operator interface for drones, **never as a kill-web component**. DIU buys via Commercial Solutions Openings and OT agreements, often in 60–90 days ([DIU](https://www.diu.mil/work-with-us/open-solicitations)).
- **SOFWERX/SOCOM UxSAI** events ask for modular architecture, an ICD, SWaP-C, comms-denied operation and government-sustainable open capability ([CV AE 2025](https://soldiersystems.net/2025/09/29/sofwerx-computer-vision-cv-inference-engine-and-model-training-for-unmanned-systems-ums-assessment-event-ae/), [Autonomy AE 2026](https://soldiersystems.net/2026/08/21/sofwerx-uxsai-mission-autonomy-systems-assessment-event/)). Some event documents are ITAR-restricted; read only the public notices.
- **Army xTech|Search 10** (open topic, US small businesses, prizes up to $1M plus SBIR Phase I) closed Oct 19, 2026 ([army.mil](https://www.army.mil/article/295227)). Target the next cycle if a company forms.
- **SBIR/STTR** was reauthorized Apr 13, 2026 through 2031, with **foreign-ties screening** ([Crowell](https://www.crowell.com/en/insights/client-alerts/sbirsttr-programs-reauthorized-after-six-month-lapse)). The RayNeo (TCL) prototype is fine; keep the software hardware-portable and the cap table clean.
- **Drones:** Blue UAS moved to DCMA on Dec 3, 2025 ([DIU](https://www.diu.mil/latest/dius-blue-uas-list-to-transition-to-dcma)). The American Security Drone Act bars federal funds for covered foreign drones (DJI, Autel) from Dec 22, 2025 ([UAF](https://www.uaf.edu/news/notice-prohibition-on-purchase-use-of-covered-foreign-drones.php)). Simulate PX4/ArduPilot-class autopilots, never DJI SDKs.
- **Buyers want to see:** named operator pull (ideally letters of support), TAK interoperability, DDIL operation (disconnected, intermittent, limited bandwidth), measured SWaP and latency, an honest TRL (Phase 0 simulation ≈ TRL 4), awareness of the cyber/ATO path, an NDAA-compliant supply chain, and a real commercial market.
- **Dual use.** Wildland fire already uses ATAK where there is no connectivity, including sUAS video ([NWCG/CoE deck](https://fsapps.nwcg.gov/nirops/docs/upload/11b_Redacted_ATAK_TFRSAC_Presentation.pdf)). SAR and disaster response follow naturally. Lead with fire and SAR. Treat police as last, and only with no facial recognition, a published retention policy and audit logs.

### 1.7 Legal and ethical guardrails
- **Export control.** Use only open-source and published material. University work generally falls under the fundamental-research exclusion when results are publishable without restriction (EAR 15 CFR 734.8; ITAR 22 CFR 120.34) ([Stony Brook summary](https://www.stonybrook.edu/research-security/export-controls/reference_guides/fre.html)). Accepting CUI, distribution-limited documents, ITAR-marked solicitations or proprietary sponsor data can void it, so don't take any on. Route sponsor agreements through [Penn Export Compliance](https://research.upenn.edu/resource/export-compliance-controls/). ATAK-CIV is EAR99; avoid ATAK-MIL/GOV material.
- **DoDD 3000.09** (reissued Jan 25, 2023) governs autonomous and semi-autonomous *weapon systems*. It excludes unarmed platforms and non-weapon autonomous systems ([summary](https://en.wikipedia.org/wiki/Department_of_Defense_Directive_3000.09); [PDF](https://www.esd.whs.mil/Portals/54/Documents/DD/issuances/dodd/300009p.PDF)). We stay outside it by never adding effects. That means no target-handoff API, no call-for-fire or CAS 9-line formats, no automatic hostile classification, no "engage" verbs and no countermeasure actuation. Also align with the DoD AI Ethical Principles: responsible, equitable, traceable, reliable, governable ([army.mil](https://www.army.mil/article/233690)). "Governable" maps onto confirm, cancel and hold.
- **Privacy.** No facial recognition or re-identification; classes stay coarse. Pennsylvania requires **all-party consent** to record private conversations, and violations are a felony ([RCFP](https://www.rcfp.org/reporters-recording-guide/pennsylvania/)). For campus tests that makes PTT-only audio, no retained raw audio by default and a visible REC indicator mandatory. Record video only of consenting teammates, or use simulation.

## 2. Interfaces and needs from other experts
- **Voice/NLP (Om):** a grammar-constrained parser emitting a typed `Command{asset, verb, location{kind,…}, modifiers, id}`, with niner/fife normalization and an unknown-verb rejection path. Measure false-accept and false-reject separately.
- **HUD (Alisha):** unknown framing for detections, one alert at a time, a confirm banner tied to the command ID, link/stale states, a night-dim palette.
- **ML (Anshuman):** classes person, vehicle, animal, small UAS; calibrated confidence; a `ce` estimate from geolocation; track IDs for "track N".
- **Architecture/sim:** a CoT gateway as the *only* egress, plus a scope guard that whitelists CoT types (no machine `a-h-*`). Simulated drones need lost-link behavior and timestamped store-and-forward.
- **Commercial (Simon):** the §1.6 buyer slide; owns the interview CRM.

## 3. Buildable pre-arrival, and how to verify
1. **CoT schema module and fixtures** for every §1.3 row. *Verify:* golden XML tests, PyTAK round-trip, and a test that machine-sourced events never carry hostile affiliation.
2. **Local TAK loop:** FreeTAKServer (pip) or OpenTAKServer (RabbitMQ from apt, no Docker) in the workspace, with a PyTAK publisher on TCP 8087 and a second subscriber. *Verify:* automated receive assertion. Multicast can't be tested in the cloud; it waits for the LAN in week 1.
3. **Command grammar and read-back generator** with a corpus of 200+ utterances, including noisy and out-of-scope ones. *Verify:* parse accuracy, 100% rejection of out-of-scope verbs, read-back equals the parse.
4. **Confirmation state machine:** timeout, barge-in rejection, command-ID binding. *Verify:* unit tests, including that "confirm" spoken during the read-back is ignored.
5. **Scripted vignette** (§1.4) as a deterministic scenario file driving the sim and HUD emulator. *Verify:* CI replay asserting the timeline and offline-queue flush order.
6. **Clock and MGRS resolver.** *Verify:* tests against known conversions (`mgrs`/`pyproj`).

**Week-1 LAN checks:**
- ATAK-CIV shows our `a-f-A-M-H-Q` and `a-u-G-E-V` symbols over mesh SA.
- Whether SPI, sensor FOV and `__video` render.
- Whether XML vs protobuf matters on mesh.

## 4. Risks and mitigations
| Risk | Mitigation |
|---|---|
| The demo reads as targeting | Unknown-only detections, no effects verbs, a scope guard in code, ethics slide in the deck |
| Accidental command from chatter | PTT; `CONFIRM` only after read-back; 6 s timeout; command ID |
| Misheard grid sends a drone to the wrong place | Digit-by-digit read-back plus map pin; geofence |
| Operators can't speak | Touch backup (companion, temple) |
| False-alert fatigue | Ranked queue; per-class thresholds tuned to an interview-derived alerts-per-hour budget |
| HUD brightness at night compromises light discipline | Night-dim mode; note NVG integration as Phase 2 |
| Chinese-made glasses hurt credibility | Hardware abstraction layer; "trusted hardware in Phase 1" stated up front |
| Interviews pull in CUI/OPSEC detail | Unclassified-only script; Penn export office if in doubt |
| ATAK rendering quirks | Week-1 checks; OTS web map as backup display |

## 5. Open questions (for the lead)
1. **`HOLD` / `ALL DRONES HOLD`.** It is the safe state. Should it keep full confirmation, per the hard constraint, or get a one-word fast confirm? I recommend keeping confirmation but with a 1-tap companion "hold all" that is itself confirmed.
2. **Altitude units.** Meters AGL vs feet AGL (aviation convention). Decide after the first interviews; the read-back always states the unit.
3. Does the brief allow `FOLLOW` (a drone following the operator) in Phase 0, or should it be deferred for sim complexity?
4. Who owns the IRB determination and the interview CRM: Simon or Alisha?
5. Is there budget or time to run OpenTAKServer on a Raspberry Pi as the demo "TOC" box, or do we stay serverless (mesh SA) for the final demo?
