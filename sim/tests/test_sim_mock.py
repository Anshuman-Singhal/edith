import math

import pytest
from edith_common.geo import enu_to_lla
from edith_common.px4 import encode as E
from edith_common.px4 import modes as M
from edith_sim.mock import InProcLink, MockVehicle
from edith_sim.profile import load_profile


@pytest.fixture
def vl():
    v = MockVehicle(load_profile(), instance=0, seed=1)
    return v, InProcLink(v)


def modes_of(v):
    return [x["mode"] for x in v.trace if x["ev"] == "mode"]


def fly_up(v, L, t=0.0, alt=60.0):
    L.heartbeat(t)
    assert L.command(E.arm(L.mav, L.tsys), t) == 0
    assert L.command(E.takeoff(L.mav, L.tsys, v.origin.alt_msl_m + alt), t) == 0
    for k in range(int(t) + 1, int(t) + 26):
        L.heartbeat(k)
    assert v.mode == M.AUTO_LOITER and v.u == pytest.approx(alt)
    return int(t) + 25


def lla(v, e, n):
    lat, lon, _ = enu_to_lla(e, n, 0, v.origin)
    return lat, lon


def test_heartbeat_identity(vl):
    v, L = vl
    v.telemetry_on = True
    v.advance(1.0)
    hb = [m for m in L.recv() if m.get_type() == "HEARTBEAT"]
    assert hb and hb[0].autopilot == 12 and hb[0].type == 2
    assert hb[0].get_srcSystem() == 1 and hb[0].custom_mode == M.AUTO_LOITER
    types = {m.get_type() for m in L.received}
    assert {"GLOBAL_POSITION_INT", "ATTITUDE", "SYS_STATUS", "EXTENDED_SYS_STATE"} <= types


def test_orbit_and_reposition_modes(vl):
    v, L = vl
    t = fly_up(v, L)
    lat, lon = lla(v, 100, 0)
    assert L.command(E.orbit(L.mav, 1, lat, lon, 270, 50), t) == 0
    assert v.mode == M.POSCTL_ORBIT
    for k in range(t, t + 60):
        L.heartbeat(k)
    assert math.dist((v.e, v.n), (100, 0)) == pytest.approx(50, abs=1.0)
    lat, lon = lla(v, 0, 50)
    assert L.command(E.reposition(L.mav, 1, lat, lon, 260), t + 60) == 0
    assert v.mode == M.AUTO_LOITER
    for k in range(t + 60, t + 90):
        L.heartbeat(k)
    assert (v.e, v.n) == pytest.approx((0, 50), abs=0.1) and v.u == pytest.approx(50)
    assert E.goto_completed(math.dist((v.e, v.n), (0, 50)), v.mode)


def test_rtl_land_disarm(vl):
    v, L = vl
    t = fly_up(v, L)
    assert L.command(E.rtl(L.mav, 1), t) == 0
    for k in range(t, t + 100):
        L.heartbeat(k)
    assert modes_of(v)[-2:] == ["AUTO.RTL", "AUTO.LAND"]
    assert v.landed and not v.armed
    assert [x["ev"] for x in v.trace if x["ev"] in ("landed", "disarmed")] == ["landed", "disarmed"]


def test_land_command_and_ground_denials(vl):
    v, L = vl
    L.heartbeat(0)
    assert L.command(E.orbit(L.mav, 1, 40.07, -88.63, 270, 50), 0) == E.RESULT_DENIED
    assert L.command(E.takeoff(L.mav, 1, 270), 0) == E.RESULT_DENIED  # not armed
    t = fly_up(v, L, 1)
    assert L.command(E.land(L.mav, 1), t) == 0 and v.mode == M.AUTO_LAND


def test_armed_idle_disarms_at_10s(vl):
    v, L = vl
    L.heartbeat(0)
    L.command(E.arm(L.mav, 1), 0.0)
    v.advance(9.9)
    assert v.armed
    v.advance(10.02)
    assert not v.armed
    last = [x for x in v.trace if x["ev"] != "pose"][-1]
    assert last["ev"] == "disarmed" and last["reason"] == "auto_disarm_preflight"


def test_disarmed_takes_no_dll_action(vl):
    v, L = vl
    L.heartbeat(0)
    v.advance(120)
    assert modes_of(v) == [] and v.mode == M.AUTO_LOITER


