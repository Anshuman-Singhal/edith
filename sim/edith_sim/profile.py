"""Vehicle profile loader (sim spec §1). ``sim/profiles/quad_sim.yaml`` is the single source."""

from __future__ import annotations

from pathlib import Path

import yaml

PROFILES_DIR = Path(__file__).resolve().parents[1] / "profiles"
DEFAULT_PROFILE = "quad_sim"
NON_PARAM_KEYS = frozenset({"orbit_vel_mps"})


def profile_path(name: str = DEFAULT_PROFILE) -> Path:
    p = Path(name)
    if p.suffix in (".yaml", ".yml") and p.exists():
        return p
    return PROFILES_DIR / f"{name}.yaml"


def load_profile(name: str = DEFAULT_PROFILE, overrides: dict | None = None) -> dict:
    data = yaml.safe_load(profile_path(name).read_text())
    if not isinstance(data, dict):
        raise ValueError(f"profile {name}: not a mapping")
    for k, v in (overrides or {}).items():
        if k not in data:
            raise KeyError(f"profile override {k!r} is not a key of profile {name!r}")
        data[k] = v
    return data


def px4_params(profile: dict) -> dict[str, float]:
    """The keys that are PX4 parameters (applied by the sim's PX4 launcher only, C90)."""
    return {k: v for k, v in profile.items() if k not in NON_PARAM_KEYS}
