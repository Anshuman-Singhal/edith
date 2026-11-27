# WS-A walkthrough: repo, contracts, lints

```bash
git clone git@github.com:Anshuman-Singhal/edith.git && cd edith
uv sync --all-extras          # Python 3.13 workspace; uv installs the interpreter if needed
./edith doctor                # toolchain, Android SDK, adb, free ports (add --skip-android on Python-only machines)
./edith test lint             # ruff + owners + no-binaries + truth-import + NC-artifact lints
./edith test unit             # Python unit tests
./edith test contract         # schemas + fixtures + pydantic round-trip (D1)
```

Adding a file: check `docs/OWNERS.yaml` names exactly one workstream for its path, or
`./edith test lint` fails. Need a dependency or a schema change? See `docs/requests/README.md`.
