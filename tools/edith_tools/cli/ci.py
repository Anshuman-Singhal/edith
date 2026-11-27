"""`./edith ci`: the same steps as .github/workflows/ci.yml (PLAN §4.4).

The glasses build runs serially, never alongside e2e (C77), and Gradle retries once on
HTTP 429 (L27).
"""

from __future__ import annotations

import argparse

from edith_tools.cli.testrun import run_tier

STEPS = ["lint", "unit", "contract", "integration", "e2e", "golden", "android"]


def main(argv: list[str]) -> int:
    import os

    ap = argparse.ArgumentParser(prog="edith ci")
    ap.add_argument("--python-only", action="store_true", help="skip golden and android")
    a = ap.parse_args(argv)
    steps = [s for s in STEPS if not (a.python_only and s in ("golden", "android"))]
    for s in steps:
        print(f"=== ci: {s}", flush=True)
        rc = run_tier(s, [], dict(os.environ))
        if rc:
            print(f"ci: step {s} failed ({rc})")
            return rc
    print("ci: all steps passed")
    return 0
