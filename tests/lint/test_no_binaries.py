"""No binaries in git except the allowlist (PLAN §4.5)."""

from pathlib import Path

import yaml
from _repo import ROOT, match, tracked_files

BANNED_EXT = {
    ".apk", ".aab", ".aar", ".jar", ".so", ".dll", ".dylib", ".dex", ".class",
    ".onnx", ".tflite", ".pt", ".pth", ".ckpt", ".safetensors", ".h5", ".pb", ".bin",
    ".npz", ".npy", ".pkl", ".mlmodel", ".engine",
    ".zip", ".tar", ".gz", ".tgz", ".xz", ".bz2", ".7z", ".rar",
    ".jks", ".keystore", ".p12", ".pem", ".key",
    ".mp4", ".mkv", ".avi", ".mov", ".h264", ".wav", ".flac", ".mp3", ".ogg",
    ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".ttf", ".otf",
}
MAX_TEXT_KB = 1024


def _allow():
    return yaml.safe_load((ROOT / "tests/lint/binaries_allowlist.yaml").read_text())["allow"]


def _allowed(f: str, size_kb: float) -> bool:
    for a in _allow():
        if match(f, a["glob"]):
            return size_kb <= a.get("max_kb", 10**9)
    return False


def _is_binary(p: Path) -> bool:
    with p.open("rb") as fh:
        return b"\0" in fh.read(8192)


def test_no_binaries():
    bad = []
    for f in tracked_files():
        p = ROOT / f
        kb = p.stat().st_size / 1024
        if _allowed(f, kb):
            continue
        if p.suffix.lower() in BANNED_EXT:
            bad.append(f"{f}: banned extension")
        elif _is_binary(p):
            bad.append(f"{f}: binary content")
        elif kb > MAX_TEXT_KB and f != "uv.lock":
            bad.append(f"{f}: {kb:.0f} KB text file > {MAX_TEXT_KB} KB")
    assert not bad, "binaries must be fetched by script, not committed:\n" + "\n".join(bad)


def test_rayneo_sdk_never_tracked():
    hits = [f for f in tracked_files() if "mercury" in f.lower() and f.endswith((".aar", ".jar"))]
    hits += [f for f in tracked_files() if f.startswith("glasses/platform-rayneo/libs/")]
    assert not hits, hits
