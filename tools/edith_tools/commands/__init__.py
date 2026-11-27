"""Per-workstream CLI modules (WS-A owns only this file).

Each ``<ws>.py`` exposes ``main(argv: list[str]) -> int`` where ``argv[0]`` is the
top-level command (``up``, ``scenario``, ``bench``...). Stubs return 2 until the owning
workstream implements them.
"""

from __future__ import annotations

# top-level command -> owning workstream (PLAN §4.3, §5.1)
ROUTES: dict[str, str] = {
    "up": "b",        # supervisor
    "scenario": "d",  # scenario lint
    "sim": "d",       # record-px4
    "glasses": "g",   # gradle, dist, install, selftest --serve
    "cost": "f",      # cost model
}

BENCH_ROUTES: dict[str, str] = {
    "goal1": "c",
    "goal2": "e",
    "placement": "e",
    "pareto": "b",
}


def route_bench(rest: list[str]) -> str:
    sub = rest[0] if rest else "goal2"
    return BENCH_ROUTES.get(sub, "e")


def stub(ws: str, deliverable: str, argv: list[str]) -> int:
    import sys

    print(
        f"edith {' '.join(argv)}: not implemented yet (WS-{ws.upper()}, {deliverable})",
        file=sys.stderr,
    )
    return 2
