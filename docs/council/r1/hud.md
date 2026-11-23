# R1 — HUD UX & Human Factors (E.D.I.T.H.)

Author: HUD/HF expert. Scope: turn wireframe v0 into a buildable 640×480 spec for RayNeo X3 Pro, plus the evaluation method for goal 3. Builds on `architect.md` (`HudState`, companion-side ranking, shared `hud-core` renderer).

## 1. Recommendations

### 1.1 Display physics → design rules

**Geometry.** The display is 30° diagonal at 640×480 (4:3), which works out to about **24.2° × 18.3°**, roughly **26.4 px/deg**, so **1 px ≈ 2.27 arcmin**. All numbers below follow from this. The vendor spec agrees on the 640×480 canvas and the 30° FOV ([RayNeo design spec](https://rayneo.gitbook.io/rayneo-devdoc/x-xi-lie/she-ji-gui-fan), [Feishu spec](https://leiniao-ibg.feishu.cn/wiki/TnHLw4vL4iZgFtkPiMZcxWl8nkb)).

**Vendor constraints we adopt as hard rules** ([RayNeo design spec](https://rayneo.gitbook.io/rayneo-devdoc/x-xi-lie/she-ji-gui-fan)):
- Safe margin is 30 px left/right and 20 px top/bottom.
- Minimum text is 16 px.
- Lines are at least 2 px. 1 px lines break up on the waveguide.
- Black is transparent, so there are no black UI elements.
- Lit-pixel ratio (APL) stays **≤13% for persistent content** and ≤25% for transient content. Full-screen white is banned.
- Keep the frame rate ≤30 fps and avoid glow and particle effects.
- Red is reserved for warnings.

**Binocular.** The Android SDK's `BaseMirrorActivity` maps one layout to both eyes, with optional per-eye tweaks through `BindingPair.checkIsLeft` ([binocular handling](https://rayneo.gitbook.io/rayneo-devdoc/x-xi-lie/android-kai-fa/neng-li-jie-shao/he-mu-chu-li)). We therefore author **one 640×480 canvas**, and SBS output exists only as an adapter fallback. Whether the final composited output is 1280×480 is still UNVERIFIED and must be checked on day 1.

**Contrast is the binding constraint, not color.** Each HUD pixel only adds light to the scene behind it, so contrast = (T·L_bg + L_hud)/(T·L_bg).
- Take sunlit concrete at about 7,000 cd/m² after the lens, and the specified 3,500-nit average output ([Skarredghost](https://skarredghost.com/2025/12/17/rayneo-x3-pro-review/)). That gives a contrast of about 1.5:1. This is right at the ~1.4–1.6:1 minimums in the literature ([FAA HF guide / McAnulty](https://hfcc.dot.gov/publications/docs/GeneralGuidance/zz_FAA_GeneralGuidanceDoc_Chapter_02_Section_01.html); Blanc-Goldhammer & MacKenzie in [Cauz et al. 2024](https://link.springer.com/article/10.1007/s10055-024-00949-6)). Treat bright sky, snow and sunlit walls as worst cases.
- Consequences:
  - Use bold glyphs, near-white luminous text and generous sizes.
  - Use **no dim fills** behind text. On an additive display a "billboard" adds luminance to the background as well as to the text, so it lowers contrast. We A/B test a 15% fill only as a texture-masking option.
  - Test a tinted clip-on or visor. Its availability is UNVERIFIED.

**Color.**
- Outdoors, OST colors collapse toward the background white point: greens drift to yellow and blues to purple ([Gabbard, Swan & Zarger](https://arxiv.org/pdf/1908.09348)). Amber vs green is also the deutan/protan confusion axis (~8% of males).
- Rule: **design monochrome-first**. Shape, position and text carry every meaning, and color is only redundant reinforcement. Night mode is monochrome anyway.
- Day palette (sRGB tokens):

| Token | Value | Use |
|---|---|---|
| `fg` | `#E8FFE8` | Default text, tape, rings at 40% |
| `friend` | `#33DDFF` | Cyan: teammates and own drones. Blue-green channels keep it bright; pure blue is too dim. |
| `caution` | `#FFB000` | Amber: unknowns and cautions |
| `warning` | `#FF3030` | Red: only the WARNING banner border and glyph |
| `ok` | `#44FF66` | Voice and link nominal |

The main contrast pair is cyan vs amber, which lies on the blue–yellow axis that survives red-green color-vision deficiency.

**Typography.**
- Typeface: **B612 Bold** ([Airbus/PolarSys, OFL](https://github.com/polarsys/b612)), which was designed for cockpit displays. The fallback is the system HarmonyOS Sans.
- Size floors from FHWA symbol-height guidance ([FHWA-RD-98-057](https://www.fhwa.dot.gov/publications/research/safety/98057/ch03.cfm)): dynamic or critical text ≥20′, key elements ≥30′, never <16′. Stroke:height should be 1:8–1:10 for light-on-dark text.

| Role | Font px | Cap height | Angular |
|---|---|---|---|
| Alert headline | 28 | ~20 px | ~45′ |
| Alert detail / confirm rows | 20 | ~14 px | ~32′ |
| Static labels (range, status) | 16 | ~11 px | ~26′ |

- Strokes: symbols use 3 px strokes when critical and 2 px otherwise.
- These sizes are tunable. The legibility trial in §1.7 sets the final values.

### 1.2 Reference frames

| Frame | Elements |
|---|---|
| **Screen-fixed (0DoF)** | Status strip, voice state, transcript, alert banner, confirmation card, drone inset, mini-map frame |
| **Heading-registered (yaw only, from fused heading)** | Heading-tape content, bearing carets on the tape, heading-up map rotation, one conformal caret for the active alert, edge arrows for off-FOV contacts |
| **6DoF** | **Not needed in Phase 0** |

**Why 6DoF is not needed.** Contacts are hundreds of meters away. A 1 m head translation against a 400 m target shifts its direction by only 0.14° (~4 px). 6DoF matters only for objects closer than ~10 m. Native 3DoF is reportedly stable, while 6DoF anchoring was not ([Skarredghost](https://skarredghost.com/2025/12/17/rayneo-x3-pro-review/)).

**Conformal caret.**
- Placement: x = 320 + (bearing − heading)·26.4 px, on a fixed band at y 232–248. Pitch is ignored on purpose.
- The caret appears only when |Δ| ≤ 11°. Otherwise an edge chevron is drawn at x=40 or x=600.
- **Hide the caret while head yaw rate exceeds 60°/s.** At ≤30 fps it would jump more than 50 px per frame.
- **Heading-quality gate:** if fused heading uncertainty is above 10° (magnetometer near a radio, rifle or vehicle), hide all conformal carets, draw the tape dashed with "HDG ±", and fall back to text ("BRG 075 · 2 o'clock").

### 1.3 Layout at 640×480 (origin top-left; safe area x30–610, y20–460)

```
x: 30      190 200              420 440            610
y20 ┌────────┐ ┌──NE──|075|──E──┐  ┌──────────────┐
    │ MINI-  │ │ ▾ ◇    ▾       │  │ DRONE INSET  │
    │  MAP   │ └────────────────┘  │  170×128     │
    │160×160 │                     ├──────────────┤148
    │        │                     │DRONE 2·LIVE·0.4s
 180└────────┘                     └──────────────┘166
 184 LINK● GPS● 62%
     (status strip)
 150        ┌───────── CENTER CLEAR ZONE ─────────┐   x170–470
            │      (only conformal caret ◇,        │   y150–330
 240  ‹     │        y-band 232–248)               │     ›  edge chevrons
            └──────────────────────────────────────┘
 336   ┌──[▲]  VEHICLE · 2 o'clock · 400 m ─────── +2 ▲◆┐ x60–580
       │       DRONE 2 · unknown · 12 s ago              │
 410   └──────  say TRACK  ·  DISMISS  ───────────────────┘
 432 ● LISTENING          heard: "drone two scan ridge"
 460 (x30–250)            (x260–610, fades 3 s)
```

| Region | px box | Spec |
|---|---|---|
| Mini-map | 30,20–190,180 | See §1.4 |
| Status strip | 30,184–190,204 | 16 px: `LINK●` `GPS●` companion battery %, then `DATA 45s` once stale |
| Heading tape | 200,20–420,58 | Compressed (not conformal), ±55° over 220 px (2 px/°). Ticks every 10°, cardinals, boxed 3-digit heading at center. Bearing carets at y46–58: cyan drones, amber unknowns. Out-of-range carets clamp to the ends with ◄/►. |
| Drone inset | 440,20–610,148, label 148–166 | See §1.4 |
| Center clear zone | 170,150–470,330 (~11°×7°) | Nothing persistent. No reticle (out of scope). |
| Alert banner / confirm card | 60,336–580,410 (card may grow up to y316) | See §1.5 |
| Voice state | 30,432–250,458 | `● LISTENING` (ok green), `◌ READY`, `… PROCESSING`, `■ MUTED`, `✕ VOICE OFFLINE` (amber). Shape differs per state. |
| Transcript | 260,432–610,458 | 16 px: the last recognized utterance, fades after 3 s, so mis-hearings are visible |

**Deviation from v0:** the compass moves to top-center. Heading is the primary navigation cue and should sit near the line of sight, and this also frees the top-right for the inset.

**APL budget** (persistent ≤13% ≈ 40k px): map, tape and text together come to about 3%, and the inset is 7.1%. That stays under budget only because the inset is transient.

### 1.4 Symbology, map, inset

**Simplified 2525-like symbols** (10–12 px, ≥23′). Shape encodes affiliation and fill encodes confirmation:
- Self: `fg` chevron at map center.
- Teammate: cyan filled circle with a 4 px heading tick.
- Own drone: cyan "∩" arc (2525 air-friendly) with its digit.
- AI detection: **amber open diamond with a class letter (P/V/D)**. This is always *unknown* ([architect](./architect.md) types detections `a-u-G`).
- Operator-confirmed threat: amber **filled** diamond.
- Stale track: dashed outline with an age label. After 5 minutes it is removed.

**Mini-map.**
- Heading-up, circular, radius 76 px.
- Default range **500 m** (6.6 m/px), with rings at 50% and 100% drawn in `fg` at 40%. Voice "map 250 / 1k / 2k" changes the range.
- No basemap imagery (APL, clutter).
- Maximum 12 symbols. Above that, clusters are drawn as "◇×4".

**Drone inset.**
- Size 170×128 (6.4°×4.8°), video 320×240 at 10–15 fps per the architect.
- It appears (a) when a tasked drone is on station, (b) when the operator says "show drone N", or (c) with a **detection crop** (96×72, bracketed) when that drone raises the top alert.
- It auto-hides 10 s after the last new detection unless pinned ("pin drone 2").
- **Frozen-video guard:** if the frame age exceeds 1 s, the inset shows a slash and "FROZEN 3s". Frozen video must never look live.
- Dark video regions disappear on an additive display, so apply a contrast stretch (no black lift, because that would create a glowing rectangle).
- Expanded mode ("drone full") is 400×300 centered. It is allowed only on request, it is dimmed to meet the 25% APL limit, and it auto-collapses when a WARNING arrives.

### 1.5 Alerts and confirmation

**Banner.**
- Border 2 px, colored by severity, flashing at 2 Hz for 2 s on onset and then steady (≤3 Hz for photosensitivity).
- A left glyph shows severity by shape as well as color: ▲ WARNING, ◆ CAUTION, ⓘ ADVISORY.
- Row 1 (28 px): class · clock · range, at most 28 characters. The clock is relative to the *current head yaw* and updates live, with an absolute `BRG` available in row 2.
- Row 2 (20 px): source, affiliation and age.
- Row 3 (20 px): `say TRACK · DISMISS`.
- Top-right: queue indicator `+N` with one pip per severity class.

**Ranking.** This is computed on the companion ([architect](./architect.md)). The HUD sees `priority` but the rule is shared:
1. Severity class is lexicographic: WARNING > CAUTION > ADVISORY.
2. Within a class: score = 0.4·proximity + 0.25·closing + 0.15·recency + 0.15·novelty + 0.05·confidence, where:
   - proximity = 1 − min(r/1000 m, 1)
   - recency = e^(−age/30 s)
   - novelty is 1 for a new track and 0.3 for a re-alert
3. **Pre-emption:** a higher class pre-empts immediately. Within the same class a new alert pre-empts only if its score beats the current one by 0.2 *and* the current one has been shown for at least 3 s (prevents flicker).
4. **Dismissed tracks** are suppressed for 60 s unless the class escalates or the range closes by 30% or more.
5. **Expiry:** advisory after 30 s, caution after 120 s. "Next" or a forward swipe cycles the queue.
6. **Flooding:** above 3 new same-class alerts in 10 s, they collapse into one summary ("3 UNKNOWN · NE · 300–600 m").

**Confirmation card** (replaces the banner in the same place):
```
CONFIRM TASK                        ████████░░ 10s
DRONE 2 → SEARCH AREA "NORTH RIDGE"
ALT 60 m · RADIUS 150 m · ETA 2 min
say CONFIRM  /  CANCEL      (2-finger hold = confirm)
```
- The readback is rendered from the structured `CommandProposal` fields, **not the raw transcript**.
- Timeout is 10 s. It then **auto-cancels and is never auto-confirmed**, showing "NOT SENT — timed out" for 2 s.
- After confirmation the card shows two-stage status, like aviation datalink: `SENT` then `ACK DRONE 2`, or `NO ACK — link` in amber after 3 s.
- Safeguards:
  - A 0.6 s confirm lockout after the card appears, so the tail of the command or an echo cannot confirm it.
  - CONFIRM must be the whole utterance and above the ASR confidence threshold.
  - Any ambiguity resolves to *cancel*.
  - A WARNING arriving mid-confirm cancels the proposal and tells the operator to re-issue.
- **Vocabulary risk:** "confirm" and "cancel" share the onset /k-n/ and are confusable in noise. Measure this. If it is confusable, adopt "CONFIRM / NEGATIVE", with "cancel" kept as a synonym for cancel only (Voice expert).

### 1.6 Modes

| Mode | Behavior |
|---|---|
| **Day** | Full palette. Brightness follows the ambient light sensor if one exists (UNVERIFIED); otherwise the user steps it ("brighter"). |
| **Night / light discipline** | Monochrome **dim NVIS-type green** (~530 nm), luminance capped at the lowest level that is still readable (to be measured; target <5 cd/m²). APL ≤3%: inset only on request, map rings off. **Not red by default.** Red helps the wearer's dark adaptation, but image-intensifier photocathodes are most sensitive in the red/NIR, and Class A NVIS is "not compatible with red" lighting ([MIL-STD-3009](https://cdn.shopify.com/s/files/1/1942/0217/files/MIL-STD-3009.pdf)). A red "dark-adapt" variant is a user option only. This addresses the IVAS complaint that the display glow was "visible from hundreds of meters away" ([TechSpot/Insider](https://www.techspot.com/news/96304-army-tester-warns-microsoft-hololens-based-ar-goggles.html)). Reviewers already notice the X3 Pro's light in the dark ([Skarredghost](https://skarredghost.com/2025/12/17/rayneo-x3-pro-review/)), so forward leakage must be measured. |
| **Quiet** | Orthogonal to night mode. No earcons or TTS. Voice input becomes push-to-talk only (whispered ASR is unreliable), and touch becomes the primary confirm path. |
| **Degraded** | **Never show stale data as current.** Per-symbol age: dashed after 30 s, labeled "last known 2m" after 120 s. Status strip shows `DATA 45s` in amber. Companion lost: amber banner "COMPANION LOST — LOCAL ONLY", heading tape stays live, map greys out after 3 s (per architect). Voice service unreachable: `✕ VOICE OFFLINE`, and touch takes over. |
| **Declutter** | Voice "declutter" cycles FULL → MIN (tape, banner, voice) → WARNINGS-ONLY. |

### 1.7 Hands-free interaction and fallback

Voice is primary, gated by PTT or a wake word (Voice expert). The temple mapping uses the vendor's right-temple gestures ([touchpad API](https://rayneo.gitbook.io/rayneo-devdoc/x-xi-lie/android-kai-fa/neng-li-jie-shao/chu-kong-ban-guan-li)).

| Right temple gesture | Action | Risk if accidental |
|---|---|---|
| Single tap | Show queue / focus (harmless) | None. The touchpads are "too sensitive" and fire when the frame is adjusted ([Skarredghost](https://skarredghost.com/2025/12/17/rayneo-x3-pro-review/)). |
| Swipe forward/back | Next/previous alert | None |
| Double tap | DISMISS / CANCEL | Safe direction |
| Long press (1 s) | Push-to-talk. Must override the system quick panel (UNVERIFIED). | Low |
| **Two-finger hold ≥1 s** (X3 only), with a progress ring | **Touch CONFIRM.** Only valid while a card is open. | Deliberate gesture |

- The left temple stays system-reserved (volume, assistant). If its long-press assistant cannot be suppressed (UNVERIFIED), document it as a known conflict.
- The ring mirrors the right temple.
- The companion touchscreen is the full fallback.
- Input is suspended while the glasses are off-head (wear-detection API), and touches within 300 ms of a wear-state change are ignored.

## 2. Interfaces and needs from other experts

- **Architect.** Additions to `HudState`:
  - `alert.queue{count, by_severity}` and `alert.shown_since_ms`
  - `entities[].age_ms` and `style∈{friend,unknown,threat,self}`
  - `operator.heading_unc_deg`
  - `mode{day|night|quiet|declutter}`
  - `proposal.rows[]` (structured readback lines), `proposal.lockout_ms`, `execution{status}`
  - `inset.frame_age_ms`, `inset.crop_bbox`
  - `voice.state` enum as in §1.3

  The ranking constants in §1.5 are to be placed in a shared config.
- **Voice (Om):** a confirm/cancel confusion matrix under 75–85 dBA noise, the confidence threshold, PTT vs wake word, and a canonical readback generator.
- **Vision/ML (Anshuman):** class set (P/V/D), confidence, stable `track_id` (needed for novelty), geolocation with `ce_m` (range text is rounded to the CE, e.g., "~400 m"), a crop per alert, and the expected alert rate (design target ≤2/min sustained).
- **Hardware (Arjun), day-1 measurements:**
  - Actual per-eye pipeline
  - Luminance range: minimum and maximum nits, measured with a phone lux meter as a proxy
  - Ambient light sensor
  - Magnetometer presence and heading error near radios
  - Whether the right/left long-press can be intercepted
  - Two-finger events
  - Wear detection
  - Fps and thermals with the inset on
  - Forward light leakage in a dark room at 1, 5 and 10 m
- **Systems (Simon):** set up ATAK-CIV on a chest-mounted phone fed by our CoT multicast as the study baseline, and budget participant pay (~18 × $20).
- **Product/HUD (Alisha):** owns the symbol set and Figma, and runs recruitment. This document gives her the starting spec.

## 3. Pre-arrival build and verification

1. **Emulator** (`glasses/emulator-desktop`, same `hud-core`):
   - **Views:** a single 640×480 view at ×2 nearest-neighbor, and a "true-angular" view that scales the canvas to subtend 24.2° at a measured eye distance (25.7 cm wide at 60 cm) so legibility can be judged at true size. Optional SBS 1280×480.
   - **See-through:** composite out = clamp(T·bg + k·hud) over background video. No alpha is allowed, and HUD black adds nothing. Sliders control lens transmission T, HUD luminance k, and ambient level. The clip library should include sunlit pavement, sky, foliage, snow, dusk and night.
   - **Registration testing:** an equirectangular 360° background cropped to a 24°×18° viewport by simulated yaw (mouse or keys, or a replayed IMU log), so heading-registered elements can be tested.
   - **Overlays:** a live **APL meter** that warns at 13% and 25%, a **2 px stroke lint**, a **text-size lint** (<16 px fails), and color-vision-deficiency simulation (Machado 2009) for deutan, protan and tritan.
   - **Inputs:** keyboard → TempleAction, typed or mic → voice, and a scripted scenario player with event logging for the pilot study.
2. **Golden PNGs** for every state: each alert class, confirm card and its timeout, each mode, stale, frozen inset, heading-quality fallback. Pixel-diff these in CI. They double as review artifacts.
3. **Unit tests for the ranking rules** (with Hypothesis, on the companion): pre-emption hysteresis, minimum dwell, dismiss suppression, flood collapse, and "WARNING cancels proposal".
4. **Cheap see-through rig (optional):** a laptop under a 45° teleprompter glass or acrylic beam-splitter, viewed outdoors. This gives a real additive look in daylight for about $30.
5. **Pilot in the emulator** with 3–5 people, covering legibility and the confirm flow. The verification gate is that all golden states render and the lints pass.

## 4. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Daylight washout (contrast ~1.5:1) | Bold 28/20 px text, luminous near-white, no fills, tint test, legibility trial in sun |
| Heading error or drift breaks registration | Fused heading, uncertainty gate, text bearing fallback, yaw-rate hide |
| Color semantics lost (sun, color-vision deficiency, night) | Shape-redundant coding, monochrome-first, Ishihara as a study covariate |
| Attention tunneling / cognitive capture (classic HUD failure) | Clear center, one banner, declutter, measure peripheral-event detection |
| Accidental confirmation | Lockout, whole-utterance confirm, deliberate touch, auto-cancel, lure trials |
| Light signature at night | Green dim mode, APL ≤3%, leakage measurement |
| Battery and thermal from the inset | On-demand inset, ≤15 fps, crops instead of full video |
| 640×480 text budget | 28-character headlines, abbreviations dictionary |
| SDK unknowns (mirroring, gesture override) | `DisplayAdapter`, emulator independence, day-1 test APK |
| Simulator sickness (IVAS: eyestrain, headaches, nausea; [DOT&E FY22](https://www.dote.osd.mil/Portals/97/pub/reports/FY2022/army/2022ivas.pdf)) | Head-locked UI, no world-locked 3D, SSQ in the study |
| IRB delay | Submit by mid-January (see §5) |

## 5. Evaluation plan for goal 3, and open questions

**Design.**
- Within-subjects, counterbalanced: **HUD glasses** vs **ATAK-CIV on a chest-mounted phone**. Both show the same scenario through our CoT feed.
- Optional ablation: HUD with ranking vs HUD with all alerts shown, which tests the ranking claim directly.
- **N = 18** students. A paired design powered for d = 0.7 at 80% power needs about 18. Add **3–5 SME sessions** (ROTC cadets or veterans, availability UNVERIFIED) run as qualitative think-alouds.

**Protocol.**
- Participants walk a marked indoor or Penn Park loop while a 10-minute scripted scenario plays.
- Stressors:
  - An auditory secondary task (call-sign monitoring, dual-task)
  - Playback noise at 75–80 dBA
  - Time pressure
  - A dusk/night block
- Tasks:
  1. Respond to alerts ("track" or "dismiss")
  2. Navigate to bearings
  3. Issue 4 drone tasks with confirmation
  4. Call out peripheral LED events (a tunneling probe)
- **Lure trials:** the secondary-task script contains "confirm" and "cancel" while a card is open, or a confederate says them.

**Measures.**
- Alert response time from onset and accuracy (hits, misses, wrong actions)
- **SAGAT:** 3 freezes per run with the display blanked, asking level 1–3 queries scored against simulator ground truth
- **SART** (3-D), **raw NASA-TLX**, SUS and SSQ after each run
- Heads-up time from the glasses IMU pitch (worn in both conditions)
- Walking speed
- Peripheral-event detection rate
- Accidental-confirmation count
- A text legibility test: read the banner within 2 s against day backgrounds

**Pre-registered success criteria.**
- Alert response time ≥20% faster than ATAK
- SAGAT non-inferior within 5 points
- TLX not higher
- Peripheral detection non-inferior
- **0 accidental confirmations in ≥180 lure exposures** (upper bound 1.7% by the rule of three)
- Legibility ≥95%

**Analysis.** Linear mixed model on trial-level response time, Wilcoxon tests on the questionnaires, and effect sizes with 95% CIs. Exclude participants with photosensitive epilepsy, and record visual acuity and color vision.

**IRB.**
- Penn requires a protocol submission even for exempt studies. Investigators cannot self-determine exemption ([Pennbook policy](https://catalog.upenn.edu/pennbook/human-subject-research/)).
- The likely route is **Exempt Category 3** (benign behavioral intervention, 45 CFR 46.104(d)(3)). Walking with a display plus noise might push it to expedited. This needs verification with Penn's IRB office.
- Faculty mentor (Mingmin Zhao) as PI is likely required (UNVERIFIED). All team members need CITI training.
- Submit **by about January 15** so approval lands before semester-2 week 8. Recruit veterans or cadets as civilians and avoid on-duty personnel.

**Open questions.**
1. Is the per-eye pipeline mirrored or SBS, and is there a virtual-image distance or convergence offset?
2. What is the minimum luminance, and does the device have an ambient light sensor?
3. Is there a magnetometer, and how large is the heading error near radios?
4. Can the app intercept long-press, left-temple and two-finger gestures?
5. Clock reference: head (as recommended), body, or direction of travel? This needs an SME.
6. Final confirm vocabulary (Voice expert).
7. Is MGRS readout ("say grid") needed for credibility in Phase 0?
8. Does the demo need the expanded drone video at all, or are crops enough?
