VERDICT: APPROVE WITH NITS

Checked: PLAN §3.2/§3.4/§3.6, D3a/D3b/D10a; voice §2, §5, §6; interfaces §3; sim §5.1, §6–7; eval §1.

| r3 id | Status | Where |
|---|---|---|
| M1 joined session text | FIXED | voice §2 "Session text", §5 rule 6; D3b rejects "and then you confirm it. Confirm."; D10a ≥20 multi-line lures × 3 voices, bar 0; eval §1 |
| M2 `say` / BT PTT / text press | FIXED | voice §5 press table; `say` = `ptt_down{held_ms 300, ctx}` → `voice.session.start{text}` → `voice.text` → `ptt_up` (sim §5.1); `voice.text` outside a PTT window ignored (interfaces §3); D3b tests both. The stricter version (touch also gated) is acceptable |
| M3 stop/cancel always apply | FIXED | voice §5 outcome table; PLAN §3.4; D3b tests "abort" and "cancel" in a lockout-started press |

D6 timing: the vignette confirms at `after_s: 2` after `card_shown`. With `held_ms` 300 (all ScaledClock ms), `est_start` ≈ card+1.7 s, past the 0.6 s lockout. TTS is off by default (C19), so the lockout is not extended. The confirm path can pass.

No blocking issues.

## Nits (builders)

- **n1.** The press method is `bt_ptt` (voice §5), but `voice.session.start.trigger` is `bt` (interfaces). Use one spelling.
- **n2.** The sim §6 confirm-path LB is `max(lockout 0.6, after_s)`, which ignores the 300 ms `held_ms` back-dating. A confirm `say` with `after_s` <≈0.9 s would lint as passing but be rejected live. Have the lint require `after_s ≥ 0.9 s + margin` for `say: "confirm"`.
- **n3.** In `text` mode the session has no audio or pre-roll, so the joined text is only the injected string. Assert this in D3a.
