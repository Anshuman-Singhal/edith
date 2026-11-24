VERDICT: APPROVE WITH NITS

Reviewer: glasses platform (Android/XR), round 4. I checked PLAN v3 §3.8, §4, §5, D11, D12 and D13a, plus `spec/hud.md` §7, `spec/interfaces.md` §3 and `docs/bringup/TESTS.md`.

## r3 issues

| id | Sev | Status | Where |
|---|---|---|---|
| N1 | M | FIXED | `bringup/TESTS.md` is normative T0–T18 and includes the v2 changes: T5 circle-aspect, T7 DOWN→first frame ≤100 ms plus the triple-tap log, T16 swatches, T18 `CURRENT_NOW`. Also in place: `selftest --serve` on :7400 for T9/T11/T13, OkHttp 4.12, `--es peer`, the D13a JVM peer test, and the registry generated from TESTS.md |
| N2 | M | FIXED | §3.8, hud §7 and interfaces §3 all have draw-pass `card_shown`, re-emit, `card_cleared` and alerts. D11 has the JVM test and the emulator + companion integration test, both the accept case and the suppressed-emission reject case |
| m3 | m | FIXED | `xmltree` + `dump resources` and the `DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION` allowance (D12, D13a) |
| m4 | m | FIXED | `help :platform-api:assemble` + warning (D13a) |
| m5 | m | FIXED | §3.8 `platform-rayneo` line and the TESTS.md prerequisite |
| m6 | m | FIXED | Touch slop for 300 ms, natural-mode mapping in T6, D12 400 ms slide test |
| m7 | m | FIXED | §3.8, D13a, T3 |
| m8 | m | FIXED | §3.8 fetch-script POM pins |

## Blocking issues

None.

## Nits for builders

1. **`selftest --serve` should take `--port` (default 7400).** The D13a JVM test should start the peer on a free port, so it cannot collide with a dev companion on :7400 or with parallel CI jobs. The rule "don't run the companion at the same time" stays for the device session.
2. **Keep the T9/T13 client logic SDK-free.** Put it in a plain Kotlin/JVM class inside `:selftest` (OkHttp only, no `com.ffalcon` and no Android types), so the D13a JVM test runs as a plain unit test. The activity just wraps that class.
3. **State the T13 latency definition in TESTS.md.** The "Latency p95 ≤150 ms" bound applies to the one-way estimate, RTT/2 + decode. Write that in, and log both the raw RTT and the decode time.
4. **Retry Gradle once on HTTP 429** in `fetch_rayneo_sdk.sh` too, not only in CI and doctor.
