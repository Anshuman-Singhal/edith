VERDICT: CHANGES REQUIRED

Widths were measured with PIL on the bundled B612-Bold.ttf. The banner/card has ≈504 px of usable inner width.

**1. MAJOR — §3.7 regions / §3.7.2: the banner and card don't fit vertically, and the card enters the clear zone.**
B612 line heights are 35, 25 and 20 px at font sizes 28, 20 and 16. The banner needs ≈101 px but gets 74 px (y336–410). The 4-row card needs ≈116 px. "Grow to y316" is not enough, and the clear zone ends at y330.
Fix:
- Clear zone `170,150–470,326`.
- Banner/card `60,330–580,424`, fixed, pitch 32/24/24.
- The card has 3 rows: header+bar, task, params.
- The hint moves to the voice row `30,432–610,458` (16 px) while `voice.state=await_confirm`: `◉ say CONFIRM / CANCEL · hold 2 fingers` (307 px).

**2. MAJOR — §3.3, §3.7.2, D4, D11: read-backs overflow.**
- The C09 line `DRONE 1 → LAUNCH + SEARCH NAI 1 · 16T CK 6142 3705 · 300 m sq · ALT 60 m` is 787 px at 20 px.
- Banner row 1 with glyph and queue is 525 px.
Fix:
- The generator emits `readback.rows[2]`:
  - row A: `<CALLSIGN> → <STEPS> <TARGET>` (358 px)
  - row B: `<MGRS-8> · <size/R> · ALT n m` (416 px)
  - ETA moves to `SENT`.
- Rule: measured width ≤490 px, not a character count.
- Banner row-1 text ≤400 px at 28 px (the worst case, `VEHICLE · 11 o'clock · ~1.5 km`, is 420 px, so drop `~` above 1 km). Reserve 84 px for the glyph and queue.
- D4 acceptance adds "all fixture rows fit (font-metric test on bundled TTF)".
- D11 lints add "every text run's bounds lie inside its region; nothing in the clear zone except the caret band".

**3. MAJOR — §3.7 symbology: B612 lacks most HUD symbols.**
The fontTools cmap has no `◆ ▲ ⓘ ◌ ■ ✕ ◄ ► █ ░`. These carry tier, voice and link meaning. Fallback glyphs differ across AIOS, phones and headless Skia, so the goldens won't match the device.
Fix:
- `hud-core/Glyphs.kt` draws every symbol as a 2–3 px vector path: tier glyphs, voice shapes, link ✕, clamps, quatrefoil, countdown bar.
- Lint: every text codepoint must be in the bundled font's cmap.

**4. MAJOR — §3.7 gestures, C08, D3/D12: double-tap DISMISS is the prefix of triple-tap STOP.**
If the SDK emits `DoubleClick` before `TripleClick` (UNVERIFIED), every STOP also dismisses the live alert for 10 min. A frame-adjust double-tap could also silently suppress a WARNING.
Fix:
- The companion holds `double_tap` for 400 ms and drops it if `triple_tap` follows.
- Gesture DISMISS is not allowed on WARNING.
- A gesture dismiss shows `DISMISSED · tap to undo` for 3 s before committing.
- A second pointer during the 300 ms PTT window cancels PTT.
- Tests:
  - D3: "3 taps in 600 ms → only SafetyStop, 0 Feedback".
  - D12: "pointerCount 2 → no PttDown".
  - T7: log the raw event sequence for a triple-tap.

**5. MAJOR — §6.4 G3: input/audio confounds and unachievable lure count.**
The two arms differ in PTT (temple vs touchscreen), mic and audio, so a response-time effect does not isolate the display, which is the point of C21. With 4 tasks per run, ≥180 lures is not specified anywhere.
Fix:
- Both arms use the same BT HID PTT button (≈$10) and the same earbud. One identical earcon at alert onset.
- Temple gestures are tested in a separate 5-min gesture/lure block.
- Primary DV: alert onset → PTT-down of a correct response. ASR latency is logged separately.
- Glasses are worn display-off in the phone arm for IMU pitch.
- Runs have 6 tasks, with ≥8 lures per participant per condition:
  - 4 confederate "confirm" during the participant's PTT
  - 2 within lockout
  - 2 embedded "…confirmed…"
  
  That gives ≥192 lures at N=12, and 0/192 gives a 95% upper bound of 1.6%.
- Legibility: the participant reads row 1 aloud on 6 alerts; a trial passes if class and clock are correct within 2 s.
- Dusk becomes a separate n≥6 legibility sub-study, because 18 dusk sessions won't fit W8–W10.
- A spotter accompanies every walking session.

**6. MINOR — §3.7 small-text overflow.**
- `DRONE 2 · FROZEN 3s` is 171 px against 170. Use `D2 · LIVE · 0.4s` / `D2 · FROZEN 3s` (122 px).
- `TAK● GPS● 62% DATA 45s REC` is 234 px against 160. Show `DATA 45s` on a second line `30,206–165,226` only when stale, and move `REC` to x215–250 of the voice row.
- Transcript: ellipsize the head (47 chars = 370/350 px).

**7. MINOR — §3.7 modes / §3.3 responses.**
Add:
- "While a card is open, CAUTION/ADVISORY alerts queue (`+N`)."
- "Bare responses apply only to the `alert_id` currently displayed (last `hud.event alert_shown`); none displayed → NOOP + toast `NO ALERT`."
- "No declutter level hides the card, stop toasts, voice state or WARNING."

**8. MINOR — night mode.**
The inset (7.1% of the eye) breaks night APL ≤3%. At night the inset is mapped to green luminance, capped at ≤8% transient, and auto-closes after 10 s.

**9. MINOR — §3.8 SBS (L5 accepted).**
- Record the HUD once into a Compose `GraphicsLayer` and draw it into both slots with one global `dx`. This guarantees identical eyes at about half the cost.
- `dx` defaults to 0, with no per-element disparity.
- T5 adds a circle-aspect check (squash ⇒ wrong mode) and L-only/R-only glyphs.
- The T16 swatches become `fg/friend/#FFD400/#FF3030` (C29), not amber.

**10. MINOR — D11 lint definitions.**
- APL = mean linear luminance (0.2126R+0.7152G+0.0722B after sRGB decode) over one eye. Persistent states are measured with the inset and banner closed.
- The golden list must include the C09 card, lockout `…`, timeout, `NO ACK`, flood collapse, night, `FROZEN`, `COMPANION LOST`, `HDG ±` and `DISMISSED · undo`.
- Alisha approves the first goldens from a generated contact sheet.

**11. MINOR — §3.7.2 / C07.**
- Derive the hint from `proposal.confirm_with`, so it never advertises a disabled temple confirm.
- If T7 fails, quiet mode and the "silent tasking" demo use `/ui/touch` on a forearm-mounted phone. Note this in §7.3.
