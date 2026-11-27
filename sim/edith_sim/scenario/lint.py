"""``edith scenario lint [--beats]`` (sim spec §6, L15, C63, C88, C92).

An expect's lower bound (LB) is the first time its predicate can hold after its anchor, from
the deterministic pre-run plus the §6 latency table (compute latencies × ``max_speed``).
Predicates with no row in the table (window counts such as ``wire``, ``alerts``, ``router_log``,
``assoc_friend``, ``invariant_violations``) contribute LB 0. Gt mode predicates use the larger of
the table formula and the pre-run measurement. Lint fails when:

1. any ``within_s`` < LB, or < LB + 2 s when LB > 0;
2. a GT (or event) anchor never occurs in the pre-run;
3. an event references an unknown id, an expect uses ``by_t``, or a tasking ``say`` lacks
   ``cmd``;
4. with ``--beats``: a beat's anchor falls outside its window.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from edith_sim.scenario.model import Event, Scenario
from edith_sim.scenario.prerun import (
    ARM_S,
    EXPIRY_S,
    L_CARD,
    L_CMD,
    LOCKOUT_S,
    STOP_WORDS,
    TAK_LOST_S,
    PreRun,
    PreRunResult,
    is_tasking_say,
)

INF = math.inf
MARGIN_S = 2.0
EPS = 1e-6
ANCHOR_KEYS = {"after", "during", "global", "within_s"}
PREDICATES = {"proposal", "gt", "asset", "alert", "alerts", "cot", "tak", "router_log", "wire",
              "intent", "assoc_friend", "invariant_violations"}


@dataclass
class Row:
    idx: int
    label: str
    lb: float | None = None
    within: float | None = None
    ok: bool = True
    why: str = ""


@dataclass
class LintReport:
    path: str
    rows: list[Row] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    beats: list[Row] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and all(r.ok for r in self.rows + self.beats)

    def lines(self) -> list[str]:
        out = [f"{self.path}: {'OK' if self.ok else 'FAIL'}"]
        out += [f"  error: {e}" for e in self.errors]
        for r in self.rows:
            if r.lb is None:
                out.append(f"  {'ok ' if r.ok else 'BAD'} expect[{r.idx}] {r.label}  (window/global)"
                           + (f"  <- {r.why}" if r.why else ""))
                continue
            need = r.lb + (MARGIN_S if r.lb > 0 else 0.0)
            out.append(f"  {'ok ' if r.ok else 'BAD'} expect[{r.idx}] {r.label}: LB {r.lb:.1f}"
                       f" -> needs >= {need:.1f}, within_s {r.within:g}"
                       + (f"  <- {r.why}" if r.why else ""))
        for b in self.beats:
            out.append(f"  {'ok ' if b.ok else 'BAD'} beat {b.label}" +
                       (f"  <- {b.why}" if b.why else ""))
        return out


class Linter:
    def __init__(self, sc: Scenario, path: str = "<scenario>") -> None:
        self.sc, self.rep = sc, LintReport(path)
        self.pr = PreRun(sc)
        self.s = self.pr.s
        self.prof = self.pr.profile
        self.r: PreRunResult | None = None

    # -- rule 3 ---------------------------------------------------------------------------
    def static(self) -> None:
        ids = {e.id for e in self.sc.events}
        err = self.rep.errors
        for ev in self.sc.events:
            for k in ("card_shown", "event"):
                ref = (ev.on or {}).get(k)
                if ref is not None and ref not in ids:
                    err.append(f"event {ev.id}: on.{k} references unknown event {ref!r}")
            if ev.say and is_tasking_say(ev.say) and ev.cmd is None:
                err.append(f"event {ev.id}: tasking say {ev.say!r} lacks cmd")
            if ev.cmd is not None and ev.cmd.asset not in {a.id for a in self.sc.assets}:
                err.append(f"event {ev.id}: cmd.asset {ev.cmd.asset!r} unknown")
        for i, ex in enumerate(self.sc.expect):
            if "by_t" in ex:
                err.append(f"expect[{i}]: absolute by_t is not allowed")
            bad = set(ex) - ANCHOR_KEYS - PREDICATES - {"by_t"}
            if bad:
                err.append(f"expect[{i}]: unknown keys {sorted(bad)}")
            for ref in self._refs(ex):
                if ref not in ids:
                    err.append(f"expect[{i}]: references unknown event {ref!r}")
        for b in self.sc.beats:
            if b.window.after not in ids:
                err.append(f"beat {b.id}: window.after references unknown event "
                           f"{b.window.after!r}")

    @staticmethod
    def _refs(ex: dict) -> list[str]:
        out = []

        def one(a):
            if isinstance(a, str) and a != "end":
                out.append(a)
            elif isinstance(a, dict) and "event" in a:
                out.append(a["event"])

        one(ex.get("after"))
        d = ex.get("during")
        if isinstance(d, dict):
            one(d.get("from"))
            one(d.get("to"))
        return out

    # -- anchors --------------------------------------------------------------------------
    def anchor(self, a) -> tuple[float | None, Event | None, bool]:
        """(time, event, is_gt)."""
        r = self.r
        if isinstance(a, str):
            if a == "end":
                return self.sc.duration_s, None, False
            return r.event_t.get(a), self.sc.event(a), False
        if "gt" in a:
            return self.pr.gt_anchor(a, self.sc.duration_s), None, True
        t = r.event_t.get(a["event"])
        return (None if t is None else t + float(a.get("plus_s", 0.0))), \
            self.sc.event(a["event"]), False

    # -- rule 1 table ---------------------------------------------------------------------
    def _confirm_event(self, ev: Event) -> Event | None:
        return next((e for e in self.sc.events
                     if e.on and e.on.get("card_shown") == ev.id), None)

    def confirm_path(self, ev: Event | None) -> float:
        ce = self._confirm_event(ev) if ev is not None else None
        if ev is None or ev.cmd is None or ce is None:
            return INF
        return self.s * L_CARD + max(LOCKOUT_S, ce.after_s) + self.s * L_CMD

    def _is_stop(self, ev: Event | None) -> bool:
        if ev is None:
            return False
        return ev.touch == "triple_tap" or any(w in (ev.say or "").lower() for w in STOP_WORDS)

    def gt_lb(self, val: dict, ev: Event | None, t0: float) -> float:
        mode, alt_min = val.get("mode"), val.get("alt_agl_min")
        table = 0.0
        if ev is not None and ev.cmd is not None:
            alt = ev.cmd.alt_agl_m or self.prof["MIS_TAKEOFF_ALT"]
            climb = (alt_min if alt_min is not None else 0.9 * alt) / self.prof["MPC_TKO_SPEED"]
            table = self.confirm_path(ev) + ARM_S + climb
        elif ev is not None and ev.jam is not None:
            if mode in ("AUTO.RTL", "AUTO.LAND"):
                table = self.prof["COM_DL_LOSS_T"] + self.prof["COM_FAIL_ACT_T"]
            elif mode == "AUTO.LOITER":
                table = self.prof["COM_DL_LOSS_T"]
        elif self._is_stop(ev):
            table = self.s * L_CMD
        assets = val.get("asset")
        assets = assets if isinstance(assets, list) else [assets]
        meas = 0.0
        for a in assets:
            t = self.r.first_mode(a, t0, mode, alt_min)
            meas = max(meas, INF if t is None else t - t0)
        return max(table, meas)

    def predicate_lb(self, name: str, val, ev: Event | None, t0: float, is_gt: bool) -> float:
        s, gt_lat = self.s, self.sc.gt_detector.latency_ms / 1000.0
        if name == "proposal":
            st = val.get("state")
            if st == "dispatched":
                return self.confirm_path(ev)
            if st == "expired":
                p = self.r.proposals.get(ev.id) if ev else None
                return INF if (p is None or p.state != "expired") else s * L_CARD + EXPIRY_S
            return s * L_CARD
        if name == "gt":
            return self.gt_lb(val, ev, t0)
        if name == "asset":
            if val.get("link") == "lost":
                return self.prof["COM_DL_LOSS_T"]
            if "mode" in val:
                return self.gt_lb({"asset": val["id"], "mode": val["mode"]}, ev, t0) + s * L_CMD
            return 0.0
        if name == "alert":
            return gt_lat + s * L_CMD if is_gt else s * L_CARD
        if name == "cot":
            if val.get("how") == "h-e" or val.get("live") is False:
                return s * L_CMD
            if "type" in val:
                return gt_lat + s * L_CMD if is_gt else s * L_CMD
            return 0.0
        if name == "tak":
            return TAK_LOST_S if val.get("link") == "lost" else 0.0
        if name == "intent":
            return s * L_CMD
        return 0.0

    def check_expect(self, i: int, ex: dict) -> Row:
        preds = [k for k in ex if k in PREDICATES]
        if "global" in ex and isinstance(ex["global"], dict):
            preds += [k for k in ex["global"] if k in PREDICATES]
        if "after" not in ex:
            label = ("during " if "during" in ex else "global ") + "(" + ", ".join(preds) + ")"
            row = Row(i, label)
            d = ex.get("during")
            if isinstance(d, dict):
                for side in ("from", "to"):
                    t, _, _ = self.anchor(d.get(side, "end"))
                    if t is None:
                        row.ok, row.why = False, f"during.{side} anchor never occurs in the pre-run"
            return row
        a = ex["after"]
        t0, ev, is_gt = self.anchor(a)
        alabel = a if isinstance(a, str) else (
            f"{a['event']}+{a.get('plus_s', 0)}" if "event" in a
            else f"gt:{a.get('gt')} {a.get('asset')}/{a.get('entity', a.get('mode'))}")
        row = Row(i, f"after {alabel} ({', '.join(preds)})", within=float(ex.get("within_s", 0)))
        if t0 is None:
            row.lb, row.ok = INF, False
            row.why = ("GT anchor never occurs in the pre-run" if is_gt
                       else "anchor event never fires in the pre-run")
            return row
        row.lb = max([0.0] + [self.predicate_lb(p, ex[p], ev, t0, is_gt) for p in preds
                              if p in ex])
        need = row.lb + (MARGIN_S if row.lb > EPS else 0.0)
        if row.within + EPS < need:
            row.ok = False
            row.why = ("predicate never holds in the pre-run" if row.lb == INF else
                       f"within_s {row.within:g} < LB {row.lb:.2f}"
                       + (" + 2" if row.lb > EPS else ""))
        return row

    # -- rule 4 ---------------------------------------------------------------------------
    def beat_time(self, anchor: dict, ref_t: float) -> float | None:
        r = self.r
        if "alert_shown" in anchor:
            return r.alert_t.get(anchor["alert_shown"]["gt_entity"])
        if "gt" in anchor:
            g = anchor["gt"]
            if g == "asset_mode":
                return r.first_mode(anchor["asset"], ref_t, anchor["mode"])
            return self.pr.gt_anchor(anchor, self.sc.duration_s)
        if "asset_link" in anchor:
            al = anchor["asset_link"]
            ts = [t for t in r.link_lost_t.get(al["asset"], []) if t >= ref_t - EPS]
            return min(ts) if ts else None
        if "event" in anchor:
            return r.event_t.get(anchor["event"])
        raise ValueError(f"unknown beat anchor {anchor}")

    def check_beats(self) -> None:
        for b in self.sc.beats:
            ref_t = self.r.event_t.get(b.window.after)
            row = Row(0, f"{b.id} [{b.ref or 'from ' + b.window.after}]")
            t = None if ref_t is None else self.beat_time(b.anchor, ref_t)
            if t is None:
                row.ok, row.why = False, "anchor never occurs in the pre-run"
            else:
                d = t - ref_t
                row.label += f": {d:.1f} s in [{b.window.from_s:g}, {b.window.to_s:g}]"
                if not (b.window.from_s - EPS <= d <= b.window.to_s + EPS):
                    row.ok, row.why = False, "outside its window"
            self.rep.beats.append(row)

    def run(self, beats: bool = False) -> LintReport:
        self.static()
        self.r = self.pr.run()
        for i, ex in enumerate(self.sc.expect):
            self.rep.rows.append(self.check_expect(i, ex))
        if beats:
            if not self.sc.beats:
                self.rep.errors.append("--beats: scenario has no beats[]")
            self.check_beats()
        return self.rep


def lint_file(path: str, beats: bool = False) -> LintReport:
    from edith_sim.scenario.model import load_scenario

    try:
        sc = load_scenario(path)
    except Exception as e:  # noqa: BLE001 - report any load/validation error as a lint error
        rep = LintReport(str(path))
        rep.errors.append(f"load: {e}")
        return rep
    return Linter(sc, str(path)).run(beats)
