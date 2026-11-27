"""Repo hygiene: gitignored outputs, the CLI shim, per-WS command modules."""

import subprocess

from _repo import ROOT

IGNORED = ["data/x", "models/x", "runs/x", "dist/x", "glasses/platform-rayneo/libs/x"]


def test_outputs_are_gitignored():
    r = subprocess.run(["git", "check-ignore", *IGNORED], cwd=ROOT, capture_output=True,
                       text=True)
    assert sorted(r.stdout.split()) == sorted(IGNORED)


def test_shim_is_executable():
    p = ROOT / "edith"
    assert p.is_file() and p.stat().st_mode & 0o111


def test_cli_routes_resolve():
    from edith_tools.cli.main import resolve

    for argv, ws in ((["doctor"], "a"), (["up"], "b"), (["bench", "goal1"], "c"),
                     (["scenario", "lint"], "d"), (["bench", "goal2"], "e"),
                     (["cost"], "f"), (["glasses", "build"], "g")):
        assert resolve(argv)[0] == ws, argv
