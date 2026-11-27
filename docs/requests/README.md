# Dependency and schema requests

WS-A is the sole writer of `uv.lock`, `pyproject.toml` dependencies and `schemas/`. To ask for
a change, append to `docs/requests/<your ws>.md` (you own that file):

```
## 2026-12-03 · WS-C · add dependency
- what: `rapidfuzz>=3.10` (MIT) to the core deps
- why: gazetteer alias matching in the resolver
- blocking: D4 resolver tests
```

WS-A merges the request into the lockfile/schemas in its next commit and replies under the entry.
