VERDICT: CHANGES REQUIRED

Re-probed in this workspace: moonshine-voice 0.1.6 `small-streaming-en` with Kokoro af_heart, streamed in 20 ms chunks (`scratchpad/r3voice/lines_probe.py`).

| r2 # | Status | Note |
|---|---|---|
| 1 | FIXED | voice §1 profiles, D4 ≥150 captured fixtures (nits N1, N2) |
| 2 | FIXED | `aliases[]` in sim §5 and the D10a check |
| 3 | FIXED | exact match, null conf, Vosk decoys in P1, 480-utterance lure suite at P0 (see M1) |
| 4 | FIXED | `card_shown`, est_start lockout, 1.5 s grace, 7-row table in D3b (see M3) |
| 5 | FIXED | C47 `gesture_seq` hold, D3b test |
| 6 | FIXED | C49 grammar + spotting, D4 fixtures |
| 7 | FIXED | mission items are MOTION (interfaces §6), D3b test |
| 8 | FIXED | C46 ring, `preroll` header, D12 test (N6) |
| 9 | FIXED | voice §6, D10b |
| 10 | FIXED | partials ≤2 Hz, 1 Hz PTT cap, idle and loaded latency |
| 11 | FIXED | pins, `voice/models.lock.yaml`, no `piper-tts` |
| 12 | FIXED | voice §6, eval §1 |
| 13 | FIXED | hud §7, D12 |

## Remaining issues

**M1 · MAJOR (new, probed) · voice §5 item 6: "the open-ASR final" is ambiguous, and Moonshine splits one press into several lines.**
- Probe: a paragraph, then a 1.2 s pause, then "confirm" gave `['The operator should never say…shown.', 'and then you confirm it.', 'Confirm.']`.
- If the rule reads the last line or any single line, the demo lure beat (§7.3: a judge reads a paragraph full of "confirm") executes. So does any press where the wearer pauses before a bystander's "confirm".
- "drone two orbit two o'clock … abort" also splits into two lines.

Fix: the session text is all lines from `ptt_down` (including pre-roll) through the final, joined in order. The confirm rule and the parser run only on that joined text, so a `confirm` is valid only if the whole session normalizes to exactly `confirm`. Add ≥20 multi-line lures × 3 voices (pause, then an isolated "confirm") to D10a, with a bar of 0 confirms.

**M2 · MAJOR · voice §5 items 3–5 vs. scenario `say`, BT PTT and touch.**
- The rule is written only for `ptt_down`/`ptt_up`.
- D6 must drive `say: "confirm"` at `--speed 4`. That means text injection (C40), because WAV ASR can't run in scaled time, and text injection has no press.
- So D6 either fails "scout dispatched" or someone adds an unreviewed bypass.
- `bt_ptt_down/up` (D12, the G3 study's primary input) is not covered either.

Fix:
- The scenario `say` action makes fake_glasses send `ptt_down{held_ms:300, ctx.proposal_id from last hud.state}` → `voice.text` → `ptt_up`. Under `--allow-text-injection`, the text is the session final (`asr.engine=text`).
- `bt_ptt_*` is a press with `held_ms` = DOWN→emit.
- Touch methods skip items 4 and 5 but are subject to lockout from their own raw start.
- D3b tests: `voice.text` "confirm" outside a PTT window never confirms, and a BT press confirms.

**M3 · MAJOR (safety scope) · voice §5 table row 7 vs. the §3.4 rule "Stop: any state".**
"A press that started in lockout → no change" suppresses "abort" or "cancel" spoken just after the card appears. That is exactly when a wrong read-back gets caught. Fix: the lockout and the `ctx.proposal_id` check gate only `confirm` (and new-command supersede). Stop (grammar or spotting) and `cancel` always apply. Add D3b rows: "abort" and "cancel" in a lockout-started press each take effect.

## Nits (builders)

- **N1.** The voice §4 fixture "grid six one four two three seven" has 6 digits, so it is valid under `DIGITS{4|6|8|10}` and won't give SAY_AGAIN. Make it 7 digits.
- **N2.** In the `written` profile, map `2:00` → o'clock before stripping `:`. Split letter+digit tokens (`i1` → `i 1`) before matching aliases.
- **N3.** D3b can't test I6 or I8 with a FakeAdapter, because both need perception, alerts and tak. Assert them in D8, D5 and D3c, and have the D6 monitor cover all eight.
- **N4.** D10a timing and setup:
  - Its WAV→dispatch integration waits for D3a.
  - Under-load latency waits for D6 and runs at speed 1.
  - Use procedural noise plus Kokoro babble with no fetch.
  - Pin the 2 extra Kokoro voices in the lockfile (only af_heart is cached here).
- **N5.** D4's 100% bar on captured fixtures: capture clean, and label any capture the ASR garbles with its true outcome. Report how many were relabelled.
- **N6.** Toggle-PTT fallback: keep the ring through the 450 ms tap decision. D12's "UP <300 ms → mic released" applies only in hold mode.
- **N7.** In the vignette, `mark` comes 3 s after `watch`. Bare-response scope must include the watched or pinned alert, or `cot h-e` fails. Add a D3c test.
- **N8.** Stop detection runs before the rejected-lexicon check ("abort, don't fire" → stop). Keep the PTT detector cap until `voice.final`. During the 1.5 s grace, show `processing`, not `not_sent_timeout`.

## Phase B feasibility

D3b and D4 are pure Python and fit easily. D10a is buildable now: Moonshine and Kokoro both run on CPU here, and 480 lures plus 150 captures take minutes. With M1–M3 applied, the acceptance tests support G1's "0 executions" claim.
