"""Non-commercial / research-only artifacts are never packaged (C84, L9).

Every lockfile row needs a license; rows whose license is NC, research-only or unknown must
set `ship: false`, and no shipped asset directory may contain such a file name.
"""

import re

import yaml
from _repo import ROOT, tracked_files

LOCKFILES = [
    "ml/models.yaml", "ml/data.lock.yaml", "sim/data.lock.yaml", "bench/noise.lock.yaml",
    "companion/edith_companion/voice/models.lock.yaml",
]
RESTRICTED = re.compile(r"(\bNC\b|-NC|non-?commercial|research|unknown|none|UNVERIFIED)", re.I)


def _rows():
    for rel in LOCKFILES:
        p = ROOT / rel
        if p.is_file():
            for a in (yaml.safe_load(p.read_text()) or {}).get("artifacts", []):
                yield rel, a


def test_every_row_has_license_and_nc_rows_do_not_ship():
    bad = []
    for rel, a in _rows():
        lic = str(a.get("license", ""))
        if not lic:
            bad.append(f"{rel}:{a.get('name')}: no license")
        elif RESTRICTED.search(lic) and a.get("ship", True) is not False:
            bad.append(f"{rel}:{a.get('name')}: license {lic!r} requires ship: false")
    assert not bad, "\n".join(bad)


def test_no_restricted_artifact_in_shipped_assets():
    names = {str(a["dest"]).rsplit("/", 1)[-1] for _, a in _rows() if a.get("ship") is False}
    shipped = [f for f in tracked_files() if "/assets/" in f and f.startswith("glasses/")]
    bad = [f for f in shipped if f.rsplit("/", 1)[-1] in names]
    assert not bad, bad
