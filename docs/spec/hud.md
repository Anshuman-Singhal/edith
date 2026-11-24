# HUD spec (PLAN v3)

Normative detail for [PLAN.md §3.7](../PLAN.md#37-hud). Owner: WS-H (Alisha). Widths were measured by hud r2/r3 with PIL and fontTools on the bundled B612-Bold.ttf. B612 covers `→ · — … ± ° ◉` [probed r3]; `✕` is not in the cmap and is drawn as a vector.

## 1. Display facts

- **Per eye:** 640×480, about 24.2°×18.3°, 26.4 px/deg.
- **Vendor rules** ([RayNeo design spec](https://rayneo.gitbook.io/rayneo-devdoc/x-xi-lie/she-ji-gui-fan)):
  - Safe area x30–610 / y20–460.
  - Text ≥16 px; lines ≥2 px.
  - Black is transparent: no filled panels behind text.
  - APL ≤13% persistent and ≤25% transient.
  - ≤30 fps.
  - Red for warnings only.
- **Line heights (B612):** 35 px at 28 px, 25 px at 20 px, 20 px at 16 px. Line boxes exceed the row pitch, so every geometry lint measures the **ink bbox** (Skia text bounds / Pillow `getbbox`), never the line box (C103).

## 2. Regions v2 (C65)

| Region | Box (x0,y0–x1,y1) | Content |
|---|---|---|
| Mini-map | 30,20–190,180 | Heading-up, r=76 px. Default 500 m, rings at 50/100%. Voice "map" sets 250/500/1k/2k. ≤12 symbols, then clusters |
| Status strip | 30,184–190,204 | `TAK` `GPS` with vector status dots, then companion battery %. **DATA line** `DATA 45s` at 30,206–165,226, only when stale |
| Heading tape | 200,20–420,58 | ±55° compressed (2 px/°), 10° ticks, cardinals, boxed 3-digit heading. Carets at y46–58. Vector clamps at the ends |
| Drone inset | 440,20–610,148 | 170×128 of the 320×240 video. Contrast-stretched without lifting blacks |
| Inset label | 440,150–610,166 | `D2 · LIVE · 0.4s` / `D2 · FROZEN 3s` (122 px) plus a vector slash when the frame is >1 s old |
| Drone chips | 440,170–610,204 | `D1 ORBIT 62%` `D2 LINK✕ RTL 0:12` (16 px; ✕ is vector). **≤2 chips at a 17 px pitch**; more drones collapse into `+N D` (C103) |
| Center clear zone | **190,150–430,326** (±4.5°, C103) | Nothing persistent. Only the conformal caret band y232–248, \|Δ\|≤11°, hidden at yaw rate >60°/s or heading unc >10°. No reticle |
| Banner / card | 60,330–580,424, **fixed** | Rows of 28/20/20 px at pitch 32/24/24 |
| Voice row | 30,432–250,458 | Vector state shape + `LISTENING` / `READY` / `PROCESSING` / `MUTED` / `VOICE OFFLINE`. `REC` at x215–250 |
| Transcript | 260,432–610,458 | 16 px last heard, ellipsized at the **head**, fades after 3 s |
| Confirm hint | 30,432–610,458 (replaces the voice row and transcript while `voice.state=await_confirm`) | `◉ say CONFIRM / CANCEL · hold 2 fingers` (307 px). Built from `proposal.confirm_with`, so it never advertises a disabled method |

## 3. Text-fit rules (C65)

- Fit is checked by **measured width on the bundled TTF**, never by character count.
  - Card rows and banner row 3: ≤490 px at 20 px.
  - **Banner row 1 (C102): ≤470 px at 28 px**, with only the 32 px tier glyph reserved. Row 1 is composed on the glasses with the live clock, so fixtures alone cannot prove fit.
  - **Banner row 2: ≤400 px at 20 px.** The `+N` queue indicator (≈80 px with its tier glyphs) sits at the right end of row 2.
  - **Alert `label` is an enum**, each value ≤160 px at 28 px [measured r3, Pillow on B612-Bold]: `PERSON` 111, `VEHICLE` 113, `GEOFENCE` 143, `TEAMMATE` 154, `D<n> LINK` 109, `TAK LINK` 123, `D<n> BATT` 116, `D<n> TASK` 113, and the flood label `<n> NEW` (111 at n=12). Kinds with no bearing (link, battery, task, TAK) render the label only.
  - The worst bearing tail is ` · 12 o'clock · ~950 m` (302 px; `~` is dropped at ≥1 km), so the worst row 1 is `TEAMMATE` + tail = 456 px.
  - **Tests:** D4 (Pillow) and D11 (Skia) both render every label × 12 clocks × {~50…~950 m in 50 m steps, 1.0…1.5 km in 0.1 km steps} and assert ≤470 px.
- **Read-back rows.** The read-back is `readback.rows[2]`:
  - Row A: `<CALLSIGN> → <STEPS> <TARGET>`
  - Row B: `<MGRS-8> · <size/R> · ALT n m`
  - ETA moves to the `SENT` state.
- **Text codepoints.** Every text codepoint must be in the bundled font's cmap (lint). If `→` or `·` is missing from the cmap, `Glyphs.kt` draws it.

## 4. Palette (C29, L6)

| Token | sRGB | Use |
|---|---|---|
| `fg` | `#E8FFE8` | Text, tape, rings (40%) |
| `friend` | `#33DDFF` | Teammates, own drones |
| `unknown` | `#FFD400` | All machine detections; CAUTION tier |
| `warning` | `#FF3030` | WARNING border and glyph; human-reclassified hostile only |
| `ok` | `#44FF66` | Voice and link nominal |
| `night` | `#33FF66` at the minimum readable level (target <5 cd/m², measured) | Night mode: everything dim green, APL ≤3%, rings off. The inset is on request only, mapped to green luminance, ≤8% transient APL, and auto-closes after 10 s (C65) |

## 5. Symbology and vector glyphs (C65)

`hud-core/Glyphs.kt` draws every symbol as a 2–3 px vector path. No symbol depends on a font:

- Tier glyphs: ▲ WARNING, ◆ CAUTION, ⓘ ADVISORY.
- Voice shapes: filled dot, ring, three dots, square, ✕.
- Link ✕, tape clamps ◄ ►, the countdown bar and the confirm-hint ◉.
- The progress ring for two-finger hold.
- Status dots.
- The 2525-like symbols below, at 12 px.

| Entity | Symbol |
|---|---|
| Self | `fg` chevron |
| Teammate (incl. friend-associated tracks, C52) | Cyan filled circle with heading tick |
| Own drone | Cyan "∩" plus its number |
| Machine detection | Yellow open quatrefoil with P/V letter (C05) |
| Human-marked contact (`entities[].marked`) | Filled quatrefoil |
| Human-reclassified hostile | Red open diamond |
| Stale | Dashed after 30 s; "last known 2m" after 120 s; removed at 5 min |

## 6. Alert banner and confirm card

```
◆ VEHICLE · 2 o'clock · ~400 m                            row1 28 px ≤470 px, live clock
  DRONE 2 · UNKNOWN · 12 s                     +2 ◆▲      row2 20 px ≤400 px + queue
  say WATCH · MARK · DISMISS                              row3 20 px
```
The 2 px tier border flashes at 2 Hz for 2 s, then holds steady (≤3 Hz).

```
CONFIRM TASK                              [=========  ] 10s    header + vector bar (28 px)
DRONE 1 → LAUNCH + SEARCH NAI 1                                 row A (20 px, ≤490 px)
16T CK 6100 3704 · 300 m sq · ALT 60 m                          row B (20 px, ≤490 px)
◉ say CONFIRM / CANCEL · hold 2 fingers                         (voice row, 16 px)
```

**States:**
- Lockout: the hint reads `…`.
- Timeout: `NOT SENT — timed out`. The card never auto-confirms.
- After confirm: `SENT · ETA 2 min` → `ACK DRONE 1`, or yellow `NO ACK — link` after 3 s.
- Stop toasts: `ALL HOLD`, `D2 HOLD`, and `D2 HOLD NOT SENT · LINK` when the link is lost (C50).
- Gesture dismiss: `DISMISSED · slide back to undo` for 3 s before it commits (C47).

**Card rules (C81):**
- While a card is open, CAUTION and ADVISORY alerts queue (`+N`). The card covers the banner, so the glasses send `alert_cleared` when the card covers it and `alert_shown` again when the card closes; bare alert responses are NOOP meanwhile ([voice §5](voice.md#5-confirmation-c48-single-owner-companionedith_companionsafetyconfirm_rulepy), C101).
- A WARNING invalidates the card.
- No declutter level hides the card, stop toasts, voice state or a WARNING.

## 7. Input (C46, C47)

The glasses `InputFsm` runs on raw pointer events in `HudActivity.dispatchTouchEvent`, before super. hud-core contains no pointer modifiers (lint).

- **Hold vs slide (C106):** PTT requires movement below the system touch slop for the first 300 ms; otherwise the gesture is a slide, so a slow slide never opens PTT and `slide_back` undo still works. Slide fwd/back direction follows the system "natural mode" setting; it is mapped in `platform-rayneo` and recorded in T6.
- **Multi-tap window (C106):** taps belong to one `gesture_seq` only if each follows the previous UP within ≤300 ms, so a slow triple-tap is never split into a double-tap plus a tap.
- **`hud.event` emission (C105):** `card_shown{ref=proposal_id}` is emitted exactly once per proposal, from the draw pass of the first frame that contains the card (never on message receipt), re-emitted after a reconnect while the card is visible, and followed by `card_cleared` on removal. `alert_shown` / `alert_cleared` follow the same rule.

| Gesture | Glasses emit | Companion action |
|---|---|---|
| Single-pointer hold ≥300 ms (right pad `cyttsp5_mt`) | `ptt_down{held_ms}` + pre-roll audio from DOWN; `ptt_up` | PTT. A second pointer before 300 ms cancels it, and the buffer is discarded |
| Slide down | `slide_down` | Show queue |
| Slide fwd / back | `slide_fwd` / `slide_back` | Next / prev alert. `slide_back` during the undo window undoes a dismiss |
| Double tap | `double_tap{gesture_seq}` | **Held 400 ms**, dropped if `triple_tap` with the same `gesture_seq` follows. Then: CANCEL if a card is open, else DISMISS if `alert.gesture_dismiss` (false on WARNING) |
| Triple tap | `triple_tap{gesture_seq}` | **SAFETY STOP: hold all** (L1, C08), no delay |
| Two-finger hold, raw-timed, with progress ring | `two_finger_hold{duration_ms, ctx}` (ctx captured at the first DOWN) | CONFIRM if ≥1000 ms, `touch_temple` is enabled, and the voice §5 lockout, card-context and expiry rules pass (C101). Never opens a voice session |
| Single tap | `tap` | None by default. In the toggle-PTT fallback: a confirmed single tap (450 ms with no second tap) toggles PTT (8 s cap); the pre-roll ring is kept through the 450 ms decision (C109) |
| BT HID PTT key | `bt_ptt_down{held_ms, ctx}` / `bt_ptt_up` | PTT (study, both arms; C72); a press under voice §5 |

- Input is ignored within 300 ms of a wear-state change.
- The SDK click sound is off while PTT is armed.
- T7 logs the raw event sequence of a triple-tap and DOWN → first captured audio frame (pass ≤100 ms).

## 8. Stereo rendering (L5, C65)

- **Compositor:**
  - `StereoCompositor` derives each slot from the measured window: `w/2 × h` in SBS, `w × h` in MONO.
  - It scales the 640×480 canvas to fit. Nothing hard-codes 640.
- **Rendering:**
  - The HUD is recorded once into a Compose `GraphicsLayer` and drawn into both slots with one global `dx`.
  - `dx` defaults to 0, with no per-element disparity.
- **T5 checks:**
  - Circle-aspect check: a squashed circle means the stereo mode is wrong.
  - L-only and R-only glyphs.
- **T16 swatches:** `fg`, `friend`, `#FFD400`, `#FF3030`.

## 9. Lints and goldens (D11)

- **APL:** mean linear luminance (0.2126R + 0.7152G + 0.0722B after sRGB decode) over one eye.
  - Persistent states are measured with the inset and banner closed: ≤13% (night ≤3%).
  - Transient states: ≤25%.
- **Geometry:** every text run's **ink bbox** lies inside its region. Nothing is drawn in the clear zone (190,150–430,326) except the caret band.
- **Minimums:** text ≥16 px; stroke ≥2 px.
- **Font coverage:** every codepoint is in the cmap.
- **Golden list (≥24 states × 2 views):**
  - Each alert tier, plus flood collapse.
  - The C09 card, lockout `…`, timeout, `NO ACK`, `SENT`.
  - Stop toasts and `HOLD NOT SENT`.
  - Night, plus night with inset.
  - `FROZEN`, `COMPANION LOST — LOCAL ONLY`, `HDG ±`, `DISMISSED · undo`.
  - DATA stale line, declutter MIN/WARN, the quiet-mode hint.
- **Approval (C106):**
  - In Phase B the builder commits **provisional** goldens plus a contact sheet; D11 diffs against those.
  - Alisha's approval of the contact sheet is a post-handoff gate (by Dec 17), after which the approved set replaces the provisional one.
  - Goldens are approved on Linux only. Other OSes run the lints only (C77).
