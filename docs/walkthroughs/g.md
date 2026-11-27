# WS-G walkthrough: glasses bring-up kit (D13a)

One runnable path from a fresh clone to results, on any laptop. Steps 1–4 need no glasses.

```bash
# 1. Python env + the RayNeo SDK (vendor sample zip from the RayNeo developer docs; never committed)
uv sync
tools/fetch_rayneo_sdk.sh --from ~/Downloads/MercuryAndroidSample_v0.2.6.zip
#   → sha256 OK ×2, POM with 7 dependency groups, xr2-platform.jks absent

# 2. Build, test, aapt2-check (one Gradle build at a time; ~3 min cold)
./edith glasses test       # registry check, JVM peer tests (T9/T11/T13 vs selftest --serve), Robolectric, APK + aapt2
./edith glasses dist --selftest
cat dist/SHA256SUMS        # hand dist/ to whoever holds the glasses (INSTALL.md §3 checks the hash)

# 3. Rehearse the host side without hardware
tools/bringup.sh --dry-run --tier g0      # fake adb; writes docs/bringup/dryrun.json, schema-validated

# 4. Peer on its own (another terminal can curl it)
./edith glasses selftest --serve --token none &
curl -s localhost:7400/healthz; kill %1

# 5. With the glasses (session 1): follow docs/bringup/INSTALL.md §4–6
./edith glasses selftest --serve          # terminal 1
tools/bringup.sh --tier g0                # terminal 2: T0–T4, install, provision
#   … run T5 → T6 → T7 → T9 → T13 → T14 on the glasses (CHECKLIST.md) …
tools/bringup.sh --pull-only              # results → runs/bringup/<ts>/
```

Where things live: tests are defined in `docs/bringup/TESTS.md` (normative); `./edith glasses
registry` regenerates `registry/registry.json` (bundled into the APK) and `CHECKLIST.md`. The
peer protocol is `docs/bringup/PROTOCOL.md`. SDK-free client logic is `glasses/selftest/proto`
(`:selftest-proto`); `glasses/platform-rayneo` is the only module importing `com.ffalcon.*`.
Without the SDK, `cd glasses && ./gradlew help :platform-api:assemble` warns and succeeds, and the
`generic` selftest flavor runs on any Android phone (`:selftest:assembleGenericDebug`).
