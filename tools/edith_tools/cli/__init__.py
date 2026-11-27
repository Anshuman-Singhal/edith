"""`./edith` command-line entry point (WS-A).

Top-level commands owned by WS-A live in this package (doctor, test, ci, fetch).
Everything else is dispatched to ``edith_tools.commands.<ws>.main(argv)``, which each
workstream owns (PLAN §5.1 "CLI" rule).
"""

from edith_tools.cli.main import main

__all__ = ["main"]
