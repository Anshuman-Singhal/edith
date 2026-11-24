VERDICT: CHANGES REQUIRED

| r2 # | Status | Note |
|---|---|---|
| 1 Friendly association | FIXED | §3.5 row, I8, D8 test, D6 expect and person sprites are all present. N1 covers a gap in my own r2 rule. |
| 2 Outbox / link state | FIXED | interfaces §7 table, flush order, expiry drop, router-log assertion. |
| 3 Vignette kinematics | FIXED | Synthetic on both drones, anchored expects, lint. Leg timing checks out (deer ≈t120, veh-7 ≈t190). |
| 4 Continuous custody | FIXED | Frozen observe; follow only me/teammate; `follow(uid_stream)`; REJECTED tests in D4 and D21. |
| 5 Retraction | FIXED | `t-x-d-d`, uids, D5/D6 tests. N2 covers new defects. |
| 6 how / ce / hae | FIXED | |
| 7 takproto inbound | FIXED | |
| 8 Lexicon | FIXED | 19 entries; "repeat" excluded. |
| 9 Budget | FIXED | |
| 10 Guardrails | FIXED | §7.1. |
| 11 TRL / IVAS / SALUTE | FIXED | SALUTE moved to P2 (D23). Acceptable. |
| 12 VIKING / EXERCISE / m-s | FIXED | |

## Remaining / new issues

**N1. MAJOR: friendly association drops moving teammates and drops every teammate during a TAK outage** (§3.5, C52, I8)

As written, a track is associated only if it is within max(15 m, ce_m) of a PLI fresher than 30 s. Two cases fail:

- **Walking teammate.** At a 10 s PLI rate and 1.4 m/s walking pace, the PLI lags the person by up to 14 m. Add geolocation error and the track falls outside the gate. VIKING 1-2 walks inside D2's footprint and is about 115 m from the operator, so a missed association is a `contact_close` WARNING. That breaks the D6 0-WARNING expect, depending on the walk speed the author picks.
- **Jam window.** The jam drops `tak:*` for 25 s, so the last teammate PLI is 25–35 s old at the end of the window. D2's video and gt Detections are not jammed. Association lapses at about t320–325, and teammates turn into unknown PERSON WARNINGs. That CoT then gets queued and flushed to the TOC on top of the friendlies. This is the r2#1 failure, now at the moment comms are degraded.

Fix (§3.5 row and C52):
- Dead-reckon each PLI to the track time using `course_deg`/`speed_mps`. Gate at max(15 m, ce_m) + min(speed·age, 15 m).
- Make association sticky. Once associated, a track keeps `assoc_friend_uid` while it stays continuously tracked inside that gate. The 30 s freshness test applies only to the first association.
- While `status.tak = lost`, measure PLI age from the moment the link was lost, not from now.

Tests:
- D8: a teammate walking at 1.5 m/s with 10 s PLI gives 0 alerts and 0 CoT.
- D8: a 25 s TAK partition with a teammate in FOV gives 0 alerts and 0 CoT.
- D6: extend the overwatch window's `alerts{tier: warning, count: 0}` and `cot{near_friend_m: 15, count: 0}` to `{event: jam, plus_s: 30}`.

**N2. MAJOR: the retraction rules delete MARKs, re-publish dismissed objects, and one expect is inconsistent with the lint** (§2 CoT, interfaces §7, sim §7)

- **(a) MARK is deleted on loss.** "DISMISS or loss emits `t-x-d-d`" does not exempt human-marked tracks. In the vignette, veh-7 is MARKed at about t200 and then leaves D1's FOV, so the operator's report vanishes from ATAK within about 1 s. That is also the live "MARK, visible on ATAK" beat. Fix: loss deletes only unmarked `m-f` tracks. A track with `how=h-e` is never auto-deleted. On loss, re-send it once as a last-known position (remarks `LKP <DTG>`) and keep its 900 s stale. The recovery replay's "latest live-track states" must include these LKPs. Add a D6 expect: `{during: {from: mark, to: end}, cot: {gt_entity: veh-7, how: h-e, live: true}}`.
- **(b) A dismissed object comes back on re-acquisition.** The DISMISS disc (15 m, same class, 10 min) suppresses alerts only. If the object is re-acquired under a new `track_id` (likely on an adjacent lawnmower leg), it is re-published under a new uid and the deer reappears on ATAK. Fix: the disc also gates CoT publication. Add a D6 expect: `{during: {from: dism, to: end}, cot: {gt_entity: deer-1, live: true, count: 0}}`.
- **(c) `after: dism, within_s: 1` cannot pass.** Lint rule 1 (within_s ≥ lower bound + 2 s) rejects it, so D2's "lint → 0" fails. It is also anchored to the start of the utterance, not to the Feedback event. Fix: use `within_s: 3` here. Keep "≤1 s from Feedback(dismiss)" as the D5 unit test.

**N3. MINOR (document, don't build):** an unknown person within 15 m of a teammate is masked (I8). List it in the §9 watch list and on the scope slide. A P1 option is one-to-one assignment with CAUTION for the extras.

**N4. MINOR (outside my domain, flagged for sim/voice):** `say` is not defined as text injection or audio. At `--speed 4`, wall-clock ASR/card latency is ×4 in sim time. `after: scout, within_s: 5 → dispatched` may then be infeasible. Lint lower bounds must scale compute latency by `EDITH_SPEED`.

## Phase B buildability (WS-F)

D5, D19 and the teammate sim are pure Python with UDP/TCP loopback, plus `takproto`/`pytak` from pip. They need no apt, PX4 or Docker and fit 2 CPU / 7 GB. The D5 tests prove the claims once two things are in place:
- the fake router has a "stop answering pings" switch for the TCP 2-miss test;
- the multicast test is allowed to skip.

D6's CoT and TAK expects are provable on Mock once N1 and N2 are applied.
