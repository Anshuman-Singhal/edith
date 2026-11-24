VERDICT: CHANGES REQUIRED

Edge ML / CV, round 3. I re-checked YOLOX-Tiny@416 in this workspace (ORT 1.29, 1 thread, isolated): p50 57.7 ms, p95 59.2 ms. That is inside D8's 62 ms ±25%, and 4 tiles come to about 240 ms, under the 350 ms p95 limit. D-FINE-N and RT-DETRv2-R18 are both available as ONNX on HF (`onnx-community/dfine_n_coco-ONNX`, `onnx-community/rtdetr_v2_r18vd-ONNX`, Apache-2.0), so the D8 fetch can be built. D8 can be built and tested here with no `data/`, GPU or PX4.

| r2 # | Status | Note |
|---|---|---|
| 1 | FIXED | Ground-plane tracker plus the lawnmower test are in §3.5 and D8. The replay path is not covered (N1) |
| 2 | FIXED | eval §2 matches the fix. It conflicts with the C81 budget (N3) |
| 3 | FIXED | pose_est, CE90 with a yaw term, MC 90 ±3%, synthetic-only CEP. Small leak in n1 |
| 4 | FIXED | ≥12 px measured at detector input, 576×320 export in D14, 45–50 m at −45° |
| 5 | FIXED | Same input for P1 and P2, Wi-Fi adb, `usb_connected` enforced, idle baseline, T18 |
| 6 | FIXED | Video `auto` is off for headless gt, wall-clock cap, D8 timed in isolation |
| 7 | FIXED | |
| 8 | FIXED | |
| 9 | FIXED | |

## Remaining issues

**N1. MAJOR: eval §2, sim §4, D9. Replay footage has no defined pose, so the ground-plane tracker cannot run on the G2 data.**
The composed G2 missions splice in real VisDrone, UAVDT and Okutama segments, but the FrameMeta for those segments is undefined. The only available pose is a "pseudo" one, such as v1's registration onto a synthetic orbit, and it has nothing to do with how the real camera moved. Projecting through it turns real pan and translation into apparent ground motion in metres, with a fabricated metres-per-pixel. Gating at σ ≈ ce_m/2.146 then breaks tracks apart. This is r2#1's failure mode again, now on the only real data. The result is missed 3/5 confirmations and duplicate alerts, which inflate FA/h and break recall.
Fix: add to §3.5 and sim §4: "Feeds with `geo_quality: pseudo` run the same Kalman/second-pass tracker in a **motion-compensated image plane**. Use an inter-tick homography (ORB+RANSAC at 640×360, ECC as fallback) to warp predictions. Use pixel Mahalanobis with σ = 0.1·box diagonal + 4 px. Pseudo geo is used for display only. Resize replay frames to 1280×720. Reset tracks at every splice boundary." Add a D8 test: synthetic frames where the true camera pans 20°/s while `pose_est` is frozen, with mode pseudo. Stationary targets must be confirmed within 2.5 s with IDF1 ≥0.8.

**N2. MAJOR: §3.5 friendly association, D8, D6. PLI age and motion are ignored.**
PLI arrives every 10 s (C26). A teammate walking at 1.4 m/s can be up to 14 m from the last PLI. Add the track error at D2's oblique view (θ about 38° at the near edge, ce_m ≈ 9 m) and the distance often exceeds max(15 m, ce_m). VIKING 1-2 is walking and 100–125 m from the operator, so it becomes a `contact_close` **WARNING** on a friendly. That fails D6's "0 WARNING during overwatch" expect. It also invalidates the `orb2` card, so `state: expired` fails too. The same failure would happen in the field.
Fix: "Dead-reckon each PLI to the detection time using `course_deg`/`speed_mps`. Radius = max(15 m, ce_m) + 0.5 m/s·age_s, with age capped at 30 s. Evaluate association in the same update that confirms the track, before any alert. Association is sticky: release only after 3 consecutive updates beyond 2× the radius." Add a D8 test: a teammate walking at 1.5 m/s with 10 s PLI and nav noise gives 0 alerts and 0 CoT over 120 s in view, and a stranger 30 m from that teammate still alerts.

**N3. MAJOR: §3.5 budget (C81) vs eval §2 recall.**
"≤2 alerts in any 60 s, ≤20/h" is not defined as either a cap or a metric. If WS-H implements it as a cap, a ≤60 s segment with up to 8 GT tracks gets at most 2 alerts, and recall ≥90% (including D9's gt test) is impossible. If it is only a metric, G2 at 10% duty breaks it by design.
Fix: "In Phase 0 the budget is a measured target. Excess CAUTION/ADVISORY alerts queue and are never dropped. In `bench goal2`, a GT entity also counts as recalled if it is boxed in an inset frame during operator-watched seconds within 10 s of event onset. Report alerts/h against the C81 budget as a secondary outcome."

## Nits (builders)

- n1: Apply σ_alt noise to `rel_alt_m`. In stabilized mode, apply σ_rp to the reported gimbal horizon reference. Otherwise geo never sees pitch or altitude error, and ce_m's σ_θ and σ_h terms are fictitious.
- n2: The vignette clutter at conf 0.3 is not sub-threshold, because τ_c(person) is 0.30 and track start is 0.25. It can confirm and hold the banner ahead of veh-7 (pre-emption needs +0.2), which breaks `shown: true`. Set it to 0.20. Give deer-1 `loiter_radius_m: 3`: with 30% leg overlap it is re-acquired, and a 10 m loiter can leave the 15 m dismiss disc.
- n3: FA/h exposure is about 0.33 h at 10% duty, so even 0 FA gives a 95% upper bound of 11/h. Pre-register the decision rule as point estimate ≤6/h, report exposure hours, and count each unique real segment once.
