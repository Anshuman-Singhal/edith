"""Generic hash-pinned fetch engine (WS-A; C73). `./edith fetch <target>`.

Each workstream owns its own lockfile; this engine only downloads, verifies and unpacks.
Lockfile format (YAML)::

    artifacts:
      - name: yolox_tiny_416
        url: https://github.com/.../yolox_tiny.onnx
        sha256: <64 hex>
        dest: models/yolox_tiny.onnx          # relative to repo root; must be gitignored
        license: Apache-2.0                   # required; NC/research-only rows need ship: false
        unpack: zip | tar | none              # optional (default none)
        ship: true | false                    # optional; false = never packaged into dist/

Files already present with the right hash are skipped. A hash mismatch is fatal.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import ssl
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import yaml

from edith_tools.cli.util import repo_root

# target -> (lockfile relative to repo root, owning WS)
TARGETS: dict[str, tuple[str, str]] = {
    "models": ("ml/models.yaml", "E"),
    "visdrone-mot": ("ml/data.lock.yaml", "E"),
    "naip": ("sim/data.lock.yaml", "D"),
    "noise": ("bench/noise.lock.yaml", "C"),
    "voice": ("companion/edith_companion/voice/models.lock.yaml", "C"),
}
SCRIPT_TARGETS = {"rayneo-sdk": "tools/fetch_rayneo_sdk.sh"}
REQUIRED = ("name", "url", "sha256", "dest", "license")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_lock(path: Path) -> list[dict]:
    doc = yaml.safe_load(path.read_text()) or {}
    arts = doc.get("artifacts", [])
    for a in arts:
        missing = [k for k in REQUIRED if not a.get(k)]
        if missing:
            raise ValueError(f"{path}: artifact {a.get('name', '?')} missing {missing}")
        if len(str(a["sha256"])) != 64:
            raise ValueError(f"{path}: artifact {a['name']} sha256 must be 64 hex chars")
    return arts


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    for env in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
        if os.environ.get(env) and Path(os.environ[env]).is_file():
            ctx.load_verify_locations(os.environ[env])
    ccr = Path("/root/.ccr/ca-bundle.crt")
    if ccr.is_file():
        ctx.load_verify_locations(str(ccr))
    return ctx


def download(url: str, out: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "edith-fetch/0.1"})
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, context=_ssl_context(), timeout=120) as r, \
                    out.open("wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
            return
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt == 1:
                time.sleep(5)
                continue
            raise


def fetch_artifact(a: dict, root: Path, src_dir: Path | None = None) -> str:
    dest = root / a["dest"]
    marker = dest.with_name(dest.name + ".sha256") if a.get("unpack") else dest
    if marker.is_file():
        have = marker.read_text().strip() if a.get("unpack") else sha256_file(dest)
        if have == a["sha256"]:
            return "present"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "download"
        local = src_dir / Path(a["url"]).name if src_dir else None
        if local and local.is_file():
            shutil.copyfile(local, tmp)
        else:
            download(a["url"], tmp)
        got = sha256_file(tmp)
        if got != a["sha256"]:
            raise RuntimeError(f"{a['name']}: sha256 mismatch (got {got}, pinned {a['sha256']})")
        kind = a.get("unpack", "none")
        if kind == "zip":
            dest.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(tmp) as z:
                z.extractall(dest)
            marker.write_text(got)
        elif kind == "tar":
            dest.mkdir(parents=True, exist_ok=True)
            with tarfile.open(tmp) as t:
                t.extractall(dest, filter="data")
            marker.write_text(got)
        else:
            shutil.move(tmp, dest)
    return "fetched"


def fetch_target(name: str, root: Path, src_dir: Path | None) -> int:
    lock_rel, ws = TARGETS[name]
    lock = root / lock_rel
    if not lock.is_file():
        print(f"fetch {name}: no lockfile yet ({lock_rel}, owned by WS-{ws}); skipping")
        return 0
    rc = 0
    for a in load_lock(lock):
        try:
            print(f"fetch {name}: {a['name']} ... {fetch_artifact(a, root, src_dir)}")
        except Exception as e:  # noqa: BLE001 - report and continue with other artifacts
            print(f"fetch {name}: {a['name']} FAILED: {e}", file=sys.stderr)
            rc = 1
    return rc


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="edith fetch")
    ap.add_argument("target", choices=[*TARGETS, *SCRIPT_TARGETS, "all"])
    ap.add_argument("--from", dest="src", type=Path, default=None,
                    help="local zip (rayneo-sdk) or directory of pre-downloaded files")
    a = ap.parse_args(argv)
    root = repo_root()
    targets = [*TARGETS, *SCRIPT_TARGETS] if a.target == "all" else [a.target]
    rc = 0
    for t in targets:
        if t in SCRIPT_TARGETS:
            script = root / SCRIPT_TARGETS[t]
            if not script.is_file():
                print(f"fetch {t}: {SCRIPT_TARGETS[t]} not present yet (WS-G)")
                continue
            if a.target == "all" and a.src is None:
                print(f"fetch {t}: needs --from <zip> (vendor URLs are tokenized); skipping")
                continue
            cmd = ["bash", str(script)] + (["--from", str(a.src)] if a.src else [])
            rc |= subprocess.call(cmd, cwd=root)
        else:
            src = a.src if a.src and a.src.is_dir() else None
            rc |= fetch_target(t, root, src)
    return rc
