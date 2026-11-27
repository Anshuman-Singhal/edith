"""`./edith test <tier>` (PLAN §4.4). `unit` is Python only."""

from __future__ import annotations

import argparse
import os
import sys

from edith_tools.cli.util import repo_root, run

NOT_UNIT = "not (contract or integration or e2e or e2e_px4 or golden or lint or slow)"
PY_TIERS = {
    "unit": ["-m", NOT_UNIT, "--ignore=tests/lint", "--ignore=tests/e2e"],
    "contract": ["-m", "contract"],
    "integration": ["-m", "integration"],
    "e2e": ["-m", "e2e and not e2e_px4"],
    "e2e-px4": ["-m", "e2e_px4"],
    "lint": ["tests/lint"],
}
ALL = ["lint", "unit", "contract", "integration", "golden", "e2e", "android"]


def _pytest(args: list[str], env: dict) -> int:
    rc = run([sys.executable, "-m", "pytest", *args], cwd=repo_root(), env=env)
    return 0 if rc == 5 else rc  # 5 = nothing collected for this tier yet


def _glasses(sub: str) -> int:
    from edith_tools.cli.main import main as edith

    return edith(["glasses", sub])


def run_tier(tier: str, extra: list[str], env: dict) -> int:
    if tier == "lint":
        rc = run(["ruff", "check", "."], cwd=repo_root())
        if rc:
            return rc
        return _pytest([*PY_TIERS["lint"], *extra], env)
    if tier in PY_TIERS:
        return _pytest([*PY_TIERS[tier], *extra], env)
    if tier == "golden":
        return _glasses("golden")
    if tier == "android":
        return _glasses("test")
    print(f"edith test: unknown tier {tier!r}", file=sys.stderr)
    return 2


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="edith test")
    ap.add_argument("tier", choices=[*PY_TIERS, "golden", "android", "all"])
    ap.add_argument("--port-base", type=int, default=None,
                    help="base port for tests that open sockets (EDITH_PORT_BASE)")
    a, extra = ap.parse_known_args(argv)
    env = dict(os.environ)
    if a.port_base is not None:
        env["EDITH_PORT_BASE"] = str(a.port_base)
    if a.tier != "all":
        return run_tier(a.tier, extra, env)
    failed = []
    for t in ALL:
        print(f"=== edith test {t}", flush=True)
        if run_tier(t, extra, env):
            failed.append(t)
    print("edith test all:", "FAILED " + ", ".join(failed) if failed else "all tiers passed")
    return 1 if failed else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
