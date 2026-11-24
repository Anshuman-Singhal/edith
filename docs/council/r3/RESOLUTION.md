# Round 3 resolution index

This index covers every issue raised in the eight round-3 reviews, nits and buildability notes included, and records how [PLAN v3](../../PLAN.md) resolves it. Decision IDs refer to [DECISIONS.md](../DECISIONS.md) (round 3: L25–L27, C87–C109). M = MAJOR, m = MINOR, n = nit or buildability note. ADOPTED-MODIFIED means the reviewer's fix was taken, but a value or mechanism was changed to reconcile it with another reviewer or a lead ruling; the change is stated in the rationale.

Totals: **57 issues** (19 M, 16 m, 22 n).

| Resolution | Count |
|---|---|
| ADOPTED | 50 |
| ADOPTED-MODIFIED | 7 |
| REJECTED | 0 |

Every MAJOR is resolved. Where three reviewers raised one problem (friendly association: defense_sme N1, ml N2, sim N3), one combined fix is applied (C98).

| Reviewer | # | Sev | Resolution | Rationale | PLAN § / spec | ID |
|---|---|---|---|---|---|---|
| architect | 1 | M | ADOPTED-MODIFIED | Runner hosts FakeGlasses via a B API (`say`, `touch`, `on_card_shown`, `on_alert_shown`); alert→entity join by majority `det_id` from `gt_dets_<i>.jsonl` + eventlog; shared `plan_search`; `cmd` on tasking `say`; D4 parser = `cmd` test. Text injection allowed with `--headless` (any assets) rather than only `--assets mock`, with the gateway refusing glasses/emulator hellos, so D15's px4 vignette still runs (L26). | §2, §3.6, §3.8, D2, D3a, D4; sim §5.1; interfaces §3 | C87 |
| architect | 2 | m | ADOPTED-MODIFIED | LB = first time the predicate holds in the pre-run with modeled latencies; +2 s only when LB > 0. Under defense N4's speed scaling (lint at `max_speed` 4) scout needs `within_s: 8`, not 6. | §3.6, D2; sim §6–7 | C88 |
| architect | 3 | m | ADOPTED | `video: off` = no pixels, no basemap; procedural basemap fallback; D7 goldens use it. | §3.6, D7; sim §4 | C93 |
| architect | 4 | m | ADOPTED | `enqueued_min` counted before compaction, plus `flushed_uids_include: [self, D1]`. | D5; sim §6–7 | C97 |
| architect | 5 | m | ADOPTED | `now = T0 + (wall − T0)·speed`; chose the "supervisor refuses `--emulator`/real glasses at speed ≠ 1" option (safer than scaling, L26). | §2; interfaces §1; sim §5.1 | C94 |
| architect | 6 | m | ADOPTED | `docs/council/**`, `tools/pyproject.toml`, `tools/edith_tools/__init__.py` → A; `glasses/platform-rayneo/sdk.lock` → G; `kokoro-onnx` in `voice` with hashes in `voice/models.lock.yaml`. | §4.1, §4.2, §5.1, §3.8 | C107 |
| architect | 7 | m | ADOPTED | Profile params applied only by the sim launcher; Mock reads the file; companion `configure()` pushes only fence + `GF_*` with read-back. | §3.1, §3.6, D3a; sim §1; interfaces §6 | C90 |
| defense_sme | N1 | M | ADOPTED-MODIFIED | Combined with ml N2 and sim N3: dead-reckoning; radius growth min(0.5 m/s·age, 15 m) (ml's value, smaller after DR, same 15 m cap; L26); freshness only for first association; PLI age from link loss during a TAK outage; sticky with ml's 3-update/2× release; teammate PLI every 2 s in sim. Both D8 tests and the D6 window extension to jam + 30 s adopted. | §3.5, §2, D6, D8; sim §3, §7; interfaces §4, §7 | C98 |
| defense_sme | N2 | M | ADOPTED-MODIFIED | (a) Loss deletes only unmarked `m-f`; `h-e` never auto-deleted; one LKP re-send, 900 s stale, included in replay. (b) Dismiss disc gates CoT. (c) Dismiss expect anchored on the `say`, `within_s` 4 (not 3, because the lint scales compute ×4 at speed 4); ≤1 s from Feedback kept as a D5 unit test. The two new `during` expects start at `plus_s: 4` so they don't see the pre-transition state. | §2, §3.5, D5, D6; interfaces §7; sim §7 | C99, C88 |
| defense_sme | N3 | m | ADOPTED | Masked unknown person near a teammate listed on the §9 watch list and the scope slide; P1 option of one-to-one assignment with CAUTION for extras. | §3.5, §7.3, §9 | C98 |
| defense_sme | N4 | m | ADOPTED | `say` defined as headless text injection with a full press; lint scales compute latency by the lint speed. | §3.6; sim §5.1, §6 | C87, C88 |
| defense_sme | B | n | ADOPTED | Fake router "stop answering pings" switch for the TCP 2-miss test; the multicast test may skip (already in v2). | D5 | C99 |
| hud | N1 | M | ADOPTED | `+N` to row 2 (≤400 px); row 1 ≤470 px with only the 32 px tier glyph; label enum ≤160 px (values measured this round, max 154 px); `<n> NEW` flood label; bearingless kinds label only; D4 Pillow + D11 Skia sweeps over every label × 12 clocks × ranges. | §3.7, D4, D11; hud §3, §6; interfaces §4 | C102 |
| hud | N2 | M | ADOPTED | Clear zone 190,150–430,326; ink-bbox geometry; chips at 17 px pitch, ≤2, then `+N D`. | §3.7, D11; hud §1, §2, §9 | C103 |
| hud | N3 | M | ADOPTED | Lockout and card-context rules apply to every press method; two-finger `est_start = t_recv − duration_ms − rtt/2`, ctx captured at first DOWN. Both D3b rejection cases added. | §3.4, §3.7, D3b; voice §5; hud §7; interfaces §3 | C101 |
| hud | N4 | M | ADOPTED | Glasses send `alert_cleared` when the card covers the banner and `alert_shown` on close; bare alert response while a card is open → NOOP + `NO ALERT`; D3b/D3c test. | §3.3, §3.7, D3b, D3c; voice §2, §5; hud §6; interfaces §3 | C101 |
| hud | N5 | n | ADOPTED | Multi-tap window ≤300 ms; D12 test. | §3.7, D12; hud §7; interfaces §3 | C106 |
| hud | N6 | n | ADOPTED | Provisional goldens + contact sheet in Phase B; Alisha's approval is a post-handoff gate. | §3.7, D11; hud §9 | C106 |
| hud | B | n | ADOPTED | Headless `ImageComposeScene` stays UNVERIFIED with the Java2D fallback already in v2; the builder probes it first. No text change needed beyond v2 §3.8. | §3.8 | — |
| ml | N1 | M | ADOPTED | Pseudo feeds tracked in a motion-compensated image plane (ORB+RANSAC 640×360, ECC fallback; σ = 0.1·diag + 4 px; 1280×720; reset at splices); D8 pan test. | §3.5, §6, D8; sim §4; eval §2 | C95 |
| ml | N2 | M | ADOPTED-MODIFIED | Combined with defense N1 (see that row): ml's radius growth and release hysteresis kept; defense's first-association-only freshness and link-loss age added; evaluated before any alert. D8 walking-teammate + stranger test adopted. | §3.5, D8 | C98 |
| ml | N3 | M | ADOPTED | Budget is a measured target in Phase 0; excess CAUTION/ADVISORY queue, never dropped; inset-boxed recall credit; alerts/h secondary. | §3.5, §6, D3c, D9; eval §2 | C100 |
| ml | n1 | n | ADOPTED | σ_alt on `rel_alt_m`; σ_rp on the gimbal horizon reference; D7 checks it. | D7; sim §4 | C96 |
| ml | n2 | n | ADOPTED | Clutter conf 0.20; deer-1 `loiter_radius_m: 3`. | sim §7 | C96 |
| ml | n3 | n | ADOPTED | FA decision rule = point estimate ≤6/h; exposure hours reported; each unique real segment once. | §0, §6, D9; eval §2 | C100 |
| platform | N1 | M | ADOPTED | `docs/bringup/TESTS.md` written as the normative T0–T18 table (seeded from r1 §5 with the v2 changes); `glasses selftest --serve` peer for T9/T11/T13; OkHttp 4.12 for `:selftest`; `--es peer` provisioning; D13a JVM test against the peer. | §3.8, §4.1–4.3, D13a, D13b; bringup/TESTS.md | C104 |
| platform | N2 | M | ADOPTED | Kotlin `card_shown` emission from the draw pass, re-emit after reconnect, `card_cleared`, same for alerts; D11 JVM + integration tests (integration after D3a and D10a). | §3.8, §5.2, D11; hud §7; interfaces §3 | C105 |
| platform | m3 | m | ADOPTED | `aapt2 dump xmltree --file AndroidManifest.xml` + `dump resources` for the theme; allow `DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION`. | D12, D13a | C106 |
| platform | m4 | m | ADOPTED | D13a no-SDK check is `./gradlew help :platform-api:assemble` + warning. | D13a | C106 |
| platform | m5 | m | ADOPTED | `MercurySDK.init` in the flavor `Application.onCreate`, also in `:selftest`. | §3.8; bringup/TESTS.md | C106 |
| platform | m6 | m | ADOPTED | PTT needs movement below touch slop for 300 ms; natural-mode slide mapping recorded in T6; D12 400 ms slide test. | §3.7, §3.8, D12; hud §7; bringup/TESTS.md | C106 |
| platform | m7 | m | ADOPTED | `bringup.sh` and `glasses install` detect `INSTALL_FAILED_UPDATE_INCOMPATIBLE`, uninstall, reinstall, re-provision. | §3.8, D13a; bringup/TESTS.md T3 | C106 |
| platform | m8 | m | ADOPTED | POM versions pinned in the fetch script. | §3.8 | C106 |
| platform | 429 | n | ADOPTED | Probe recorded as verified (L27); CI and doctor retry Gradle once on HTTP 429. | §4.2, §4.4 | L27, C107 |
| pm | 1 | M | ADOPTED | `demo_live.yaml` own layout (veh-7 leg 1 ≤45 s, deer-1 leg 2, D2 tasked by the silent beat, jam + `COM_DL_LOSS_T: 8` in the same file); `lint --beats`; owner Simon, due at the W7 G3 gate. | §3.6, §7.3, D2; sim §5, §7.1 | C92 |
| pm | 2 | M | ADOPTED | Lure beat rewritten as specified (PTT ≥1 s after card, ≤6 s sentence, release before 8 s, AWAIT_CONFIRM, 0 MOTION, then "cancel"); added "no stop word" so token spotting doesn't fire. Beat stays 30 s. | §7.3 | C108 |
| pm | N1 | n | ADOPTED | Mode-predicate bound ends when the verb is sent (no path term). | §3.6; sim §6 | C88 |
| pm | N2 | n | ADOPTED | Synthetic seconds charged at the real-seconds FA upper CI × R inside AFS_E; uncharged WR secondary. | §6, D9; eval §2 | C100 |
| pm | N3 | n | ADOPTED | Every lure press satisfies rules 1–5; suite invalid if positive-control FR >20%. | D10a; voice §6; eval §1 | C108 |
| pm | N4 | n | ADOPTED | Dec 12 e2e-px4 gate owner → Simon (Arjun supplies the laptop); risk 10 → Simon. | §7 owners, §7.1, §9 | C108 |
| pm | N5 | n | ADOPTED | D13a done only when the selftest APK + SHA256SUMS reach the user and the hash is checked, by Nov 29; session 1 needs only that APK; §7.1 wording fixed. | §5.2, §7.1, D13a | C108 |
| sim | N1 | M | ADOPTED | `COM_FAIL_ACT_T: 5` in the profile with read-back; delayed hold in `edith_common.px4` and Mock; lint failsafe bound; vignette expect split (22 s / 27 s); `dll_countdown_s` formula; contract-suite + `record-px4` DLL case. | §1.4, §3.6, D2, D3a, D6, D15, §9; sim §1, §2, §6, §7; interfaces §6 | C89 |
| sim | N2 | M | ADOPTED-MODIFIED | Per-predicate bound table adopted. Values differ from the reviewer's (scout 2.8 → 5.2, orb2 10.5 → 12) because compute latency is scaled ×4 at the lint speed (defense N4); vignette `within_s` set to the smallest passing values. | §3.6, D2; sim §6–7 | C88 |
| sim | N3 | m | ADOPTED | Both options taken: VIKING 1-2 walk timed (0.24 m/s) and sim teammate PLI every 2 s; association also made robust to 10 s PLI (C98). | §2; sim §3, §7; interfaces §7 | C98 |
| sim | N4 | m | ADOPTED | `MPC_ACC_HOR` (value UNVERIFIED) in the profile; trapezoidal corners in Mock and the pre-run; veh-7 departs t280; kinematic notes updated. | §3.6, D2; sim §1, §7 | C91 |
| sim | B | n | ADOPTED | D7 procedural basemap fallback so CI doesn't skip the golden. | D7; sim §4 | C93 |
| voice | M1 | M | ADOPTED | Confirm rule and parser run on the joined session text; ≥20 multi-line lures × 3 voices in D10a, bar 0. | §1.4, §3.2, D3b, D10a; voice §2, §5, §6; eval §1 | C101 |
| voice | M2 | M | ADOPTED-MODIFIED | `say` = `ptt_down{held_ms 300, ctx}` → `voice.text` → `ptt_up` (merged with architect #1's `voice.session.start`); BT PTT is a press with `held_ms`; `voice.text` outside a PTT window never confirms; BT press confirms. Changed: touch methods are **not** exempt from rules 4–5; hud N3's stricter rule applies to every press (L26, lead instruction). | §3.4, D3a, D3b; voice §5; interfaces §3 | C101, C87 |
| voice | M3 | M | ADOPTED | Lockout and ctx gate only `confirm` and a superseding command; stop and `cancel` always apply; D3b rows added. | §3.4, D3b; voice §5 | C101 |
| voice | N1 | n | ADOPTED | SAY_AGAIN grid fixture now 7 digits. | D4; voice §4 | C109 |
| voice | N2 | n | ADOPTED | `2:00` mapped before stripping `:`; letter+digit split before aliases. | D4; voice §1 | C109 |
| voice | N3 | n | ADOPTED | I6/I8 asserted in D8, D5 and D3c; the D6 monitor covers all eight. | D3b, D3c | C109 |
| voice | N4 | n | ADOPTED | D10a integration after D3a, under-load latency after D6 at speed 1; procedural noise + Kokoro babble, no fetch; 2 extra Kokoro voices pinned. | §5.2, D10a; voice §6 | C109 |
| voice | N5 | n | ADOPTED | Captures made clean; garbled captures labelled with their true outcome; relabel count reported. | D4; voice §4 | C109 |
| voice | N6 | n | ADOPTED | Toggle-PTT keeps the ring through the 450 ms decision; "UP <300 ms → mic released" scoped to hold mode. | D12; hud §7 | C109 |
| voice | N7 | n | ADOPTED | Bare-response scope includes the WATCH-pinned alert; D3c test. | §3.3, D3c; voice §2 | C109 |
| voice | N8 | n | ADOPTED | Stop detection before the rejected lexicon; PTT detector cap until `voice.final`; the grace shows `processing`. | D4; voice §2, §5 | C109 |

## Items needing a human

- **D13a hand-off (C108):** the user must receive `edith-selftest-rayneo-debug.apk` + `SHA256SUMS` and confirm the hash by Nov 29.
- **Ownership changes:** Simon takes the Dec 12 PX4 gate and risk 10 (C108); add to open question 8 at the next team meeting.
- **Golden approval (C106):** Alisha approves the provisional HUD goldens after handoff (by Dec 17).
- Unchanged from v2: PX4/apt approval (L14) and the open questions in PLAN §10.
