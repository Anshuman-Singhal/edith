"""Shared helpers for WS-A CLI commands."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def repo_root() -> Path:
    env = os.environ.get("EDITH_ROOT")
    if env:
        return Path(env).resolve()
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "edith").is_file() and (parent / "pyproject.toml").is_file():
            return parent
    return Path.cwd()


def android_home() -> Path | None:
    for key in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        v = os.environ.get(key)
        if v and Path(v).is_dir():
            return Path(v)
    for cand in ("/opt/android-sdk", "~/Library/Android/sdk", "~/Android/Sdk",
                 "~/AppData/Local/Android/Sdk"):
        p = Path(cand).expanduser()
        if p.is_dir():
            return p
    return None


def run(cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> int:
    print("+", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=cwd, env=env)


def run_retry_429(cmd: list[str], cwd: Path | None = None) -> int:
    """Run a Gradle command; retry once if Maven Central answered HTTP 429 (L27)."""
    for attempt in (1, 2):
        print("+", " ".join(cmd), flush=True)
        p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True)
        saw_429 = False
        assert p.stdout is not None
        for line in p.stdout:
            print(line, end="")
            if " 429" in line or "status code 429" in line or "Too Many Requests" in line:
                saw_429 = True
        rc = p.wait()
        if rc == 0 or not saw_429 or attempt == 2:
            return rc
        print("edith: HTTP 429 from a Maven repository; retrying once", flush=True)
    return rc
