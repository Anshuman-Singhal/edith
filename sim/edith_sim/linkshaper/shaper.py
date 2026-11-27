"""Link shaper core: scheduled impairment windows + the MAVLink wire log (sim spec §3, C50).

Links are named ``mavlink:<asset>``, ``tak:<peer>`` and ``video:<asset>``; a window's ``link``
is an fnmatch glob (``tak:*``). Every MAVLink message in both directions is written to the wire
log as ``{t_sim_ms, dir, asset, msgid, name, class, dropped}``; ``dir`` is ``up`` (companion →
vehicle) or ``down`` (vehicle → companion). Uplink ``class`` comes from
``edith_common.px4.classify`` (MOTION / SAFE / CONFIG / null = would be blocked); downlink
messages are ``TELEM``. The truth tap is never impaired (the UDP relay copies before shaping).
"""

from __future__ import annotations

import fnmatch
import json
import random
from dataclasses import dataclass
from pathlib import Path

from edith_common.px4.classify import classify
from pymavlink.dialects.v20 import common as mavlink


@dataclass(frozen=True)
class Window:
    link: str
    start_s: float
    end_s: float
    drop: float = 1.0  # probability; 1.0 = partition
    delay_ms: float = 0.0
    bw_bps: float | None = None

    def active(self, link: str, t: float) -> bool:
        return self.start_s <= t < self.end_s and fnmatch.fnmatchcase(link, self.link)


def jam_windows(t: float, duration_s: float, links: list[str]) -> list[Window]:
    """A scenario ``jam{duration_s, links}`` event → full-drop windows."""
    return [Window(link, t, t + duration_s) for link in links]


class WireLog:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else None
        self.records: list[dict] = []
        self._fh = None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = self.path.open("a", buffering=1)

    def write(self, rec: dict) -> None:
        self.records.append(rec)
        if self._fh:
            self._fh.write(json.dumps(rec, sort_keys=True) + "\n")

    def close(self) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None


class Shaper:
    def __init__(self, windows: list[Window] | None = None, seed: int = 0,
                 wire_log: WireLog | None = None) -> None:
        self.windows: list[Window] = list(windows or [])
        self.rng = random.Random(seed)
        self.wire = wire_log or WireLog()
        self._parsers: dict[tuple[str, str], mavlink.MAVLink] = {}
        self._bucket: dict[tuple[str, str], tuple[float, float]] = {}
        self.stats = {"passed": 0, "dropped": 0}

    def add(self, *ws: Window) -> None:
        self.windows.extend(ws)

    def active(self, link: str, t: float) -> list[Window]:
        """Active windows for a link (cameras query ``video:<asset>`` with this)."""
        return [w for w in self.windows if w.active(link, t)]

    def _parse(self, link: str, direction: str, data: bytes) -> list:
        key = (link, direction)
        p = self._parsers.get(key)
        if p is None:
            p = self._parsers[key] = mavlink.MAVLink(None)
            p.robust_parsing = True
        return [m for m in (p.parse_buffer(data) or []) if m.get_type() != "BAD_DATA"]

    def _decide(self, link: str, direction: str, size: int, t: float) -> tuple[bool, float]:
        drop, delay = False, 0.0
        for w in self.active(link, t):
            if w.drop >= 1.0 or (w.drop > 0 and self.rng.random() < w.drop):
                drop = True
            delay = max(delay, w.delay_ms / 1000.0)
            if w.bw_bps:
                key = (link, direction)
                tokens, last = self._bucket.get(key, (w.bw_bps / 8.0, t))
                tokens = min(w.bw_bps / 8.0, tokens + (t - last) * w.bw_bps / 8.0)
                if tokens < size:
                    drop = True
                else:
                    tokens -= size
                self._bucket[key] = (tokens, t)
        return drop, delay

    def process(self, link: str, direction: str, data: bytes,
                t: float) -> list[tuple[float, bytes]]:
        """Shape one datagram at sim time ``t``; return ``[(deliver_t, bytes)]`` (0 or 1)."""
        drop, delay = self._decide(link, direction, len(data), t)
        if link.startswith("mavlink:"):
            asset = link.split(":", 1)[1]
            for m in self._parse(link, direction, data):
                cls = classify(m) if direction == "up" else "TELEM"
                self.wire.write({"t_sim_ms": int(round(t * 1000)), "dir": direction,
                                 "asset": asset, "msgid": m.get_msgId(), "name": m.get_type(),
                                 "class": cls, "dropped": drop})
        self.stats["dropped" if drop else "passed"] += 1
        return [] if drop else [(t + delay, data)]
