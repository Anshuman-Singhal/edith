# Evaluation spec (PLAN v3)

Normative protocol for [PLAN.md §6](../PLAN.md#6-evaluation). Every target is pre-registered here before W8.

## 1. G1: voice tasking (C69)

| Item | Protocol |
|---|---|
| **Primary evidence** | **Naive study participants' task utterances**: 6 tasks × 2 conditions × N (≈144 at N=12), during the G3 study at 75–80 dB(A) Leq30, measured at the wearer's ear. Report intent success with a 95% CI. |
| Engineering corpus (B6) | ≥3 team speakers × 100 commands through the glasses' mics, played back at 60/75/85/95 dB(A) Leq30 at the ear. Reported **separately**. Bar: intent success ≥90% at 85 dB(A). Consent from all parties (PA law). |
| Synthetic corpus | 2,000 grammar-sampled commands plus ≥100 human paraphrases. Kokoro and Piper voices at 0.9/1.1 speed. Noise per [voice.md §6](voice.md#6-corpus-and-noise-c67-c69), SNR clean to −5 dB. Bar at 10 dB: intent ≥95%, slot exact ≥90%, confident-wrong ≤0.5%. It ranks engines; it does not prove G1. |
| Safety | 0 executions without a valid confirmation across: the audio lure suite (≥480 utterances plus ≥60 multi-line lures, D10a; invalid if the positive-control false-reject rate is >20%, C108); the 10,000-utterance text suite (regression only); ≥2 h of replayed chatter with PTT pressed at random; and the study lures (§4). |
| Metrics | WER; intent success (correct proposal with all slots exact, ≤1 say-again); slot exact-match; confident-wrong (wrong proposal reaches the card); say-again rate; confirm FA/FR; per-stage p50/p95 latency, both idle and under `edith up`. |

## 2. G2: watch reduction (C70)

- **Missions are composed timelines.**
  - Real annotated segments (≤60 s each) are spliced between empty stretches. A script selects segments with ≤8 GT tracks from VisDrone-MOT val/test-dev, Okutama and the UAVDT test split.
  - Empty stretches are synthetic NAIP flyovers with no entities, or real empty segments where they exist.
  - Duty cycle (the fraction of mission time containing a GT entity) is **pre-registered at 5%, 10% and 20%**. The headline is reported at 10%, and WR is reported as a curve.
  - Cross-drone overlap uses Okutama pairs only.
  - The held-out split is frozen in `ml/splits.yaml` before any fine-tune.
- **AFS (attended feed-seconds).**
  - Baseline B0: all N feeds visible for the whole mission (AFS = N·T).
  - Condition E: the scripted operator model opens the inset on `alert_shown` and closes it after R = 6 s or on clear. R = 3 s and R = 10 s are also reported.
  - WR = 1 − AFS_E / AFS_B0. AFS per true event is a secondary metric.
  - **Synthetic-seconds charge (C100).** About 90% of mission time at 10% duty is synthetic empty footage, where a real detector's false alerts are not observed. AFS_E therefore charges those seconds at the real-seconds FA rate (upper 95% CI) × R. The uncharged WR is reported as secondary.
- **Events and recall.**
  - An event is an entity ≥12 px tall **at detector input** (tile scale logged), unoccluded for ≥1 s.
  - On replay, recall is matched **in image space**: IoU ≥0.3 against the annotated track within 10 s. On synthetic, a match is the same class within ≤20 m or ≤ ce_m.
  - A collapsed alert recalls every GT entity inside its extent.
  - A GT entity also counts as recalled if it is boxed in an inset frame during operator-watched seconds within 10 s of event onset (C100), because queued alerts are never dropped.
  - Recall is also reported by pixel height (8–32 px).
- **False alerts (C100).** FA/h counts **real-footage seconds only**, each unique real segment counted once. Exposure is only about 0.33 h at 10% duty (0 FA still gives a 95% upper bound of 11/h), so the pre-registered decision rule is **point estimate ≤6/h**, reported with exposure hours and an exact Poisson 95% CI. FA on synthetic empties is reported separately.
- **Alert budget (C100).** In Phase 0 the C81 budget (≤2 in any 60 s, ≤20/h) is a **measured target, not a cap**: excess CAUTION/ADVISORY alerts queue and are never dropped. Alerts/h against the budget is a secondary outcome.
- **Geolocation.** CEP90 and fusion are measured **only on synthetic missions with `nav_noise`**. Replay tracks are `geo_quality: pseudo`, are tracked in a motion-compensated image plane ([sim §4](sim.md#4-cameras-video-policy-and-frame-sync-c59-c60), C95), and never raise `contact_close`.
- **Person missions.** These fly at 45–50 m AGL with −45° pitch, so a person is about 12.7 px tall at a 576×320 detector input.
- **Procedure.** 10 seeded missions × 10 min × 2 drones. Bootstrap 95% CIs. Sweep τ_c and persistence, then freeze the operating point at W8.

## 3. Edge vs offload (C71)

| Placement | Path |
|---|---|
| P1 (default) | Detector on the companion |
| P2 | The companion relays the **same detector input as P1** (tiles, JPEG q90, at the detector rate, about 2–3 Mbit/s) to the glasses, which detect and return Detections. The best feasible P2 configuration is also reported separately |
| P3 | Offload server over Wi-Fi, same `[Detection]` API on 5800+i (optional) |
| P4 | Glasses camera → on-glasses detection (camera pointed at a monitor replaying clips) |

- **Measurements:** per-stage timestamps; capture→alert p50/p95; sustained fps and dropped frames; parity F1 ≥0.95 vs ORT fp32; bytes/s each way; thermal state; a 20-min soak per configuration.
- **Energy:** measured with adb over Wi-Fi and **USB unplugged** (`usb_connected=false` is enforced). The idle baseline receives the same JPEG stream but runs no inference. T18 records the sign, units and update period of `CURRENT_NOW`.
- **Runtimes, in order:** LiteRT CPU 1/2/4 threads → LiteRT GPU fp16 → NNAPI → QNN. All are UNVERIFIED on AR1.
- **Pareto study** (W8, lead Arjun): alert latency and recall versus link bandwidth and loss (50 kbps–5 Mbps, 0–30%) for three pipelines: stream video then detect; detect at source and send detections + thumbnails; detect on the companion.

## 4. G3: HUD user study (C72)

| Item | Spec |
|---|---|
| Design | Within-subjects, counterbalanced. **Glasses HUD** vs **phone-native layout of the same `HudState`** on a chest-mounted phone (`generic` flavor), frozen at W5 (C72 supersedes part of C21). Both arms use the **same BT HID PTT button (≈$10), the same earbud, one identical earcon at alert onset, a haptic per alert on the phone, and the same confirm methods**. Glasses are worn display-off in the phone arm so the IMU still logs pitch. Optional ablation: ranked vs all alerts |
| N | 18 target (d=0.7, 80% power); floor 12, with effect sizes and CIs (C22). Plus 3–5 SME think-alouds |
| Run | 10-min scripted scenario, 6 tasks, walking a marked loop with a spotter on every walking session. Stressors: call-sign dual task, 75–80 dB(A) Leq30 at the ear, time pressure |
| Primary DV | Alert onset → PTT-down of a correct response. ASR latency is logged separately |
| Lures | ≥8 per participant per condition: 4 confederate "confirm" spoken during the participant's PTT, 2 within the lockout, 2 with "…confirmed…" embedded. That is ≥192 at N=12, so 0/192 gives a 95% upper bound of 1.6%. **Plus ≥2 seeded wrong read-backs per participant** (e.g. the card shows NAI 2 after "NAI 1"); the catch rate is reported as a pre-registered secondary outcome |
| Gesture block | A separate 5-min block of temple gestures and lures (T7-gated temple confirm, triple-tap stop, double-tap hold) |
| Legibility | The participant reads row 1 aloud on 6 alerts. A trial passes if class and clock are correct within 2 s (target ≥95%). Dusk is a separate legibility sub-study with n ≥ 6 |
| Measures | SAGAT (3 freezes), SART, raw NASA-TLX, SUS, SSQ, heads-up time from IMU pitch, walking speed, peripheral LED detection, accidental confirms, wrong-read-back catches |
| Analysis | Mixed model on response time; Wilcoxon on questionnaires. Exclude photosensitive epilepsy. Record acuity and colour vision |

**IRB** (owner Alisha; Prof. Zhao as faculty PI is UNVERIFIED):

| Date | Step |
|---|---|
| Dec 4 | Determination request |
| Dec 18 | CITI training done (all 5) |
| Jan 8 | Protocol, consent and recruitment text submitted |
| Feb 19 | Approval target |
| Feb 22–28 | Pilot with 3–5 users |
| Mar 15–Apr 4 | Main study |

Budget: about 23 × $20.

## 5. G4: cost model (C79)

- **Separate quantities.** Report **capex per kit**, **opex per seat-year** and **5-year TCO** separately. Never add one-time hardware to annual software.
  - `docs/cost/model.csv` has a `basis: one_time|per_year` column, and `cost_model.py` fails on any row missing a basis, or missing both a source URL and an UNVERIFIED tag.
- **Kits:**
  - Incremental kit: trusted glasses $2–5k + EUD $1.5–2.5k as capex (both UNVERIFIED), plus software $3–5k per seat-year as opex. The software price is a **willingness-to-pay hypothesis** to test in interviews.
  - Full kit: includes a MANET radio (pricing UNVERIFIED).
  - Lite kit: goTenna Pro X class radio.
- **Anchors:** IVAS ~$80k/unit hardware (UNVERIFIED, C80); Skydio X10D ≈$21k/system. Compare unit to unit and lifecycle to lifecycle.
- **Phase 0 spend:** RayNeo $1,099–1,399, plus <$2k of accessories, plus a BT PTT button and a forearm phone mount.

## 6. D8 perception metric definitions (WS-E)

- **IDF1** (`edith_bench.goal2.metrics.idf1`): per frame, GT = entities in view; hypotheses =
  confirmed tracks updated in that frame; a pair matches within 10 m (ground) or 40 px (pseudo
  image plane); the identity map is greedy by co-occurrence (a lower bound on IDTP).
- **Confirm latency**: track confirmation time − first frame with the entity in view.
- **Duplicate rate**: confirmed fused tracks per GT entity that has ≥1 (majority `det_id`).
- **CE90 calibration**: fraction of Monte-Carlo fixes with |error| ≤ ce_m under the sim
  nav_noise; must be 90% ±3%.
