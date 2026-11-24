VERDICT: APPROVE WITH NITS

I re-measured the widths with Pillow on the bundled B612-Bold.ttf. The label enum widths are 108–154 px. `100 NEW` is 129 px and `D10 LINK` is 126 px, both within the 160 px cap. B612 digits are fixed at 18.2 px at 28 px. The worst row 1, `TEAMMATE · 12 o'clock · ~950 m` (or `~975 m`), is 456 px. Even `12.0 km` gives 459 px, so it fits within 470. At 16 px the ink bbox is 14 px tall, so the 16 px inset label and two chips at a 17 px pitch fit inside 440,170–204.

| r3 id | Status | Where verified |
|---|---|---|
| N1 (row-1 budget) | FIXED | hud §3, §6; PLAN §3.7, D4, D11; interfaces §4 (label enum, `+N` on row 2) |
| N2 (D11 geometry lint) | FIXED | hud §1 (ink bbox), §2 (clear zone 190,150–430,326; chips ≤2 at 17 px, `+N D`), §9; D11 |
| N3 (temple bypasses lockout and ctx) | FIXED | voice §5 press table and rules 3–4 for every method; interfaces `ctx` required on `two_finger_hold`; both D3b rejection cases are present |
| N4 (bare response on a hidden alert) | FIXED | `alert_cleared`/`alert_shown` around the card (hud §6, §7; interfaces `hud.event`); voice §2 and §5 row NOOP + `NO ALERT`; D3b/D3c test |
| N5, N6 (nits) | FIXED | hud §7 multi-tap ≤300 ms plus a D12 test; hud §9 provisional goldens |

No blocking issues.

Nits for builders:
1. The mini-map box ends at x190, which is where the clear zone starts. Treat region boxes as half-open (`x1` exclusive) in the D11 lint, or ring ink at x190 will be counted as clear-zone ink.
2. voice §2 lists `say again` as a bare response, but the §5 card-open row says it re-renders the card. Keep the §5 behaviour: while a card is open, `say again` targets the card.
3. The row-1 sweep stops at 1.5 km, but range is not clamped. I measured up to 12.0 km and it still fits (459 px). Optionally extend the sweep to 9.9 km so the guarantee is tested.
