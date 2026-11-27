VERDICT: APPROVE WITH NITS

| r3 id | Sev | Status | Verified in |
|---|---|---|---|
| N1 friendly association | MAJOR | FIXED | PLAN §3.5 row has dead-reckoning, radius growth min(0.5·age, 15 m), freshness checked only on first association, PLI age from link loss, and a sticky 3-update/2× release. D8 has both tests. The sim §7 overwatch window runs to jam +30 s with `assoc_friend{min: 1}`. |
| N2a MARK deleted on loss | MAJOR | FIXED | §2 and interfaces §7: `h-e` is never auto-deleted, gets one LKP re-send, keeps a 900 s stale, and LKPs are in the replay. D5 test; sim §7 `during {mark +4 → end}` expects `h-e` live. |
| N2b dismissed object re-published | MAJOR | FIXED | The disc gates CoT (§3.5, interfaces §7). D5 re-acquisition test; sim §7 expects deer-1 live count 0. |
| N2c dismiss expect vs lint | MAJOR | FIXED | `within_s: 4` on the `say`. LB 1.2 + 2 = 3.2 ≤ 4. The ≤1 s from Feedback check is kept in D5. |
| N3, N4 | MINOR | FIXED | Watch list and scope slide; `say` is defined; lint scales latency by speed. |

No blocking issues. I re-checked every D6 CoT/TAK expect against the sim §6 LB table and the timeline (MARK ≈t236, jam t300–325, end t360).

## Nits for builders
1. §3.5: during an outage, use link-loss age for the freshness gate and the radius growth. Pin the dead-reckoning age in D8.
2. Sim §6 `live` should state that a uid stops being live once the router receives its `t-x-d-d`, and that an LKP re-send keeps the original uid.
3. Week-1 ATAK-CIV LAN check: confirm the LKP re-send updates the existing marker and does not add a second one.
