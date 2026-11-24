VERDICT: CHANGES REQUIRED

All widths below were measured with PIL and fontTools on the bundled B612-Bold.ttf (scratchpad `m3.py` and `m4.py`). B612 covers `→ · — … ± ° ◉`, so that UNVERIFIED item is closed. It does not cover `✕`, which is drawn as a vector, as specified.

| r2 # | Status | Note |
|---|---|---|
| 1 | FIXED | The regions are as proposed. The clear-zone overlap is a new issue (N2) |
| 2 | PARTIAL | `rows[2]` is fine: the worst read-back I could construct is 458/490 px. The row-1 budget is wrong (N1) |
| 3 | FIXED | Glyphs.kt and the cmap lint are in place |
| 4 | FIXED | 400 ms hold, no dismiss on WARNING, second pointer cancels PTT, slide-back undo, tests in D3b and D12 |
| 5 | FIXED | eval §4 matches |
| 6 | FIXED | |
| 7 | PARTIAL | The new press-outcome table contradicts the bare-response scoping (N4) |
| 8–11 | FIXED | |

## Issues

**N1 — MAJOR — The banner row-1 budget fails on common cases. This was my r2 error.**
- The worst case is not `11 o'clock · 1.5 km` (399 px). Under 1 km the `~` stays, so the tail ` · 12 o'clock · ~950 m` is 302 px.
- `VEHICLE` fails in 54 of 300 clock×range combinations, worst 414 px. `GEOFENCE` reaches 445 px and the flood label `3 UNKNOWN` 477 px.
- Row 1 is composed on the glasses with the live clock. A test on fixtures alone will pass, and the text will still overflow on the device.

Fix (hud §3, §6, D4, D11):
- Move the `+N` queue indicator to the right end of row 2. It is about 80 px at 20 px.
- Reserve only the 32 px tier glyph, so row 1 ≤470 px and row 2 ≤400 px.
- Alert `label` is an enum, each value ≤160 px at 28 px. The flood label is `<n> NEW`. Kinds with no bearing (link, battery, task) render the label only.
- D4 (Pillow) and D11 (Skia) both test every label × 12 clocks × {~50…~950 m, 1.0…1.5 km}.

**N2 — MAJOR — The D11 geometry lint cannot pass as written.**
- The clear zone `170,150–470,326` contains x440–470 of the inset label (`440,150–610,166`). It also contains the same strip of the persistent drone chips (`440,170–610,204`), and x170–190 of the mini-map box.
- "Nothing in the clear zone" therefore fails on every golden.
- "Text bounds inside region" with line boxes also fails:
  - 28 px B612 has a 35 px line box against a 32 px pitch.
  - The inset label is 16 px text (20 px line box) in a 16 px region.

Fix:
- Clear zone `190,150–430,326` (±4.5°). The caret band stays exempt.
- Measure bounds on the ink bbox (Skia text bounds / Pillow `getbbox`), not the line box.
- Stack the drone chips at a 17 px pitch, with ≤2 chips. More drones collapse into `+N D`.

**N3 — MAJOR — Temple confirm bypasses L18's lockout and card-at-DOWN check.**
- voice §5 rules 3–4 (est_start ≥ lockout, `ctx.proposal_id` match) are stated only for `ptt_down`.
- A `two_finger_hold` that starts before the card appears and reaches 1000 ms after the lockout therefore confirms a card the operator never saw.

Fix:
- Apply rules 3–4 to every press method. For `two_finger_hold`: est_start = t_recv − duration_ms − rtt/2 ≥ `lockout_until_ms`, and `ctx.proposal_id` (captured at first DOWN) == `proposal_id`.
- D3b adds two cases, both rejected:
  - "1200 ms hold started 300 ms before card_shown"
  - "two_finger_hold with no ctx.proposal_id"

**N4 — MAJOR — A bare response can act on an alert that is hidden.**
- The card replaces the banner (shared fixed region). The voice §5 row "`hud_cmd` or an alert response → applied; card kept" still applies `watch/mark/dismiss` to the last `alert_shown`, which is no longer visible.
- A DISMISS there suppresses the track for 10 min and retracts its CoT team-wide.

Fix:
- The glasses emit `alert_cleared` when the card covers the banner, and `alert_shown` again when the card closes.
- Change the row to: "`hud_cmd` → applied, card kept. Bare alert response → NOOP + `NO ALERT` (transcript slot), card kept."
- D3b/D3c test: "card open over alert A, `dismiss` → 0 Feedback, A not suppressed."

**N5 — nit.** Pin the InputFsm multi-tap window to ≤300 ms and add a D12 test. Otherwise the 400 ms double-tap hold can miss a slow triple-tap.

**N6 — nit.** D11 "diff ≤0.5% vs approved" has no baseline in Phase B. The builder commits provisional goldens and a contact sheet, and Alisha's approval becomes a post-handoff gate.

## Phase B buildability (hud scope)

- **D3c and the D4 width tests:** buildable now. Pillow 12.3 and fontTools 4.67 are installed, and the B612 TTF is in hand.
- **D11:**
  - JDK 21, Gradle 8.14.3 and SDK 36 are present.
  - Compose and skiko are not cached, so they must come from Maven through the proxy.
  - Headless `ImageComposeScene` on a display-less Linux host is plausible (Skia raster) but UNVERIFIED. The builder should probe it first and keep the Java2D fallback.
  - The serial 3 GB heap fits in 7 GB.
- **Do the tests prove the claims?** Only once N1 and N2 are applied. As written, D4 either fails or under-tests (fixtures only), and D11's lint cannot pass.
- The APL lint proves frame APL only. Device luminance stays with T16, which is correct.
