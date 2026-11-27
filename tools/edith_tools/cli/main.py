"""Command router for ``./edith``."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable

from edith_tools.commands import ROUTES, route_bench

USAGE = """usage: ./edith <command> [args]

  doctor                               check toolchain, SDKs, ports
  fetch models|naip|noise|visdrone-mot|voice|rayneo-sdk [--from zip]|all
  scenario lint scenarios/*.yaml [--beats]
  up [--headless] --scenario <yaml> --assets mock|px4 --detector gt|yolox [--speed N] ...
  test unit|contract|golden|integration|e2e|e2e-px4|android|lint|all [--port-base N]
  bench goal1|goal2|placement|pareto
  glasses build|test|golden|emulator|dist|install --ip <ip>|selftest [--serve]|pull
  sim record-px4
  cost ...
  ci

See docs/PLAN.md §4.3.
"""


def _a_command(name: str) -> Callable[[list[str]], int]:
    if name == "doctor":
        from edith_tools.cli.doctor import main as f
    elif name == "test":
        from edith_tools.cli.testrun import main as f
    elif name == "ci":
        from edith_tools.cli.ci import main as f
    elif name == "fetch":
        from edith_tools.fetch import main as f
    else:  # pragma: no cover
        raise KeyError(name)
    return f


def resolve(argv: list[str]) -> tuple[str, Callable[[list[str]], int] | None, list[str]]:
    """Return (owner workstream, handler or None, remaining argv)."""
    cmd, rest = argv[0], argv[1:]
    if cmd in ("doctor", "test", "ci", "fetch"):
        return "a", _a_command(cmd), rest
    if cmd == "bench":
        ws = route_bench(rest)
    elif cmd in ROUTES:
        ws = ROUTES[cmd]
    else:
        return "", None, rest
    try:
        mod = importlib.import_module(f"edith_tools.commands.{ws}")
    except ModuleNotFoundError as e:
        if e.name != f"edith_tools.commands.{ws}":
            raise
        return ws, None, rest
    return ws, mod.main, [cmd, *rest]


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    ws, handler, rest = resolve(argv)
    if not ws:
        print(f"edith: unknown command {argv[0]!r}\n\n{USAGE}", file=sys.stderr)
        return 2
    if handler is None:
        print(
            f"edith {argv[0]}: not available yet (WS-{ws.upper()} has not landed "
            f"edith_tools/commands/{ws}.py)",
            file=sys.stderr,
        )
        return 2
    return int(handler(rest) or 0)
