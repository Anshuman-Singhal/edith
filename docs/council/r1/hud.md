# R1 — HUD UX & Human Factors (E.D.I.T.H.)

This document turns wireframe v0 into a buildable 640×480 spec for the RayNeo X3 Pro and sets out how goal 3 will be evaluated. It builds on `architect.md`: the `HudState` schema, alert ranking on the companion, and the shared `hud-core` renderer.

## 1. Recommendations

### 1.1 Display physics → rules

**Geometry**
- The display is 30° diagonal at 640×480 (4:3), which gives **24.2° × 18.3°**, **26.4 px/deg** and **1 px ≈ 2.27′**.
- Vendor sources confirm the canvas and FOV: [RayNeo design spec](https://rayneo.gitbook.io/rayneo-devdoc/x-xi-lie/she-ji-gui-fan) and the [Feishu spec](https://leiniao-ibg.feishu.cn/wiki/TnHLw4vL4iZgFtkPiMZcxWl8nkb).

**Vendor rules we adopt as hard rules** (from the design spec above)
- Safe margin of 30 px left/right and 20 px top/bottom.
- Text no smaller than 16 px.
- Lines at least 2 px wide (1 px lines look jagged).
- No black UI elements, because black renders as transparent.
- Lit-pixel ratio (APL) **≤13% for persistent content** and ≤25% for transient content.
- ≤30 fps, no glow or particle effects.
- Red only for warnings.

**Binocular rendering**
- `BaseMirrorActivity` mirrors one layout to both eyes, and `BindingPair.checkIsLeft` allows per-eye tweaks ([binocular doc](https://rayneo.gitbook.io/rayneo-devdoc/x-xi-lie/android-kai-fa/neng-li-jie-shao/he-mu-chu-li)).
- So we author **one 640×480 canvas** and keep side-by-side (SBS) output only as an adapter fallback. The real pipeline is UNVERIFIED until day 1 on the device.

**Contrast, not color, is the binding constraint**
- On an additive display, contrast = (T·L_bg + L_hud)/(T·L_bg), where T is lens transmission.
- With sunlit concrete at ~7,000 cd/m² behind the lens and the 3,500-nit average output ([Skarredghost](https://skarredghost.com/2025/12/17/rayneo-x3-pro-review/)), contrast is ≈1.5:1. That is right at the 1.4–1.6:1 minimums in [FAA HF guidance](https://hfcc.dot.gov/publications/docs/GeneralGuidance/zz_FAA_GeneralGuidanceDoc_Chapter_02_Section_01.html) and [Cauz et al. 2024](https://link.springer.com/article/10.1007/s10055-024-00949-6).
- Therefore:
  - Use bold, near-white text at generous sizes.
  - **Put no fills behind text.** On an additive display a filled "billboard" brightens the background as well as the text, which lowers contrast. A 15% fill gets A/B tested only as a texture mask.
  - Test a tinted visor or clip-on (UNVERIFIED that one exists).

**Color**
- Outdoors, see-through display colors wash toward the background white: greens drift yellow, blues drift purple ([Gabbard, Swan & Zarger](https://arxiv.org/pdf/1908.09348)).
- Amber vs green is also the red-green colorblind confusion axis (about 8% of males).
- **Rule: monochrome-first.** Shape, position and text carry every meaning; color only reinforces.

| Token | sRGB | Use |
|---|---|---|
| `fg` | `#E8FFE8` | text, tape, map rings (at 40%) |
| `friend` | `#33DDFF` | teammates and own drones (cyan stays bright; pure blue is too dim) |
| `caution` | `#FFB000` | unknowns, cautions |
| `warning` | `#FF3030` | WARNING border and glyph only |
| `ok` | `#44FF66` | voice/link nominal |

The cyan/amber pair sits on the blue–yellow axis, which stays distinguishable for red-green colorblind users.

**Typography**
- Typeface: **B612 Bold** ([Airbus, OFL](https://github.com/polarsys/b612)), designed for cockpit displays. Fallback: HarmonyOS Sans.
- Size floors from [FHWA-RD-98-057](https://www.fhwa.dot.gov/publications/research/safety/98057/ch03.cfm): critical or dynamic text ≥20′, key elements ≥30′, nothing below 16′. Light-on-dark stroke-to-height ratio of 1:8–1:10.

| Role | px | Cap height | Arcmin |
|---|---|---|---|
| Alert headline | 28 | ~20 px | ~45′ |
| Detail / confirm rows | 20 | ~14 px | ~32′ |
| Static labels | 16 | ~11 px | ~26′ |

- Symbol strokes are 3 px for critical elements and 2 px otherwise. The legibility trial in §5 sets the final values.

### 1.2 Reference frames

**Screen-fixed (head-locked)**
- Status strip, voice state, transcript, alert banner, confirmation card, drone inset, mini-map frame.

**Heading-registered (yaw only, from fused IMU/magnetometer heading)**
- Tape contents and bearing carets.
- Heading-up rotation of the map.
- One conformal caret for the active alert, at x = 320 + (bearing − heading)·26.4 in a fixed band at y 232–248. Pitch is ignored. The caret shows only when |Δ| ≤ 11°; otherwise an edge chevron appears at x = 40 or 600.
- The caret is **hidden when head yaw rate exceeds 60°/s**, because at ≤30 fps it would jump more than 50 px per frame.
- **Heading-quality gate:** if heading uncertainty exceeds 10° (for example a magnetometer near a radio or rifle), hide all conformal carets, draw the tape dashed and labeled "HDG ±", and fall back to text ("BRG 075 · 2 o'clock").

**6DoF: not needed in Phase 0**
- Moving the head 1 m sideways changes the direction to a contact 400 m away by only 0.14° (~4 px). 6DoF only matters for objects within about 10 m.
- Native 3DoF is reportedly stable, while 6DoF anchoring was not ([Skarredghost](https://skarredghost.com/2025/12/17/rayneo-x3-pro-review/)).

### 1.3 Layout (origin top-left; safe area x30–610, y20–460)

```
x: 30      190 200              420 440            610
y20 ┌────────┐ ┌──NE──|075|──E──┐  ┌──────────────┐
    │ MINI-  │ │ ▾ ◇    ▾       │  │ DRONE INSET  │
    │  MAP   │ └────────────────┘  │  170×128     │
    │160×160 │                     ├──────────────┤148
 180└────────┘                     │DRONE 2·LIVE·0.4s
 184 LINK● GPS● 62%                └──────────────┘166
 150        ┌──────── CENTER CLEAR ZONE ──────────┐  x170–470
 240  ‹     │  (only conformal caret, y232–248)    │  ›   y150–330
            └──────────────────────────────────────┘
 336   ┌─[▲] VEHICLE · 2 o'clock · 400 m ──────── +2 ▲◆┐ x60–580
       │     DRONE 2 · unknown · 12 s ago                │
 410   └───── say TRACK · DISMISS ───────────────────────┘
 432 ● LISTENING           heard: "drone two scan ridge"
```

| Region | Box (x0,y0–x1,y1) | Spec |
|---|---|---|
| Mini-map | 30,20–190,180 | See §1.4 |
| Status strip | 30,184–190,204 | 16 px: `LINK●` `GPS●` companion battery %, and `DATA 45s` when stale |
| Heading tape | 200,20–420,58 | Compressed (not conformal) ±55° (2 px/°); 10° ticks and cardinals; boxed 3-digit heading. Carets at y46–58: cyan for drones, amber for unknowns, clamped with ◄/► when off-scale |
| Drone inset | 440,20–610,148, plus label to y166 | See §1.4 |
| Center clear zone | 170,150–470,330 (~11°×7°) | Nothing persistent. No reticle (out of scope) |
| Banner / confirm card | 60,336–580,410 (card may grow to y316) | See §1.5 |
| Voice state | 30,432–250,458 | `● LISTENING`, `◌ READY`, `… PROCESSING`, `■ MUTED`, `✕ VOICE OFFLINE`. Each state has a distinct shape |
| Transcript | 260,432–610,458 | 16 px, last recognized utterance, fades after 3 s, so mishearings are visible |

**Changes from v0 and budget**
- The compass moves to top-center, because heading is the primary navigation cue.
- Persistent APL is ≈3%. The inset adds 7.1%, which fits only because it is transient.

### 1.4 Symbology, map, inset

**Symbols (simplified, 2525-like, 10–12 px)**
- Self: `fg` chevron.
- Teammate: cyan filled circle with a heading tick.
- Own drone: cyan "∩" plus its number.
- AI detection: amber **open** diamond with a class letter (P/V/D), always *unknown*. This matches the architect's `a-u-G`.
- Operator-confirmed threat: amber **filled** diamond.
- Stale symbol: dashed, with an age label. Removed after 5 min.

**Mini-map**
- Heading-up circle, radius 76 px. Default range 500 m (6.6 m/px), with rings at 50% and 100%. Voice "map 250 / 1k / 2k" changes range.
- No basemap imagery.
- At most 12 symbols; beyond that, symbols cluster ("◇×4").

**Drone inset**
- 170×128 px (6.4°×4.8°), with 320×240 video at 10–15 fps.
- Shown when:
  - a tasked drone is on station,
  - the operator says "show drone N", or
  - that drone raises the top alert. In that case a 96×72 detection crop is shown.
- Hides 10 s after the last new detection unless pinned.
- **If a frame is more than 1 s old: draw a slash and "FROZEN 3s".** Frozen video must never look live.
- Dark parts of the video vanish on an additive display. Contrast-stretch the video, but do not lift blacks, which would make a glowing rectangle.
- "Drone full" (400×300 px) only on request, dimmed to meet the 25% APL limit, and it auto-collapses on a WARNING.

### 1.5 Alerts and confirmation

**Banner**
- 2 px severity border that flashes at 2 Hz for 2 s, then stays steady. The rate stays ≤3 Hz for photosensitivity.
- The glyph shape also encodes severity: ▲ WARNING, ◆ CAUTION, ⓘ ADVISORY.
- Row 1 (28 px, ≤28 characters): class · clock position · range. The clock position is relative to current head yaw and updates live.
- Row 2 (20 px): source, affiliation, age, and `BRG`.
- Row 3: `say TRACK · DISMISS`.
- Queue indicator `+N` with one pip per severity.

**Ranking (computed on the companion; rules shared in config)**
- Severity class wins outright: WARNING > CAUTION > ADVISORY.
- Within a class, score = 0.4·proximity + 0.25·closing + 0.15·recency + 0.15·novelty + 0.05·confidence, where:
  - proximity = 1 − min(r/1 km, 1)
  - recency = e^(−age/30 s)
  - novelty = 1 for a new track, 0.3 for a re-alert
- **Pre-emption:**
  - A higher class takes over immediately.
  - Within the same class, a new alert takes over only if its score is ≥0.2 higher *and* the current alert has been shown for at least 3 s. This prevents flicker.
- **Dismissal and expiry:**
  - A dismissed track stays suppressed for 60 s unless it escalates in class or its range closes by ≥30%.
  - Advisories expire after 30 s, cautions after 120 s.
- **Flood control:** more than 3 alerts of the same class within 10 s collapse into one ("3 UNKNOWN · NE · 300–600 m").

**Confirmation card (replaces the banner in the same place)**
```
CONFIRM TASK                        ████████░░ 10s
DRONE 2 → SEARCH AREA "NORTH RIDGE"
ALT 60 m · RADIUS 150 m · ETA 2 min
say CONFIRM / CANCEL        (2-finger hold = confirm)
```
- The card is rendered from the structured `CommandProposal`, never from the raw transcript.
- **After 10 s it auto-cancels ("NOT SENT — timed out"). It never auto-confirms.**
- After confirm it shows `SENT`, then `ACK DRONE 2`, or `NO ACK — link` in amber after 3 s.
- **Safeguards:**
  - Confirm is locked out for 0.6 s after the card appears.
  - "Confirm" counts only as the whole utterance and only above the ASR confidence threshold.
  - Anything ambiguous counts as cancel.
  - A WARNING that arrives mid-confirm cancels the proposal and prompts the operator to re-issue it.
- **Vocabulary risk:** "confirm" and "cancel" both start with /k/ + vowel + /n/, so they may be confused in noise. Measure the confusion rate. If it is too high, switch to CONFIRM / NEGATIVE.

### 1.6 Modes

**Day**
- Full palette.
- Brightness follows the ambient light sensor if one exists (UNVERIFIED); otherwise voice "brighter".

**Night / light discipline**
- Monochrome **dim NVIS-type green (~530 nm), not red**, capped at the lowest readable luminance. The target is below 5 cd/m², to be measured.
- APL ≤3%: inset only on request, map rings off.
- Why not red: red helps preserve the wearer's dark adaptation, but image intensifiers are most sensitive in red and near-infrared, and Class A NVIS "is not compatible with red" lighting ([MIL-STD-3009](https://cdn.shopify.com/s/files/1/1942/0217/files/MIL-STD-3009.pdf)). A red "dark-adapt" variant is an option only.
- This addresses the IVAS report that the display glow was "visible from hundreds of meters away" ([TechSpot/Insider](https://www.techspot.com/news/96304-army-tester-warns-microsoft-hololens-based-ar-goggles.html)). Reviewers already notice the X3 Pro's light in the dark, so forward light leakage must be measured.

**Quiet** (independent of night mode)
- No earcons or TTS.
- Voice is push-to-talk only, because whispered ASR is unreliable.
- Touch is the primary way to confirm.

**Degraded**
- **Never show stale data as current.** A symbol goes dashed after 30 s and shows "last known 2m" after 120 s. The status strip shows `DATA 45s`.
- Companion lost: amber "COMPANION LOST — LOCAL ONLY". The tape stays live and the map greys out after 3 s.
- Voice service lost: `✕ VOICE OFFLINE`, and touch takes over.

**Declutter**
- Voice "declutter" cycles FULL → MIN (tape, banner, voice) → WARNINGS-ONLY.

### 1.7 Hands-free input and fallback

Voice is primary, gated by push-to-talk (PTT) or a wake word. Right-temple gestures come from the [touchpad API](https://rayneo.gitbook.io/rayneo-devdoc/x-xi-lie/android-kai-fa/neng-li-jie-shao/chu-kong-ban-guan-li). Reviewers found the pads "too sensitive" and prone to firing when users adjust the frame, so **no single gesture can command an asset.**

| Gesture | Action |
|---|---|
| Tap | Show the queue (harmless) |
| Swipe forward/back | Next/previous alert |
| Double-tap | DISMISS / CANCEL (the safe direction) |
| Long-press 1 s | PTT. This must override the system quick panel (UNVERIFIED) |
| **Two-finger hold ≥1 s with a progress ring** (X3 only) | Touch CONFIRM, valid only while a confirmation card is open |

- The left temple stays reserved for the system. If its assistant long-press cannot be suppressed (UNVERIFIED), document it as a known conflict.
- The ring mirrors the right temple, and the companion touchscreen is the full fallback.
- Input is suspended when the glasses are off-head (wear detection). Touches within 300 ms of a wear-state change are ignored.

## 2. Interfaces/needs from other experts

- **Architect:** add to `HudState`: `alert.queue{count,by_severity}`, `alert.shown_since_ms`, `entities[].age_ms`, `style∈{self,friend,unknown,threat}`, `operator.heading_unc_deg`, `mode`, `proposal.rows[]`, `proposal.lockout_ms`, `execution.status`, `inset.frame_age_ms`, `inset.crop_bbox`, and the `voice.state` enum.
- **Voice (Om):** a confirm/cancel confusion matrix at 75–85 dBA, the confidence threshold, a PTT vs wake-word decision, and a canonical readback generator.
- **Vision/ML (Anshuman):** P/V/D classes with confidence, a stable `track_id` (needed for novelty), `ce_m` so range is rounded to the location error ("~400 m"), a detection crop per alert, and an expected alert rate (target ≤2/min).
- **Hardware (Arjun), day-1 measurements:** per-eye pipeline; minimum and maximum luminance; ambient light sensor; magnetometer and heading error near radios; whether long-press and two-finger gestures can be intercepted; wear detection; fps and thermals with the inset on; forward light leakage in the dark at 1, 5 and 10 m.
- **Systems (Simon):** the ATAK-CIV baseline on a chest-mounted phone fed from our CoT multicast, and participant pay (~18 × $20).
- **Product/HUD (Alisha):** owns the symbol set, Figma and recruitment. This document is her starting spec.

## 3. Pre-arrival build and verification

**Emulator** (`glasses/emulator-desktop`, same `hud-core`)

- **Views:** 640×480 at ×2 nearest-neighbor; a **true-angular** view scaled to 24.2° at a measured eye distance (25.7 cm wide at 60 cm); optional side-by-side 1280×480.
- **See-through:** out = clamp(T·bg + k·hud), no alpha, with sliders for T, k and ambient. Clips: sunlit pavement, sky, foliage, snow, dusk, night.
- **Registration:** a 360° equirectangular background cropped to 24°×18° by simulated yaw (mouse or replayed IMU log).
- **Lints:** live APL meter (warns at 13%/25%), stroke ≥2 px, text ≥16 px, Machado colorblindness simulation.
- **Inputs:** keys → `TempleAction`, typed text or mic for voice, and a scripted scenario player with event logging.

**Golden PNGs** (pixel-diffed in CI) for every alert class, confirm/timeout, mode, stale/frozen state and heading fallback. **Ranker property tests** (Hypothesis) for dwell, suppression, flood collapse and WARNING-cancels-proposal.

**Optional see-through rig:** a laptop under a 45° teleprompter or acrylic beam-splitter, viewed outdoors. It costs about $30 and gives a real additive look in daylight.

**Emulator pilot** with 3–5 people on legibility and the confirm flow.

**Gate:** all golden states render and the lints pass.

## 4. Risks + mitigations

| Risk | Mitigation |
|---|---|
| Daylight washout (~1.5:1) | Bold large text, no fills, visor test, sunlight legibility trial |
| Heading error/drift | Uncertainty gate, text-bearing fallback |
| Color meaning lost | Monochrome-first shape coding; Ishihara as covariate |
| Attention tunneling | Clear center, one banner, peripheral-detection measure |
| Accidental confirmation | Lockout, deliberate touch, auto-cancel, lure trials |
| Night light signature | Dim green, APL ≤3%, leakage measurement |
| Battery/thermal from inset | On-demand, crops over video |
| Sickness (IVAS: eyestrain, headaches, nausea — [DOT&E FY22](https://www.dote.osd.mil/Portals/97/pub/reports/FY2022/army/2022ivas.pdf)) | Head-locked UI, SSQ |
| SDK unknowns / IRB delay | `DisplayAdapter` + day-1 APK; submit IRB by Jan 15 |

## 5. Evaluation plan (goal 3) and open questions

**Design**
- Within-subjects and counterbalanced.
- Conditions: **HUD glasses** vs **ATAK-CIV on a chest-mounted phone**, both driven by the same CoT scenario.
- Optional ablation: ranked alerts vs all alerts.
- **N = 18 students.** A paired design with d = 0.7 and 80% power needs about 18.
- Plus 3–5 subject-matter-expert think-alouds (ROTC or veterans; availability UNVERIFIED).

**Protocol**
- Participants walk a marked indoor or Penn Park loop during a 10-minute scripted scenario.
- Stressors: an auditory call-sign secondary task (dual-task), 75–80 dBA noise, time pressure, and a dusk block.
- Tasks:
  - respond to alerts
  - navigate to bearings
  - issue 4 confirmed drone tasks
  - call out peripheral LED events (an attention-tunneling probe)
- **Lure trials:** "confirm" and "cancel" spoken by the secondary-task script or by a confederate while a card is open.

**Measures**
- Response time from alert onset to correct action, plus hits, misses and wrong actions.
- **SAGAT:** 3 blanked freezes per run, with level 1–3 queries scored against sim ground truth.
- **SART**, **raw NASA-TLX**, SUS and SSQ after each run.
- Heads-up time from glasses IMU pitch (worn in both conditions).
- Walking speed and peripheral detection rate.
- Accidental confirmations.
- Banner legibility within 2 s.

**Success criteria (pre-registered)**
- Alert response time ≥20% faster than ATAK.
- SAGAT non-inferior within 5 points.
- TLX no higher.
- Peripheral detection non-inferior.
- **0 accidental confirmations in ≥180 lures** (rule-of-three upper bound 1.7%).
- Legibility ≥95%.

**Analysis**
- Mixed model on response time; Wilcoxon tests on questionnaires; effect sizes with 95% CIs.
- Exclude photosensitive epilepsy; record acuity and color vision.

**IRB**
- At Penn, even exempt studies need a protocol submission, and investigators cannot decide exemption themselves ([Pennbook](https://catalog.upenn.edu/pennbook/human-subject-research/)).
- Likely **Exempt Category 3** (benign behavioral intervention, 45 CFR 46.104(d)(3)). Walking plus noise could push it to expedited review. Verify with Penn's IRB office.
- Faculty PI (Mingmin Zhao) likely required (UNVERIFIED), and CITI training for all.
- Submit by about Jan 15 so approval lands before semester-2 week 8.
- Recruit cadets and veterans as civilians, not on-duty personnel.

**Open questions**
1. Is the output mirrored or side-by-side, and is there a virtual-image distance or convergence offset?
2. What is the minimum luminance, and is there an ambient light sensor?
3. Is there a magnetometer, and how large is the heading error near radios?
4. Can long-press, left-temple and two-finger gestures be intercepted?
5. Should clock positions be relative to head, body, or direction of travel? (Recommend head; needs SME input.)
6. What is the final confirm vocabulary?
7. Is an MGRS readout ("say grid") needed in Phase 0?
8. Does the demo need expanded drone video, or are crops enough?
