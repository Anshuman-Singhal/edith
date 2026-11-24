VERDICT: CHANGES REQUIRED

R3 review by the Robotics & Simulation expert. Facts marked **[probed]** were read this round from the PX4 `v1.18.0-rc2` source (raw GitHub) or tested in this workspace.

| r2 # | Status | Note |
|---|---|---|
| 1 | PARTIAL | Profile, tasking of D2, the timeout case, jam at t300 and anchoring are all in. The D2 RTL expect still cannot pass on PX4 (N1). My own r2 fix had the same error |
| 2 | PARTIAL | `edith_common.px4` is complete apart from the failsafe hold delay (N1). The contract suite has no DLL case |
| 3 | FIXED | |
| 4 | FIXED | |
| 5 | FIXED | |
| 6 | FIXED | |
| 7 | FIXED | |
| 8–12 | FIXED | `NAV_DLL_ACT` 2 = Return_mode [probed], so the UNVERIFIED tag can be dropped |

## Remaining and new issues

**N1. MAJOR. The failsafe hold delay is not modelled, so Mock and PX4 diverge on the jam beat.**
- **What PX4 does** [probed]:
  - `COM_FAIL_ACT_T` defaults to 5 s.
  - `fromNavDllOrRclActParam()` leaves `allow_user_takeover = Auto`. The delay therefore applies (framework.cpp, "Check if we should enter delayed Hold").
  - The RTL action has `ClearCondition::OnModeChangeOrDisarm`, so it persists after the link returns.
- **Effect on the vignette:** D2 goes `lost` at t320, sits in AUTO.LOITER until about t325, and only then enters AUTO.RTL.
  - `{after: jam, within_s: 22, gt: {drone2, AUTO.RTL}}` fails on PX4 but passes on Mock. This is the Mock-only pass that L14 and L15 exist to prevent.
  - D15's trace diff won't catch it, because the contract suite has no DLL case.
  - `dll_countdown_s` and "RTL 0:12" are also off by 5 s.
- **Fix:**
  1. Add `COM_FAIL_ACT_T: 5` to `quad_sim.yaml` (read back like the other values).
  2. In `edith_common.px4` and Mock: on a failsafe, go to AUTO.LOITER for `COM_FAIL_ACT_T`, then take the action. The action survives link recovery and is cleared only by a mode change or disarm. A mode command during the delay or the action is accepted.
  3. In the lint: the failsafe bound becomes `COM_DL_LOSS_T + COM_FAIL_ACT_T`.
  4. In the vignette, split the expect: `{after: jam, within_s: 22, asset: {id: drone2, link: lost}}` and `{after: jam, within_s: 27, gt: {asset: drone2, mode: AUTO.RTL}}`.
  5. Set `dll_countdown_s = COM_DL_LOSS_T + COM_FAIL_ACT_T − silence`.
  6. Add a contract-suite case, also recorded by `record-px4`: armed in air → silence → LOITER (delay) → RTL → link restored → hold accepted → LOITER.

**N2. MAJOR. The lint's lower-bound rule rejects the committed vignette as written, so D2's "lint → 0" test can't pass.**
- sim §6 sums card latency + lockout + confirm delay + 2 s:
  - `scout` within 5 s holds only if card latency is ≤0.4 s (the budget is 0.5 s p50 and 1.5 s p95).
  - `ovw` (POSCTL.ORBIT within 35 s) fails once path/cruise is added (≈12 s to the circle). PX4 enters ORBIT on ACK, not on arrival.
  - `orb2` (expired) has no bound source at all.
- Builders will loosen the lint, and L15 loses its teeth.
- **Fix:** add a per-predicate table to sim §6:
  - Confirm path = `L_card` (0.5 s, headless text `say`) + max(0.6 lockout, `after_s`) + 0.3.
  - Expired = `L_card` + 10.
  - Mode predicates = arm 1 s + 0.9·alt / `MPC_TKO_SPEED`, with no path term.
  - Position and `completed` predicates add path / `MPC_XY_CRUISE`.
  - Failsafe as in N1.
- **Result:** scout 2.8 s, ovw 21.8 s, orb2 10.5 s and RTL 25 s, each +2 s, all pass.

**N3. MINOR. Teammate PLI is too slow for the association radius.**
- Teammate PLI arrives every 10 s, and VIKING 1-2's walk has no timing.
- At 1.4 m/s, PLI lag (14 m) plus CE90 (~5 m at D2's 50–67° depression) exceeds max(15 m, ce_m). The result would be a WARNING inside the asserted overwatch window, and it would also invalidate any open card.
- **Fix:** give the path timing `{t: 0, e: −120, n: 40}, {t: 360, e: −60, n: 100}` (0.24 m/s), or have the sim teammates send PLI every 2 s.

**N4. MINOR. Mock's mission timing is optimistic.**
- PX4 slows down at each of the ≈8 lawnmower corners (`MPC_ACC_HOR`, PX4 default, value UNVERIFIED). D1 likely reaches veh-7 at about t225–235 instead of t190. That leaves little margin before veh-7 departs at t260.
- **Fix:** add `MPC_ACC_HOR` to the profile, use trapezoidal corners in Mock and the pre-run, and move veh-7's departure to t280.

## Phase B buildability (2 CPU, 7 GB, no GPU/Docker)

All of the P0 sim work can be built here: D2, D7, and D6 at `--speed 4` with video off. All of it is pure Python.
- The current PyAV wheel ships `libx264` [probed]. pymavlink installs on 3.13 [probed].
- The NAIP STAC endpoint is reachable from here [probed]. Note that D7's golden PNG needs `data/`. Give D7 a procedural basemap fallback, or CI will skip the test.
- D15 stays approval-gated.

Once N1 and N2 are fixed, the acceptance tests prove the claims.
