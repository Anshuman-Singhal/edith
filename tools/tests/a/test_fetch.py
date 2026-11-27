import hashlib
from pathlib import Path

import pytest
import yaml
from edith_tools.fetch import fetch_artifact, load_lock


def _lock(tmp: Path, sha: str) -> Path:
    p = tmp / "x.lock.yaml"
    p.write_text(yaml.safe_dump({"artifacts": [{
        "name": "blob", "url": "https://example.invalid/blob.bin", "sha256": sha,
        "dest": "models/blob.bin", "license": "CC0-1.0"}]}))
    return p


def test_fetch_from_local_dir_verifies_hash(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "blob.bin").write_bytes(b"hello")
    sha = hashlib.sha256(b"hello").hexdigest()
    [a] = load_lock(_lock(tmp_path, sha))
    assert fetch_artifact(a, tmp_path, src) == "fetched"
    assert fetch_artifact(a, tmp_path, src) == "present"
    assert (tmp_path / "models/blob.bin").read_bytes() == b"hello"


def test_fetch_rejects_hash_mismatch(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "blob.bin").write_bytes(b"tampered")
    [a] = load_lock(_lock(tmp_path, "0" * 64))
    with pytest.raises(RuntimeError, match="sha256 mismatch"):
        fetch_artifact(a, tmp_path, src)


def test_lock_requires_license(tmp_path: Path):
    p = tmp_path / "bad.yaml"
    p.write_text(yaml.safe_dump({"artifacts": [{"name": "n", "url": "u", "sha256": "0" * 64,
                                                "dest": "d"}]}))
    with pytest.raises(ValueError, match="license"):
        load_lock(p)
