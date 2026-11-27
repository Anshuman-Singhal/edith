VERDICT: APPROVE WITH NITS

R4 sign-off by the Robotics & Simulation expert. Re-probed: PX4 `v1.18.0-rc2` `failsafe/framework.cpp`.

| r3 id | Sev | Status | Evidence |
|---|---|---|---|
| N1 | MAJOR | FIXED | All of these are in: profile `COM_FAIL_ACT_T: 5` with read-back; delayed hold in sim §2; contract and `record-px4` DLL case; lint failsafe row; expects split 22 s / 27 s; countdown formula; D2, D15, risk 10. Re-probe: a link return during the delay keeps an `OnModeChangeOrDisarm` action, so RTL at ≈t325 is robust to the jam ending at t325. The stop at t350 takes over |
| N2 | MAJOR | FIXED | sim §6 table recomputed at s = 4: confirm 5.2, mode 24.2, expired 12, RTL 25. Every `within_s` ≥ LB + 2 |
| N3 | minor | FIXED | VIKING 1-2 timed walk; sim PLI every 2 s |
| N4 | minor | FIXED | `MPC_ACC_HOR`, trapezoidal corners, veh-7 departs t280 |
| B | note | FIXED | Procedural basemap golden (C93) |

No blocking issues.

## Nits for builders

1. **Repeated DLL cases.** After a delayed hold, PX4 refills its start delay at dt/4. A second failsafe within about 20 s therefore gets a shorter hold. Run the DLL contract case last on each instance, or wait ≥20 s or restart before the next one.
2. **Trace-diff timing.** PX4 times link loss from the last GCS heartbeat (1 Hz). The companion times it from the last inbound message. PX4's LOITER and RTL can lead by up to about 1 s.
   - Allow ±1 s timing tolerance in the Mock-vs-PX4 diff.
   - Mode order must match exactly.
3. **Countdown string.** "RTL 0:12" in PLAN §1.4 and hud §1 is illustrative. Render it from the `dll_countdown_s` formula; do not hard-code it.
