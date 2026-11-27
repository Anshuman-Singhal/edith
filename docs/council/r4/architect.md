VERDICT: APPROVE WITH NITS

Round 4, systems architect. All round-3 items are fixed in the v3 text. I found no new blocker.

| r3 # | Sev | Status | Where verified |
|---|---|---|---|
| 1 | MAJOR | FIXED | PLAN §3.6 "Runner seams", §2, D2/D3a/D4/D8; sim §2, §5.1; interfaces §3/§6; voice §5. The C87 change (injection allowed with `--headless` on any assets, and the gateway refuses glasses/emulator hellos) keeps the safety intent and is binding under L26 |
| 2 | minor | FIXED | sim §6 LB table plus rule 1 (+2 s only when LB > 0); scout 8. I recomputed the bounds at s=4: scout 5.2, ovw/MISSION 24.2, orb2 12, response 1.2, lost 20, RTL 25. Every `within_s` passes |
| 3 | minor | FIXED | PLAN §3.6; D7 (procedural-basemap golden, no pixels when `video: off`) |
| 4 | minor | FIXED | `enqueued_min` counted before compaction, plus `flushed_uids_include` |
| 5 | minor | FIXED | §2 / interfaces §1. D3a tests the speed-4 emulator refusal |
| 6 | minor | FIXED | §4.1 owner table (A, G); §4.2 `kokoro-onnx` + `models.lock.yaml` |
| 7 | minor | FIXED | sim §1; interfaces §6 `configure()` |

Blocking issues: none.

Nits for builders:
1. **The jam/RTL margin in the vignette is at most 1 s.** D2 loses the link at about t320 and finishes the 5 s hold at about t325, which is exactly when the jam ends. sim §2 says what happens to the failsafe action after link recovery, but not what happens when the link recovers *during* the `COM_FAIL_ACT_T` hold. Fixes:
   - State the PX4-matching rule for recovery during the hold.
   - Have MockVehicle evaluate the hold deadline by timestamp before it processes the recovering packet, so the RTL expect does not flake under CPU load.
   - If the probed PX4 behaviour is "cancel on recovery during the delay", lengthen the jam to ≥30 s and shift the dependent anchors to match.
2. **Text injection with `--assets px4`.** The supervisor should also require that the px4 endpoint is one started by the sim launcher (local SITL/SIH), so `--headless` text injection can never reach a Phase 1 vehicle.
3. **Alert-to-entity join timing.** The runner reads the eventlog while the companion is writing it. It should tolerate a partial last line and re-poll until `track.update` arrives, before it decides `alert_shown{gt_entity}`.
