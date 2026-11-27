"""Scenario runner skeleton with the FakeGlasses seams (sim spec §5.1, C87).

The runner is the only thing that executes ``say`` / ``touch``, and it resolves
``alert_shown{gt_entity}`` anchors through the alert-to-entity join. WS-B's
``tools/edith_tools/fake_glasses.py`` implements ``GlassesPort``; the supervisor (WS-B) wires
``LinkControl`` to the linkshaper and feeds GT events (``on_gt``) from simd.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from edith_sim.scenario.model import Event, Scenario


class GlassesPort(Protocol):
    """What the runner needs from FakeGlasses (WS-B)."""

    def say(self, text: str) -> None: ...  # ptt_down{held_ms 300, ctx} → session.start → text → ptt_up
    def touch(self, kind: str, duration_ms: int | None = None) -> None: ...
    def on_card_shown(self, cb: Callable[[str], None]) -> None: ...  # cb(proposal_id)
    def on_alert_shown(self, cb: Callable[[str], None]) -> None: ...  # cb(alert_id)


class LinkControl(Protocol):
    def jam(self, t_s: float, duration_s: float, links: list[str]) -> None: ...


def _read_jsonl(path: Path) -> list[dict]:
    """Read complete lines only: a partial last line (writer mid-write) is ignored."""
    if not path.exists():
        return []
    out = []
    text = path.read_text()
    lines = text.split("\n")
    if not text.endswith("\n"):
        lines = lines[:-1]
    for ln in lines:
        if ln.strip():
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
    return out


class AlertJoin:
    """alert_id → GT entity by majority ``det_id`` of the alert's track (read-only, no truth
    enters the companion). Re-polls the files until ``track.update`` arrives (architect r4 nit 3)."""

    def __init__(self, eventlog: Path, gt_dets: list[Path]) -> None:
        self.eventlog, self.gt_dets = Path(eventlog), [Path(p) for p in gt_dets]

    @staticmethod
    def _kind_body(rec: dict) -> tuple[str, dict]:
        kind = rec.get("type") or rec.get("kind") or rec.get("event") or ""
        return kind, rec.get("body", rec)

    def entity_for(self, alert_id: str) -> str | None:
        track = None
        dets: list[str] = []
        for rec in _read_jsonl(self.eventlog):
            kind, b = self._kind_body(rec)
            if kind == "alert.created" and b.get("alert_id") == alert_id:
                track = b.get("track_id")
        if track is None:
            return None
        for rec in _read_jsonl(self.eventlog):
            kind, b = self._kind_body(rec)
            if kind == "track.update" and b.get("track_id") == track:
                dets += [str(d) for d in b.get("det_ids", [])]
        if not dets:
            return None
        truth = {}
        for p in self.gt_dets:
            for rec in _read_jsonl(p):
                truth[str(rec.get("det_id"))] = rec.get("entity_id")
        votes = Counter(truth.get(d) for d in dets if d in truth)
        if not votes:
            return None
        ent, _ = votes.most_common(1)[0]
        return ent


class ScenarioRunner:
    def __init__(self, sc: Scenario, glasses: GlassesPort, links: LinkControl | None = None,
                 join: AlertJoin | Callable[[str], str | None] | None = None,
                 headless: bool = True) -> None:
        self.sc, self.g, self.links, self.headless = sc, glasses, links, headless
        self._join = join.entity_for if isinstance(join, AlertJoin) else join
        self.fired: dict[str, float] = {}
        self._due: list[tuple[float, Event]] = [(e.t, e) for e in sc.events if e.t is not None]
        self._last_tasking: list[str] = []  # tasking event ids awaiting a card
        self._card_event: dict[str, str] = {}  # proposal_id → event id
        self._pending_alerts: list[str] = []
        self._now = 0.0
        self.log: list[tuple[float, str, str]] = []
        glasses.on_card_shown(self._card_shown)
        glasses.on_alert_shown(self._alert_shown)

    # seams -------------------------------------------------------------------------------
    def _card_shown(self, proposal_id: str) -> None:
        if proposal_id not in self._card_event and self._last_tasking:
            self._card_event[proposal_id] = self._last_tasking.pop(0)
            self._trigger("card_shown", self._card_event[proposal_id])

    def _alert_shown(self, alert_id: str) -> None:
        self._pending_alerts.append(alert_id)
        self._resolve_alerts()

    def _resolve_alerts(self) -> None:
        still = []
        for aid in self._pending_alerts:
            ent = self._join(aid) if self._join else None
            if ent is None:
                still.append(aid)
            else:
                self._trigger("alert_shown", ent)
        self._pending_alerts = still

    def on_gt(self, kind: str, **kw) -> None:
        """GT feed: ``asset_mode(asset, mode)`` / ``entity_in_fov(asset, entity, dwell_s)``."""
        for ev in self.sc.events:
            if ev.on is None or "gt" not in ev.on or ev.id in self.fired or \
                    ev.id in {e.id for _, e in self._due}:
                continue
            on = ev.on
            if on["gt"] != kind:
                continue
            if kind == "asset_mode" and on.get("asset") == kw.get("asset") and \
                    on.get("mode") == kw.get("mode"):
                self._due.append((self._now + ev.after_s, ev))
            elif kind == "entity_in_fov" and on.get("asset") == kw.get("asset") and \
                    on.get("entity") == kw.get("entity") and \
                    kw.get("dwell_s", 0) >= on.get("min_dwell_s", 0):
                self._due.append((self._now + ev.after_s, ev))

    # scheduling --------------------------------------------------------------------------
    def _trigger(self, kind: str, key: str) -> None:
        for ev in self.sc.events:
            if ev.on is None or ev.id in self.fired:
                continue
            v = ev.on.get(kind)
            if (kind == "alert_shown" and isinstance(v, dict) and v.get("gt_entity") == key) \
                    or (kind != "alert_shown" and v == key):
                if all(e.id != ev.id for _, e in self._due):
                    self._due.append((self._now + ev.after_s, ev))

    def tick(self, now_s: float) -> None:
        self._now = now_s
        self._resolve_alerts()
        due = sorted([d for d in self._due if d[0] <= now_s + 1e-9], key=lambda d: d[0])
        self._due = [d for d in self._due if d[0] > now_s + 1e-9]
        for _, ev in due:
            self._fire(ev, now_s)

    def _fire(self, ev: Event, now_s: float) -> None:
        self.fired[ev.id] = now_s
        if ev.jam is not None:
            if self.links is not None:
                self.links.jam(now_s, ev.jam.duration_s, ev.jam.links)
            self.log.append((now_s, ev.id, "jam"))
        elif ev.say is not None or ev.touch is not None:
            if not self.headless:
                self.log.append((now_s, ev.id, "skipped (live)"))
            elif ev.say is not None:
                self.g.say(ev.say)
                self.log.append((now_s, ev.id, f"say {ev.say!r}"))
            else:
                self.g.touch(ev.touch)
                self.log.append((now_s, ev.id, f"touch {ev.touch}"))
            if ev.cmd is not None:
                self._last_tasking.append(ev.id)
        self._trigger("event", ev.id)

    @property
    def done(self) -> bool:
        return not self._due and all(e.id in self.fired for e in self.sc.events if e.t is not None)
