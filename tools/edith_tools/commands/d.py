"""WS-D CLI: ``scenario lint``, ``sim record-px4|mock|linkshaper`` (PLAN §4.3, D2, D15)."""

from __future__ import annotations

import argparse
import glob
import sys

RECORD_PX4_MSG = """\
edith sim record-px4: not run here.

PX4 SIH is approval-gated (PLAN L14, D15). On a team laptop with PX4 installed by
tools/install_px4.sh (after the user's explicit approval), record-px4 will:
  1. boot PX4 v1.18 SIH, apply sim/profiles/quad_sim.yaml after boot and read every value
     back (abort on mismatch, C90);
  2. run arm -> takeoff -> goto -> orbit -> search mission -> hold -> rtl -> land and the DLL
     case (silence -> AUTO.LOITER for COM_FAIL_ACT_T -> AUTO.RTL -> link back -> hold), run
     last on the instance (sim r4 nit 1);
  3. save the mode sequence, ACKs and mission handshake to sim/traces/px4_1.18.json.
CI then diffs MockVehicle's trace against it: mode order exact, timing +/-1 s (sim r4 nit 2).
This build does not include the PX4 recorder yet (D15, P1).
"""


def _lint(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="edith scenario lint")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--beats", action="store_true", help="also check beats[] windows (C92)")
    ap.add_argument("-q", "--quiet", action="store_true", help="print failures only")
    a = ap.parse_args(argv)
    from edith_sim.scenario.lint import lint_file

    files = [f for pat in a.files for f in (sorted(glob.glob(pat)) or [pat])]
    rc = 0
    for f in files:
        rep = lint_file(f, beats=a.beats)
        lines = rep.lines()
        if a.quiet:
            lines = [ln for ln in lines if "BAD" in ln or "error" in ln or "FAIL" in ln]
        print("\n".join(lines))
        rc |= 0 if rep.ok else 1
    return rc


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: edith scenario lint <files> [--beats] | edith sim record-px4|mock|linkshaper",
              file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "scenario" and rest[:1] == ["lint"]:
        return _lint(rest[1:])
    if cmd == "sim" and rest[:1] == ["record-px4"]:
        print(RECORD_PX4_MSG, file=sys.stderr)
        return 3
    if cmd == "sim" and rest[:1] == ["mock"]:
        from edith_sim.mock.udp import main as mock_main

        return mock_main(rest[1:])
    if cmd == "sim" and rest[:1] == ["linkshaper"]:
        from edith_sim.linkshaper.relay import main as ls_main

        return ls_main(rest[1:])
    print(f"edith {' '.join(argv)}: unknown WS-D command", file=sys.stderr)
    return 2
