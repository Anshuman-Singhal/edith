VERDICT: APPROVE WITH NITS

Round 4, PM / red team. I checked PLAN §3.6, §7.3, D2 and W7, and sim §5–§7.1.

| r3 id | Status | Evidence |
|---|---|---|
| 1 (MAJOR) | FIXED | sim §7.1 gives `demo_live` its own layout: veh-7 on leg 1 (≤45 s), deer-1 on leg 2, the silent beat tasks D2, and the jam plus `COM_DL_LOSS_T: 8` sit in the same file. The `gt: asset_mode` trigger is in the grammar. `beats[]` and lint rule 4 exist. D2 accepts `lint --beats → 0`. W7 G3 has it, owned by Simon. |
| 2 (MAJOR) | FIXED | The §7.3 Lure beat matches my text, plus "no stop word", and stays 30 s. |
| N1–N5 | FIXED | Confirmed in the RESOLUTION rows and the PLAN text. |

**Blocking issues:** none.

**Nits for builders:**
- **B1.** The jam windows (lost ≤8 s, RTL ≤13 s) equal their §6 LBs, and rule 4 adds no slack. Tick quantization can fail the P0 `lint --beats`. Use `to_s` 10 / 15.
- **B2.** veh-7 ≤45 s is tight. From confirm, arm plus climb is ≈21 s and the 156 m transit to (−120,100) is ≈19 s, plus a 3 s dwell. With a near-nadir camera, veh-7 at y=160 alerts at ≈48 s. If the lint fails, move veh-7 south to about (−118,120). Do not widen the window.
- **B3.** D2 reaches ORBIT ≈22 s after the silent confirm, and with `after_s: 20` there is ≈12–15 s of dead air. Narrate it or use `after_s: 5`.
- **B4.** The §7.1 header says "from the scout confirm", but the jam row is measured from jam start. Label it per row.
