"""Deterministic in-process pre-run (sim spec §6, C88).

Steps the seeded mover and one in-process MockVehicle per asset (dt 20 ms, trapezoidal corners)
through the scenario's events, flying each tasking event's ``cmd`` with the shared
``edith_common.px4.plan_search``. The companion is not run: its latencies come from the §6
table (compute latencies × lint speed ``s``; profile kinematics, lockout, expiry, ``after_s``
in sim seconds):

- card shown = say + s·L_card; dispatch = card + max(lockout, confirm − card) + s·L_cmd;
- the next composed step (takeoff / MISSION_START) follows the arm by ARM_S; orbit is sent once
  alt ≥ 0.9 × target (C09);
- an alert is shown ``ALERT_DWELL_S`` after an entity enters a drone's FOV, + gt latency +
  s·L_card; a stop holds every asset at stop + s·L_cmd;
- the companion's link view goes ``lost`` COM_DL_LOSS_T after a MAVLink jam starts.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from functools import partial

from edith_common.geo import enu_to_lla
from edith_common.px4 import encode as E
from edith_common.px4 import modes as M
from edith_common.px4.search import plan_search, square

from edith_sim.gt import FovTracker, in_fov
from edith_sim.linkshaper.shaper import Window, jam_windows
from edith_sim.mock import DT, InProcLink, MockVehicle
from edith_sim.mover import Mover
from edith_sim.profile import load_profile
from edith_sim.scenario.model import Cmd, Event, Scenario

L_CARD, L_CMD = 0.5, 0.3  # wall s, × lint speed
LOCKOUT_S, EXPIRY_S = 0.6, 10.0
ARM_S = 1.0
ALERT_DWELL_S = 3.0
TAK_LOST_S = 3.0
CONFIRM_WORDS = ("confirm",)
CANCEL_WORDS = ("cancel",)
STOP_WORDS = ("abort", "all stop", "all hold", "stop")
TASK_VERBS = ("scout", "overwatch", "orbit", "search", "observe", "goto", "go to", "follow",
              "take off", "takeoff", "launch", "land", "return", "rtl", "watch area")


def is_tasking_say(text: str) -> bool:
    low = text.lower()
    return low.startswith(("drone", "all drones")) and any(v in low for v in TASK_VERBS)


@dataclass
class Proposal:
    event: str
    cmd: Cmd
    card_t: float
    state: str = "await"  # await | dispatched | expired | cancelled
    dispatch_t: float | None = None


@dataclass
class PreRunResult:
    speed: float
    event_t: dict[str, float] = field(default_factory=dict)
    card_t: dict[str, float] = field(default_factory=dict)
    proposals: dict[str, Proposal] = field(default_factory=dict)
    alert_t: dict[str, float] = field(default_factory=dict)
    link_lost_t: dict[str, list[float]] = field(default_factory=dict)
    jams: list[Window] = field(default_factory=list)
    samples: dict[str, list[tuple[float, str, float]]] = field(default_factory=dict)
    fov: FovTracker = field(default_factory=FovTracker)
    traces: dict[str, list[dict]] = field(default_factory=dict)
    gt_anchor_t: dict[str, float] = field(default_factory=dict)

    def first_mode(self, asset: str, t_from: float, mode: str | None = None,
                   alt_min: float | None = None) -> float | None:
        for t, m, u in self.samples.get(asset, []):
            if t + 1e-9 < t_from:
                continue
            if (mode is None or m == mode) and (alt_min is None or u >= alt_min - 1e-6):
                return t
        return None



def _cmd_at(link: InProcLink, msg, t: float) -> None:
    link.command(msg, t)


class PreRun:
    def __init__(self, sc: Scenario, speed: float | None = None) -> None:
        self.sc = sc
        self.s = sc.max_speed if speed is None else speed
        self.profile = load_profile(sc.vehicle_profile, sc.profile_overrides)
        self.origin = sc.origin.to_origin()
        self.mover = Mover(sc)
        self.vehicles: dict[str, MockVehicle] = {}
        self.links: dict[str, InProcLink] = {}
        for a in sc.assets:
            v = MockVehicle(self.profile, a.instance, self.origin, (a.spawn.e, a.spawn.n),
                            sc.seed, telemetry=False)
            self.vehicles[a.id] = v
            self.links[a.id] = InProcLink(v)
        self.r = PreRunResult(self.s, samples={a.id: [] for a in sc.assets})
        self._q: list = []
        self._n = 0
        self._pending_orbit: dict[str, dict] = {}
        self._fired: set[str] = set()
        self._alerted: set[str] = set()
        self._last_proposal: Proposal | None = None

    # -- scheduling -----------------------------------------------------------------------
    def _at(self, t: float, fn, *args) -> None:
        self._n += 1
        heapq.heappush(self._q, (t, self._n, fn, args))

    def _trigger(self, kind: str, key, t: float) -> None:
        for ev in self.sc.events:
            if ev.on is None or ev.id in self._fired:
                continue
            on = ev.on
            hit = ((kind == "card_shown" and on.get("card_shown") == key)
                   or (kind == "event" and on.get("event") == key)
                   or (kind == "alert_shown" and isinstance(on.get("alert_shown"), dict)
                       and on["alert_shown"].get("gt_entity") == key))
            if hit:
                self._fired.add(ev.id)
                self._at(t + ev.after_s, self._fire, ev)

    def _check_gt_triggers(self, t: float) -> None:
        for ev in self.sc.events:
            if ev.on is None or "gt" not in ev.on or ev.id in self._fired:
                continue
            ta = self.gt_anchor(ev.on, t)
            if ta is not None:
                self._fired.add(ev.id)
                self.r.gt_anchor_t[ev.id] = ta
                self._at(ta + ev.after_s, self._fire, ev)

    def gt_anchor(self, spec: dict, t_now: float) -> float | None:
        """GT anchor ``{gt: asset_mode|entity_in_fov, …}`` (or ``gt: {kind: …}``) time so far."""
        g = spec["gt"]
        if isinstance(g, str):
            kind, args = g, spec
        elif "kind" in g:
            kind, args = g["kind"], g
        else:
            kind, args = next(iter(g.items()))
        if kind == "asset_mode":
            return self.r.first_mode(args["asset"], 0.0, args["mode"])
        if kind == "entity_in_fov":
            return self.dwell_t(args["asset"], args["entity"], args.get("min_dwell_s", 0.0))
        raise ValueError(f"unknown gt anchor {kind!r}")

    def dwell_t(self, asset: str, entity: str, min_dwell: float) -> float | None:
        t = self.r.fov.first_dwell(asset, entity, min_dwell)
        cur = self.r.fov.open.get((asset, entity))
        if t is None and cur is not None and self._t - cur["t_enter"] >= min_dwell - 1e-9:
            t = cur["t_enter"] + min_dwell
        return t

    # -- actions --------------------------------------------------------------------------
    def _fire(self, t: float, ev: Event) -> None:
        self.r.event_t[ev.id] = t
        if ev.jam:
            ws = jam_windows(t, ev.jam.duration_s, ev.jam.links)
            self.r.jams += ws
            for a in self.sc.assets:
                if any(w.active(f"mavlink:{a.id}", t) for w in ws):
                    self.r.link_lost_t.setdefault(a.id, []).append(
                        t + self.profile["COM_DL_LOSS_T"])
        text = (ev.say or "").lower()
        if ev.cmd is not None:
            self._propose(t, ev)
        elif ev.on and "card_shown" in ev.on and (any(w in text for w in CONFIRM_WORDS)
                                                   or ev.touch):
            self._confirm(t, ev.on["card_shown"])
        elif any(w in text for w in CANCEL_WORDS) and self._last_proposal:
            if self._last_proposal.state == "await":
                self._last_proposal.state = "cancelled"
        elif ev.touch == "triple_tap" or any(w in text for w in STOP_WORDS):
            self._at(t + self.s * L_CMD, self._hold_all)
        self._trigger("event", ev.id, t)

    def _propose(self, t: float, ev: Event) -> None:
        card = t + self.s * L_CARD
        p = Proposal(ev.id, ev.cmd, card)
        self.r.proposals[ev.id] = p
        self._last_proposal = p
        self._at(card, self._card, p)
        self._at(card + EXPIRY_S, self._expire, p)

    def _card(self, t: float, p: Proposal) -> None:
        self.r.card_t[p.event] = t
        self._trigger("card_shown", p.event, t)

    def _expire(self, t: float, p: Proposal) -> None:
        if p.state == "await":
            p.state = "expired"

    def _confirm(self, t: float, eid: str) -> None:
        p = self.r.proposals.get(eid)
        if p is None or p.state != "await" or t > p.card_t + EXPIRY_S:
            return
        p.state = "dispatched"
        p.dispatch_t = p.card_t + max(LOCKOUT_S, t - p.card_t) + self.s * L_CMD
        self._at(p.dispatch_t, self._dispatch, p)

    def _target_en(self, cmd: Cmd, t: float) -> tuple[float, float]:
        tg = cmd.target
        if tg.get("self"):
            e, n, _ = self.mover.operator(t)
            return e, n
        if "named" in tg:
            g = self.sc.place(tg["named"])
            return g.e, g.n
        return float(tg["e"]), float(tg["n"])

    def _lla(self, e: float, n: float) -> tuple[float, float]:
        lat, lon, _ = enu_to_lla(e, n, 0.0, self.origin)
        return lat, lon

    def _dispatch(self, t: float, p: Proposal) -> None:
        cmd, link = p.cmd, self.links[p.cmd.asset]
        v, mav, ts = link.v, link.mav, link.tsys
        alt = cmd.alt_agl_m or self.profile["MIS_TAKEOFF_ALT"]
        steps = cmd.steps
        te, tn = self._target_en(cmd, t)
        if "search" in steps:
            g = self.sc.place(cmd.target["named"])
            poly = square(g.e, g.n, g.area_m or 300.0)
            wps = [(*self._lla(e, n), a) for e, n, a in plan_search(poly, alt)]
            items = E.search_mission(wps, alt if v.landed else None)
            link.upload(items, t)
            if v.landed:
                link.command(E.arm(mav, ts), t)
                self._at(t + ARM_S, partial(_cmd_at, link, E.mission_start(mav, ts)))
            else:
                link.command(E.mission_start(mav, ts), t)
            return
        lat, lon = self._lla(te, tn)
        amsl = self.origin.alt_msl_m + alt
        if any(s in steps for s in ("orbit", "observe")):
            radius = cmd.radius_m or 50.0
            msg = E.orbit(mav, ts, lat, lon, amsl, radius, self.profile["orbit_vel_mps"])
        elif "goto" in steps:
            msg = E.reposition(mav, ts, lat, lon, amsl)
        elif "rtl" in steps:
            msg = E.rtl(mav, ts)
        elif "land" in steps:
            msg = E.land(mav, ts)
        else:
            msg = None
        send = None if msg is None else partial(link.command, msg)
        if v.landed and ("takeoff" in steps or send is not None):
            link.command(E.arm(mav, ts), t)
            self._at(t + ARM_S, partial(_cmd_at, link, E.takeoff(mav, ts, amsl)))
            if send is not None:
                self._pending_orbit[cmd.asset] = {"send": send, "alt": 0.9 * alt}
        elif send is not None:
            send(t)

    def _hold_all(self, t: float) -> None:
        for link in self.links.values():
            link.command(E.hold(link.mav, link.tsys), t)

    # -- main loop ------------------------------------------------------------------------
    def run(self) -> PreRunResult:
        sc = self.sc
        for ev in sc.events:
            if ev.t is not None:
                self._fired.add(ev.id)
                self._at(ev.t, self._fire, ev)
        n_ticks = int(round(sc.duration_s / DT))
        next_hb = 0.0
        for k in range(n_ticks + 1):
            t = k * DT
            self._t = t
            while self._q and self._q[0][0] <= t + 1e-9:
                tq, _, fn, args = heapq.heappop(self._q)
                fn(tq, *args)
            if t >= next_hb - 1e-9:
                next_hb += 1.0
                for aid, link in self.links.items():
                    link.up = not any(w.active(f"mavlink:{aid}", t) for w in self.r.jams)
                    link.heartbeat(t)
                    link.up = True
            for aid, v in self.vehicles.items():
                v.advance(t)
                self.links[aid].recv()
                po = self._pending_orbit.get(aid)
                if po and v.in_air and v.u >= po["alt"] - 1e-6:
                    del self._pending_orbit[aid]
                    po["send"](t)
                self.r.samples[aid].append((t, v.mode_name, v.u))
            self._fov(t)
            self._check_gt_triggers(t)
        self.r.fov.finish(sc.duration_s)
        self.r.traces = {aid: v.trace for aid, v in self.vehicles.items()}
        return self.r

    def _fov(self, t: float) -> None:
        ents = self.mover.entities(t)
        for a in self.sc.assets:
            v = self.vehicles[a.id]
            for eid, (e, n, _) in ents.items():
                seen = v.in_air and v.u > 5 and in_fov(v.e, v.n, v.u, v.heading, a.camera, e, n)
                rng = math.dist((v.e, v.n, v.u), (e, n, 0.0))
                self.r.fov.update(t, a.id, eid, seen, rng)
                cur = self.r.fov.open.get((a.id, eid))
                if (cur and eid not in self._alerted
                        and t - cur["t_enter"] >= ALERT_DWELL_S - 1e-9):
                    self._alerted.add(eid)
                    ta = (t + self.sc.gt_detector.latency_ms / 1000.0 + self.s * L_CARD)
                    self.r.alert_t[eid] = ta
                    self._trigger("alert_shown", eid, ta)


def prerun(sc: Scenario, speed: float | None = None) -> PreRunResult:
    return PreRun(sc, speed).run()


__all__ = ["ALERT_DWELL_S", "ARM_S", "EXPIRY_S", "LOCKOUT_S", "L_CARD", "L_CMD", "M",
           "PreRun", "PreRunResult", "TAK_LOST_S", "is_tasking_say", "prerun"]
