import hashlib
import json
from pathlib import Path

import pytest
from edith_common.px4 import encode as E
from edith_sim.linkshaper import jam_windows
from edith_sim.mock import InProcLink, MockVehicle
from edith_sim.mover import Mover
from edith_sim.profile import load_profile
from edith_sim.runner import AlertJoin, ScenarioRunner
from edith_sim.scenario.lint import Linter, lint_file
from edith_sim.scenario.model import load_scenario, load_yaml

ROOT = Path(__file__).resolve().parents[2]
SCEN = ROOT / "scenarios"
VIGNETTE = SCEN / "demo_vignette.yaml"


@pytest.fixture(scope="module")
def vignette_lint():
    lin = Linter(load_scenario(VIGNETTE), str(VIGNETTE))
    return lin, lin.run()


def test_yaml_on_is_a_string_key():
    assert load_yaml("on: {event: x}\nvideo: off\nok: true") == {
        "on": {"event": "x"}, "video": "off", "ok": True}


@pytest.mark.parametrize("path", sorted(SCEN.glob("*.yaml")), ids=lambda p: p.name)
def test_every_scenario_lints(path):
    rep = lint_file(str(path), beats=path.name == "demo_live.yaml")
    assert rep.ok, "\n".join(rep.lines())


def test_vignette_reproduces_sim7_bounds(vignette_lint):
    _, rep = vignette_lint
    lb = {r.idx: r.lb for r in rep.rows}
    expected = {0: 5.2, 1: 24.2, 2: 24.2, 3: 12.0, 6: 1.2, 10: 1.2, 12: 3.0, 13: 20.0,
                14: 25.0, 16: 1.2, 17: 1.2}
    for i, v in expected.items():
        assert lb[i] == pytest.approx(v, abs=0.05), (i, rep.rows[i])
    assert lb[15] == 0.0


def test_vignette_kinematics(vignette_lint):
    lin, _ = vignette_lint
    r = lin.r
    d1 = [(x["t"], x["mode"]) for x in r.traces["drone1"] if x["ev"] == "mode"]
    d2 = [(x["t"], x["mode"], x["reason"]) for x in r.traces["drone2"] if x["ev"] == "mode"]
    assert d1[0][1] == "AUTO.MISSION" and d1[1][1] == "AUTO.LOITER" and 260 <= d1[1][0] <= 290
    assert ("POSCTL.ORBIT" in [m for _, m, _ in d2])
    hold = next(t for t, m, why in d2 if why == "dll_hold")
    rtl = next(t for t, m, why in d2 if why == "dll_action")
    assert rtl - hold == pytest.approx(5.0) and 318 <= hold <= 321
    stop = next(t for t, m, why in d2 if why == "cmd" and m == "AUTO.LOITER")
    assert stop == pytest.approx(351.2)
    assert r.alert_t["veh-7"] < 280 and "deer-1" in r.alert_t


def test_infeasible_copy_fails_naming_the_expect():
    rep = lint_file(str(SCEN / "tests" / "infeasible_vignette.yaml"))
    assert not rep.ok
    bad = [r for r in rep.rows if not r.ok]
    assert [r.idx for r in bad] == [2]
    assert "expect[2] after ovw" in "\n".join(rep.lines())


def test_lint_rule3_and_rule2(tmp_path):
    sc = load_yaml(VIGNETTE.read_text())
    sc["events"][1]["on"] = {"card_shown": "nope"}
    sc["events"].append({"id": "x", "t": 5, "say": "drone two orbit nai two"})
    sc["expect"].append({"after": "scout", "by_t": 10, "proposal": {"state": "dispatched"}})
    sc["expect"].append({"after": {"gt": "entity_in_fov", "asset": "drone2", "entity": "deer-1",
                                   "min_dwell_s": 300}, "within_s": 5, "alert": {}})
    p = tmp_path / "bad.yaml"
    p.write_text(json.dumps(sc))
    rep = lint_file(str(p))
    txt = "\n".join(rep.lines())
    assert "unknown event 'nope'" in txt and "lacks cmd" in txt and "by_t" in txt
    assert "GT anchor never occurs" in txt


