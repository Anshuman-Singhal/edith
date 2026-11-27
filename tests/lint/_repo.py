"""Helpers shared by the repository lints."""

from __future__ import annotations

import subprocess
from pathlib import Path, PurePosixPath

import yaml

ROOT = Path(__file__).resolve().parents[2]


def tracked_files() -> list[str]:
    """Files git tracks plus untracked-but-not-ignored ones (what a commit would add)."""
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT, capture_output=True, check=True,
    ).stdout.decode()
    return sorted({f for f in out.split("\0") if f and (ROOT / f).is_file()})


def match(path: str, glob: str) -> bool:
    return PurePosixPath(path).full_match(glob)


def load_owners() -> dict:
    return yaml.safe_load((ROOT / "docs" / "OWNERS.yaml").read_text())["workstreams"]


def owners_of(path: str, ws: dict) -> list[str]:
    hits = []
    for name, spec in ws.items():
        if any(match(path, g) for g in spec["paths"]) and not any(
            match(path, g) for g in spec.get("exclude", [])
        ):
            hits.append(name)
    return hits
