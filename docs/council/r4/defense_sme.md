VERDICT: APPROVE WITH NITS

| r3 id | Sev | Status | Where verified |
|---|---|---|---|
| N1 friendly association (walking teammate, jam window) | MAJOR | FIXED | PLAN §3.5 row (dead-reckoning, radius growth min(0.5·age, 15 m), freshness checked only on first association, PLI age measured from link loss, sticky with 3-update/2× release); D8 has both tests (1.5 m/s with 10 s PLI, 25 s partition); sim §7 overwatch window now runs to `{event: jam, plus_s: 30}` with `assoc_friend{min: 1}`; sim PLI every 2 s; VIKING 1-2 at 0.24 m/s stays 114–122 m from the operator, inside D2's 75–141 m footprint. |
| N2a MARK deleted on loss | MAJOR | FIXED | PLAN §2 CoT, interfaces §7 (`h-e` never auto-deleted, one LKP re-send, 900 s stale, LKPs in the recovery replay); D5 unit test; sim §7 `during {mark +4 → end} cot{veh-7, h-e, live: true}`. |
| N2b dismissed object re-published | MAJOR | FIXED | §3.5 and interfaces §7: the disc gates CoT; D5 re-acquisition test; sim §7 `during {dism +4 → end} cot{deer-1, live: true, count: 0}`. |
| N2c dismiss expect vs lint | MAJOR | FIXED | `within_s: 4`, anchored on the `say`. LB = s·L_cmd = 1.2, and 1.2 + 2 = 3.2 ≤ 4, so lint rule 1 passes. The ≤1 s from Feedback check stays as a D5 unit test. |
| N3, N4 | MINOR | FIXED | §9 watch list, scope slide; `say` defined, lint scales compute latency by speed. |

No blocking issues. I re-checked every D6 CoT/TAK expect against the sim §6 LB table and the vignette timeline (veh-7 MARK at about t236, jam t300–325, end t360). They are consistent and provable on Mock.

## Nits for builders
1. §3.5: during a TAK outage, measure PLI age from link loss for both the freshness gate and the radius-growth term. Keep the true age for the dead-reckoning step. The two choices make no difference to the vignette, but D8 should pin one.
2. The sim §6 meaning of `live` should say outright that a `t-x-d-d` the router has received makes the uid not live, and that LKP re-sends keep the original uid.
3. Week-1 ATAK-CIV LAN check (Simon): confirm an LKP re-send with `how=h-e` renders as an update to the existing marker, not a second one.
