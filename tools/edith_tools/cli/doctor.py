"""`./edith doctor`: toolchain, SDK, adb and port checks (PLAN §4.3, D0)."""

from __future__ import annotations

import argparse
import platform
import re
import shutil
import socket
import subprocess
import sys

from edith_tools.cli.util import android_home, repo_root

REQUIRED_PLATFORMS = ("34", "35", "36")
REQUIRED_BUILD_TOOLS = "36.0.0"
GRADLE_WRAPPER = "8.14.3"
TCP_PORTS = (7400, 18087)
UDP_PORTS = (14550, 18088)


class Report:
    def __init__(self) -> None:
        self.fail = 0
        self.warn = 0

    def ok(self, what: str, detail: str) -> None:
        print(f"  ok    {what:<14} {detail}")

    def bad(self, what: str, detail: str, hint: str = "") -> None:
        self.fail += 1
        print(f"  FAIL  {what:<14} {detail}" + (f"\n        -> {hint}" if hint else ""))

    def note(self, what: str, detail: str) -> None:
        self.warn += 1
        print(f"  warn  {what:<14} {detail}")


def _out(cmd: list[str]) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def check_python(r: Report) -> None:
    v = sys.version_info
    s = f"Python {v.major}.{v.minor}.{v.micro}"
    (r.ok if (v.major, v.minor) == (3, 13) else r.bad)("python", s)
    uv = shutil.which("uv")
    if uv:
        r.ok("uv", _out([uv, "--version"]))
    else:
        r.bad("uv", "not found", "https://docs.astral.sh/uv/")


def check_java(r: Report) -> None:
    java = shutil.which("java")
    if not java:
        r.bad("java", "not found", "install a JDK 21 (Temurin)")
        return
    out = _out([java, "-version"])
    m = re.search(r'version "(\d+)', out)
    major = int(m.group(1)) if m else 0
    line = next((ln for ln in out.splitlines() if "version" in ln), "?")
    if major == 21:
        r.ok("java", f"Java {major} ({line})")
    elif major >= 17:
        r.note("java", f"Java {major}; JDK 21 is the pinned toolchain ({line})")
    else:
        r.bad("java", line, "install a JDK 21")


def check_gradle(r: Report) -> None:
    props = repo_root() / "glasses" / "gradle" / "wrapper" / "gradle-wrapper.properties"
    if props.is_file():
        m = re.search(r"gradle-([\d.]+)-(?:bin|all)\.zip", props.read_text())
        ver = m.group(1) if m else "?"
        (r.ok if ver == GRADLE_WRAPPER else r.bad)("gradle", f"Gradle {ver} (wrapper)")
        return
    g = shutil.which("gradle")
    sysver = ""
    if g:
        m = re.search(r"Gradle ([\d.]+)", _out([g, "--version"]))
        sysver = m.group(1) if m else "?"
    r.note("gradle", f"wrapper not present yet (WS-G); system Gradle {sysver or 'absent'}; "
           f"pinned wrapper is Gradle {GRADLE_WRAPPER}")


def check_android(r: Report, skip: bool) -> None:
    home = android_home()
    if home is None:
        (r.note if skip else r.bad)("android-sdk", "not found",
                                    "set ANDROID_HOME; see docs/bringup/INSTALL.md")
        return
    plats = sorted(p.name.removeprefix("android-") for p in (home / "platforms").glob("android-*"))
    tools = sorted(p.name for p in (home / "build-tools").glob("*"))
    missing = [p for p in REQUIRED_PLATFORMS if p not in plats]
    detail = f"Android SDK platforms {','.join(plats)}; build-tools {', '.join(tools)} ({home})"
    if missing or REQUIRED_BUILD_TOOLS not in tools:
        (r.note if skip else r.bad)(
            "android-sdk", detail,
            "sdkmanager 'platforms;android-34' 'platforms;android-35' 'platforms;android-36' "
            "'build-tools;36.0.0' 'platform-tools'")
    else:
        r.ok("android-sdk", f"Android SDK platforms {','.join(REQUIRED_PLATFORMS)}; "
             f"build-tools {REQUIRED_BUILD_TOOLS} ({home})")
    adb = shutil.which("adb") or (str(home / "platform-tools" / "adb")
                                  if (home / "platform-tools" / "adb").exists() else None)
    if adb:
        on_path = "on PATH" if shutil.which("adb") else "not on PATH; add platform-tools to PATH"
        r.ok("adb", f"{adb} ({on_path})")
    else:
        (r.note if skip else r.bad)("adb", "not found", "sdkmanager 'platform-tools'")


def check_ports(r: Report) -> None:
    for port in TCP_PORTS:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("0.0.0.0", port))
            r.ok(f"tcp/{port}", "free")
        except OSError:
            r.bad(f"tcp/{port}", "in use", "stop the process holding it (companion / selftest?)")
        finally:
            s.close()
    for port in UDP_PORTS:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.bind(("0.0.0.0", port))
            r.ok(f"udp/{port}", "free")
        except OSError:
            hint = "QGroundControl or another GCS holds 14550" if port == 14550 else ""
            r.bad(f"udp/{port}", "in use", hint)
        finally:
            s.close()


def check_platform_notes(r: Report) -> None:
    if sys.platform == "darwin" and platform.machine() == "x86_64":
        r.note("moonshine", "Intel macOS: moonshine-voice wheels are UNVERIFIED; "
               "use the vosk/sherpa engines or a Linux/arm64 machine")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="edith doctor")
    ap.add_argument("--skip-android", action="store_true",
                    help="treat missing Android SDK/adb as a warning (Python-only machines)")
    a = ap.parse_args(argv)
    r = Report()
    print(f"edith doctor ({platform.system()} {platform.machine()}, root {repo_root()})")
    check_python(r)
    check_java(r)
    check_gradle(r)
    check_android(r, a.skip_android)
    check_ports(r)
    check_platform_notes(r)
    print(f"{r.fail} failed, {r.warn} warnings")
    return 1 if r.fail else 0
