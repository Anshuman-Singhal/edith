VERDICT: APPROVE WITH NITS

Edge ML / CV, round 4. I checked my r3 MAJORs against PLAN v3 §3.5, §6, D3c, D8 and D9, plus sim §4 and eval §2.

| r3 id | Status | Where |
|---|---|---|
| N1 pseudo-pose tracking | FIXED | §3.5 tracker row, sim §4 (C95), eval §2, D8 20°/s pan test |
| N2 PLI age/motion | FIXED | §3.5 (C98) dead-reckoning, +min(0.5·age, 15 m), checked before any alert, sticky 3-update/2× release; D8 walking-teammate, stranger and partition tests; sim PLI 2 s |
| N3 budget vs recall | FIXED | §3.5 and eval §2: budget is a measured target, not a cap; queued alerts never dropped (D3c); inset recall credit (D9); alerts/h secondary |

My r3 nits n1–n3 also landed.

## Blocking issues

None.

## Nits (builders)

- nb1: Measuring PLI age from link loss while TAK is down should apply only to the <30 s freshness check. The radius term should keep using the true PLI age, up to the 15 m cap. Otherwise the gate stops growing while dead-reckoning error keeps growing. In D8's 25 s partition test, make the teammate walk.
- nb2: D8 pseudo-test frames need texture (for example the C93 procedural basemap) so ORB finds keypoints. At 20°/s and 2 Hz the camera moves about 10° per tick, so pick an HFOV that leaves ≥60% overlap. Assert that the ECC fallback is hit at least once.
- nb3: Pseudo tracks skip friendly association and metre-based novelty, because their geo is display-only. `contact_close` stays metric-only.
