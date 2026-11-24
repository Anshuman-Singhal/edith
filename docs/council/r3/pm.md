VERDICT: CHANGES REQUIRED

Round 3, product lead / red team. I checked the v2 text against my r2 review, and I checked the workspace: the remote answers and `git ls-remote origin main` equals HEAD 5812607; platforms 34/35/36 and build-tools 36.0.0 are under `/opt/android-sdk`; adb is in `platform-tools` but not on PATH, which doctor handles; 2 CPU, 7 GB.

## r2 issues

| r2 # | Status | Note |
|---|---|---|
| 1 | FIXED | L13 remote exists; D0 asserts `ls-remote`; D13a ships INSTALL.md + dist APKs + SHA256SUMS |
| 2 | FIXED | D0 → {D1, D13a}; standalone `:selftest`; G0 tier in session 1 |
| 3 | FIXED | Checked the kinematics. Composed search uploads `[NAV_TAKEOFF, …]` at about t33, so D1 sends no MOTION in the orb2 window. D2 enters POSCTL.ORBIT at about t62. D2 is lost at t320 and still descending at t350 |
| 4 | FIXED | compileSdk 36 and the SDK are installed |
| 5 | FIXED | See N2 |
| 6 | FIXED | |
| 7 | FIXED | 0/192 gives UB 1.56% ✓; seeded wrong read-backs |
| 8 | FIXED | |
| 9 | FIXED | See N4 |
| 10 | FIXED | |
| 11 | PARTIAL | The beat sheet exists, but two live beats can't be executed as written (issues 1 and 2) |
| 12–14 | FIXED | |

## Remaining issues

**1. MAJOR: the `demo_live.yaml` geometry contradicts the C78 beat sheet.** sim §7 says `demo_live` "reuses this geometry", and `--assets px4` forces speed 1. With that geometry the deer appears about 87 s after the scout confirm, and veh-7 about 157 s after it. That puts the false positive before the vehicle and leaves about 2 min of dead air. The sheet allots Scout 45 s → Alert 40 s → FP 15 s. The jam beat also names a separate `demo_jam.yaml`, which would mean restarting the sim mid-demo, with drones re-launching and a 20 s climb.
**Fix (sim §7 + PLAN §7.3):** give `demo_live.yaml` its own layout matched to the beat sheet:
- veh-7 on lawnmower leg 1, with its alert ≤45 s after the scout confirm at speed 1;
- deer-1 later, on leg 2;
- the silent-touch beat tasks D2, so D2 is airborne for the jam;
- `profile_overrides: {COM_DL_LOSS_T: 8}` in this same file, with no scenario switch.

Add `edith scenario lint --beats`, which checks that each beat's GT anchor in the deterministic pre-run falls inside its beat window. Owner Simon, due at the W7 G3 gate.

**2. MAJOR: the lure beat times out before it can show anything.** The beat holds PTT for 30 s while a judge reads a paragraph. Expiry is 10 s after `card_shown` (voice §5 rule 5), so the card expires partway through. The audience sees a timeout, not a rejected lure. Rule 6, exact-match confirm, is never what blocks execution.
**Fix (§7.3):** "Card shown → operator presses PTT ≥1 s after the card → judge reads one ≤6 s sentence containing 'confirm'/'confirmed' → release before 8 s → the HUD still shows AWAIT_CONFIRM ('no change' row) and the god-view wire log shows 0 MOTION → operator says 'cancel'." The beat stays 30 s.

## Nits (builders may handle)

- **N1.** Lint lower bounds for mode-only expects are ambiguous. If the lint adds path length to the `ovw` expect, the bound is 0.5+0.6+2+1+20+12+2 ≈ 38 s, which exceeds `within_s: 35`, so the vignette fails its own lint. Define the bound per predicate: a `gt.mode` bound ends when the verb is sent (C09: orbit is sent at alt ≥0.9×), not when the vehicle arrives.
- **N2.** At 10% duty, about 90% of mission time is synthetic empty footage. WR should charge those seconds at the real-seconds FA rate (upper 95% CI) × R inside AFS_E. Report the uncharged WR as secondary.
- **N3.** D10a lure harness: every lure press must satisfy rules 1–5, so that only rule 6 is under test. The suite is invalid if the positive-control "confirm" false-reject rate is >20%.
- **N4.** The Dec 12 e2e-px4 gate depends on D15 (WS-D, Simon), but its owner is Arjun. Arjun also holds WS-B and WS-G and risks 1, 2, 3, 8 and 10. Make Simon the gate owner (Arjun supplies the laptop) and move risk 10 to Simon.
- **N5.** Make the hand-off an acceptance step. D13a is done when `edith-selftest-rayneo-debug.apk` + SHA256SUMS have reached the user and their hash has been checked on receipt, by Nov 29. §7.1 says "D12 dist first", but §5.2 puts D12 at step 4. State that session 1 needs only the selftest APK.

## Phase B feasibility

Phase B can be built here. Every P0 deliverable runs on Mock, with no GPU, Docker or apt. The Moonshine, sherpa-onnx and Kokoro voices were probed on 3.13. The SDK zip hash was probed. Gradle at 3g runs serially within 7 GB. PX4 is correctly P1. The acceptance tests prove their claims, given N3, and with the honest limit that D13a proves build and badging, not on-device behaviour.
