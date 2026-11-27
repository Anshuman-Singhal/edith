"""Scenario YAML v2 (sim spec §5) as pydantic models."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from edith_common.geo import Origin
from pydantic import BaseModel, ConfigDict, Field, model_validator


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class XY(_M):
    e: float
    n: float


class PathPt(_M):
    t: float
    e: float
    n: float
    heading: float | None = None


class OriginM(_M):
    lat: float
    lon: float
    alt_msl: float
    geoid_n_m: float = 0.0

    def to_origin(self) -> Origin:
        return Origin(self.lat, self.lon, self.alt_msl, self.geoid_n_m)


class Camera(_M):
    mode: Literal["synth", "replay"] = "synth"
    w: int = 1280
    h: int = 720
    hfov: float = 70.0
    pitch: float = -60.0
    gimbal: Literal["stabilized", "body_fixed"] = "stabilized"
    fps: float = 10.0
    clip: str | None = None
    max_range_m: float = 400.0


class Asset(_M):
    id: str
    callsign: str
    instance: int
    spawn: XY
    camera: Camera = Field(default_factory=Camera)


class Person(_M):
    callsign: str
    uid: str | None = None
    path: list[PathPt]
    sprite: str | None = None


class Gazetteer(_M):
    name: str
    e: float
    n: float
    area_m: float | None = None
    aliases: list[str] = Field(default_factory=list)


class Entity(_M):
    id: str
    cls: Literal["vehicle", "person", "animal"]
    sprite: str | None = None
    path: list[PathPt]
    loiter_radius_m: float | None = None


class Clutter(_M):
    e: float
    n: float
    conf: float
    cls: Literal["vehicle", "person", "other"] = "other"


class GtDetector(_M):
    pd: float = 0.95
    fa_per_h: float = 0.0
    latency_ms: float = 150.0
    bbox_noise_px: float = 2.0
    rate_hz: float = 4.0
    confusions: dict[str, str] = Field(default_factory=dict)
    clutter: list[Clutter] = Field(default_factory=list)


class Cmd(_M):
    asset: str
    steps: list[str]
    target: dict[str, Any] = Field(default_factory=dict)
    radius_m: float | None = None
    alt_agl_m: float | None = None


class Jam(_M):
    duration_s: float
    links: list[str]


class Event(_M):
    id: str
    t: float | None = None
    on: dict[str, Any] | None = None
    after_s: float = 0.0
    say: str | None = None
    cmd: Cmd | None = None
    touch: str | None = None
    jam: Jam | None = None
    assert_hold: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _one_trigger(self) -> Event:
        if (self.t is None) == (self.on is None):
            raise ValueError(f"event {self.id}: exactly one of t / on")
        if sum(x is not None for x in (self.say, self.touch, self.jam, self.assert_hold)) != 1:
            raise ValueError(f"event {self.id}: exactly one action (say/touch/jam/assert_hold)")
        return self


class BeatWindow(_M):
    after: str
    from_s: float
    to_s: float


class Beat(_M):
    id: str
    ref: str | None = None  # human label of the window's reference (r4 PM nit B4)
    cmd: Cmd | None = None
    anchor: dict[str, Any]
    window: BeatWindow


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[2]
    name: str | None = None
    seed: int = 0
    duration_s: float = 360.0
    max_speed: float = 4.0
    origin: OriginM
    vehicle_profile: str = "quad_sim"
    profile_overrides: dict[str, float] = Field(default_factory=dict)
    disclosures: list[str] = Field(default_factory=list)
    basemap: str | None = None
    ao: list[tuple[float, float]] = Field(default_factory=list)
    safety: dict[str, Any] = Field(default_factory=dict)
    video: Literal["on", "off", "auto"] = "auto"
    detector: Literal["gt", "real"] = "gt"
    operator: Person
    teammates: list[Person] = Field(default_factory=list)
    assets: list[Asset]
    gazetteer: list[Gazetteer] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
    gt_detector: GtDetector = Field(default_factory=GtDetector)
    events: list[Event] = Field(default_factory=list)
    beats: list[Beat] = Field(default_factory=list)
    expect: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _overrides_disclosed(self) -> Scenario:
        for k in self.profile_overrides:
            if not any(k in d for d in self.disclosures):
                raise ValueError(f"profile_overrides.{k} must be disclosed in `disclosures`")
        return self

    def event(self, eid: str) -> Event | None:
        return next((e for e in self.events if e.id == eid), None)

    def asset(self, aid: str) -> Asset:
        return next(a for a in self.assets if a.id == aid)

    def place(self, name: str) -> Gazetteer:
        low = name.lower()
        for g in self.gazetteer:
            if g.name.lower() == low or low in (a.lower() for a in g.aliases):
                return g
        raise KeyError(f"unknown gazetteer name {name!r}")


class _Loader(yaml.SafeLoader):
    """YAML 1.2-style booleans: only true/false. Scenario keys use `on:` and `video: off`,
    which YAML 1.1 would turn into booleans."""


_Loader.yaml_implicit_resolvers = {
    k: [(tag, rx) for tag, rx in v if tag != "tag:yaml.org,2002:bool"]
    for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    __import__("re").compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF"))


def load_yaml(text: str):
    return yaml.load(text, Loader=_Loader)  # noqa: S506 - SafeLoader subclass


def load_scenario(path: str | Path) -> Scenario:
    data = load_yaml(Path(path).read_text())
    return Scenario.model_validate(data)