def test_beats_outside_window_fail(tmp_path):
    sc = load_yaml((SCEN / "demo_live.yaml").read_text())
    for b in sc["beats"]:
        if b["id"] == "jam_lost":
            b["window"]["to_s"] = 7
    p = tmp_path / "live.yaml"
    p.write_text(json.dumps(sc))
    rep = lint_file(str(p), beats=True)
    assert not rep.ok and any("jam_lost" in r.label and not r.ok for r in rep.beats)


def _mock_trace(seed: int) -> str:
    v = MockVehicle(load_profile(), 0, seed=seed, telemetry=True)
    L = InProcLink(v)
    L.heartbeat(0)
    L.command(E.arm(L.mav, 1), 0.5)
    L.command(E.takeoff(L.mav, 1, 270), 1.0)
    for k in range(2, 30):
        L.heartbeat(k)
        L.recv()
    L.command(E.rtl(L.mav, 1), 30)
    v.advance(80)  # silence → no DLL while in RTL already; then landing
    return v.trace_sha256()


def _det_hash(seed: int) -> str:
    sc = load_scenario(VIGNETTE)
    sc.seed = seed
    jam = [w.__dict__ for e in sc.events if e.jam for w in jam_windows(e.t, e.jam.duration_s,
                                                                         e.jam.links)]
    h = hashlib.sha256()
    h.update(Mover(sc).sha256().encode())
    h.update(json.dumps(jam, sort_keys=True).encode())
    h.update(_mock_trace(seed).encode())
    return h.hexdigest()


def test_same_seed_identical_sha256():
    assert _det_hash(7) == _det_hash(7)
    sc = load_scenario(VIGNETTE)
    assert Mover(sc, 7).sha256() != Mover(sc, 8).sha256()  # the deer loiter phase is seeded


class StubGlasses:
    def __init__(self):
        self.said, self.touched, self._card, self._alert = [], [], None, None

    def say(self, text):
        self.said.append(text)

    def touch(self, kind, duration_ms=None):
        self.touched.append(kind)

    def on_card_shown(self, cb):
        self._card = cb

    def on_alert_shown(self, cb):
        self._alert = cb


class StubLinks:
    def __init__(self):
        self.jams = []

    def jam(self, t_s, duration_s, links):
        self.jams.append((t_s, duration_s, links))


def test_runner_seams(tmp_path):
    sc = load_scenario(VIGNETTE)
    ev, dets = tmp_path / "eventlog.jsonl", tmp_path / "gt_dets_0.jsonl"
    dets.write_text("".join(json.dumps({"det_id": f"d{i}", "entity_id": "deer-1"}) + "\n"
                            for i in range(3)))
    ev.write_text(json.dumps({"type": "alert.created", "body": {"alert_id": "a1",
                                                               "track_id": "t1"}}) + "\n"
                  + '{"type": "track.update", "body": {"track_id": "t1"')  # partial line
    g, links = StubGlasses(), StubLinks()
    run = ScenarioRunner(sc, g, links, AlertJoin(ev, [dets]))
    run.tick(30)
    assert g.said == ["drone one scout nai one"]
    g._card("prop-1")
    run.tick(31.9)
    assert g.said[-1] != "confirm"
    run.tick(32.0)
    assert g.said[-1] == "confirm"
    g._alert("a1")  # track.update not complete yet → re-polled later
    run.tick(80)
    assert "dismiss" not in g.said
    with ev.open("a") as fh:
        fh.write(', "det_ids": ["d0", "d1", "d2"]}}\n')
    run.tick(81)
    run.tick(84.1)
    assert g.said[-1] == "dismiss"
    run.tick(300)
    assert links.jams == [(300, 25.0, ["mavlink:drone2", "tak:*"])]
    run.tick(350)
    assert g.touched == ["triple_tap"]


def test_runner_gt_anchor_and_live_mode():
    sc = load_scenario(SCEN / "demo_live.yaml")
    g, links = StubGlasses(), StubLinks()
    run = ScenarioRunner(sc, g, links, headless=False)
    run.tick(10)
    assert g.said == []  # live: the operator speaks, the runner does not
    run.on_gt("asset_mode", asset="drone2", mode="POSCTL.ORBIT")
    run.tick(170)
    assert links.jams and links.jams[0][1] == 25.0