def test_dll_hold_then_rtl_persists_then_hold_accepted(vl):
    v, L = vl
    lat, lon = lla(v, 200, 0)
    t = fly_up(v, L)  # last heartbeat at t
    L.command(E.reposition(L.mav, 1, lat, lon, 270), t)  # away from home so RTL lasts
    v.advance(t + 20 + 4.9)
    assert v.mode == M.AUTO_LOITER and modes_of(v)[-1] == "AUTO.LOITER"
    hold_ev = [x for x in v.trace if x.get("reason") == "dll_hold"][0]
    assert hold_ev["t"] == pytest.approx(t + 20)
    v.advance(t + 25.1)
    assert v.mode == M.AUTO_RTL
    rtl_ev = [x for x in v.trace if x.get("reason") == "dll_action"][0]
    assert rtl_ev["t"] == pytest.approx(t + 25)  # COM_FAIL_ACT_T = 5 s
    for k in range(t + 26, t + 30):  # link returns: RTL persists
        L.heartbeat(k)
    assert v.mode == M.AUTO_RTL
    assert L.command(E.hold(L.mav, 1), t + 30) == 0 and v.mode == M.AUTO_LOITER
    v.advance(t + 40)
    assert v.mode == M.AUTO_LOITER


def test_link_recovery_during_hold_still_rtl(vl):
    v, L = vl
    t = fly_up(v, L)
    v.advance(t + 22)  # in the delayed hold
    assert v.mode == M.AUTO_LOITER
    L.heartbeat(t + 23)
    v.advance(t + 26)
    assert "AUTO.RTL" in modes_of(v)
    assert [x["t"] for x in v.trace if x.get("reason") == "dll_action"] == [pytest.approx(t + 25)]


def test_late_recovering_packet_honours_deadline_by_timestamp(vl):
    v, L = vl
    t = fly_up(v, L)
    v.advance(t + 24.0)  # the vehicle loop stalled; the next packet is stamped after the deadline
    L.heartbeat(t + 25.01)
    rtl = [x for x in v.trace if x.get("reason") == "dll_action"]
    assert rtl and rtl[0]["t"] == pytest.approx(t + 25)


def test_search_mission_trapezoidal_corners(vl):
    v, L = vl
    L.heartbeat(0)
    wps = [(0.0, 0.0), (0.0, 100.0), (60.0, 100.0)]
    items = E.search_mission([(*lla(v, e, n), 60.0) for e, n in wps], 60.0)
    assert L.upload(items, 0.0) == E.MISSION_ACCEPTED
    assert len(v.mission) == 4
    L.command(E.arm(L.mav, 1), 0.0)
    assert L.command(E.mission_start(L.mav, 1), 1.0) == 0
    assert v.mode == M.AUTO_MISSION
    speeds, t = [], 1.0
    while v.mode == M.AUTO_MISSION and t < 120:
        t += 0.02
        v.advance(t)
        if int(t * 50) % 50 == 0:
            L.heartbeat(t)
        speeds.append((round(t, 2), v.v, v.n))
    assert v.mode == M.AUTO_LOITER  # mission end → LOITER
    reached = [x["seq"] for x in v.trace if x["ev"] == "reached"]
    assert reached == [0, 1, 2, 3]
    assert any(m.get_type() == "MISSION_ITEM_REACHED" and m.seq == 3 for m in L.recv())
    # corner at (0, 100): the speed goes to 0 there (trapezoidal), peaks at cruise between
    at_corner = [s for _, s, n in speeds if abs(n - 100) < 0.06]
    assert min(at_corner) == 0.0 and max(s for _, s, _ in speeds) == pytest.approx(10.0)
    # leg 1: 100 m with a=3, v=10: 2×3.33 s ramps + 6.67 s cruise ≈ 13.3 s
    t_leg = [t for t, s, n in speeds if n > 0.01 and n < 99.9]
    assert t_leg[-1] - t_leg[0] == pytest.approx(13.3, abs=0.5)


def test_params_and_fence(vl):
    v, L = vl
    L.send(E.param_set(L.mav, 1, "COM_DL_LOSS_T", 8), 0)
    pv = [m for m in L.recv() if m.get_type() == "PARAM_VALUE"]
    assert pv and E.decode_param_value(pv[0].param_value, pv[0].param_type) == 8
    assert v.fs.dl_loss_t == 8
    L.send(E.param_request_read(L.mav, 1, "MPC_XY_CRUISE"), 0)
    pv = [m for m in L.recv() if m.get_type() == "PARAM_VALUE"]
    assert pv[0].param_value == 10.0
    fence = E.fence_items([(40.06, -88.64), (40.08, -88.64), (40.08, -88.62)])
    assert L.upload(fence, 0.0, E.MISSION_TYPE_FENCE) == 0 and len(v.fence) == 3


def test_change_speed_and_set_mode(vl):
    v, L = vl
    t = fly_up(v, L)
    assert L.command(E.change_speed(L.mav, 1, 5), t) == 0 and v.cruise == 5
    assert L.command(E.set_mode(L.mav, 1, M.AUTO_RTL), t) == 0 and v.mode == M.AUTO_RTL
    assert L.command(E.command_int(L.mav, 1, 31000), t) == E.RESULT_UNSUPPORTED
