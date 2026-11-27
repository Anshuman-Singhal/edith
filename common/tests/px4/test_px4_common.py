import math

import pytest
from edith_common.px4 import classify as C
from edith_common.px4 import encode as E
from edith_common.px4 import modes as M
from edith_common.px4.failsafe import DllFailsafe, dll_countdown_s
from edith_common.px4.search import leg_spacing_m, plan_search, square
from pymavlink.dialects.v20 import common as mavlink


@pytest.fixture
def mav():
    return mavlink.MAVLink(None, srcSystem=245, srcComponent=190)


def test_mode_encoding():
    assert M.AUTO_LOITER == (4 << 16) | (3 << 24)
    assert M.POSCTL_ORBIT == (3 << 16) | (1 << 24)
    for name in ("AUTO.TAKEOFF", "AUTO.LOITER", "AUTO.MISSION", "AUTO.RTL", "AUTO.LAND",
                 "POSCTL.ORBIT"):
        assert M.mode_name(M.mode_from_name(name)) == name
    assert M.decode_mode(M.AUTO_LOITER) == (4, 3)
    assert M.sysid_for(1) == 2 and M.AUTOPILOT_PX4 == 12 and M.TYPE_QUADROTOR == 2


def test_param_int32_bytewise():
    f = E.int32_to_param_float(20)
    assert E.param_float_to_int32(f) == 20
    assert E.encode_param_value("COM_DL_LOSS_T", 8)[1] == E.PARAM_TYPE_INT32
    assert E.encode_param_value("MPC_XY_CRUISE", 10.0) == (10.0, E.PARAM_TYPE_REAL32)


def test_classifier_table(mav):
    hold = E.hold(mav, 1)
    assert C.classify(hold) == "SAFE"
    assert C.classify(E.set_mode(mav, 1, M.AUTO_RTL)) == "MOTION"
    for m in (E.arm(mav, 1), E.takeoff(mav, 1, 270), E.reposition(mav, 1, 40, -88, 270),
              E.orbit(mav, 1, 40, -88, 270, 150), E.rtl(mav, 1), E.land(mav, 1),
              E.change_speed(mav, 1, 5), E.mission_start(mav, 1),
              E.mission_count(mav, 1, 3), E.mission_clear_all(mav, 1)):
        assert C.classify(m) == "MOTION", m
    items = E.search_mission([(40.0, -88.0, 60.0)], 60.0)
    assert C.classify(items[0].to_msg(mav, 1)) == "MOTION"
    fence = E.fence_items([(40, -88), (40.1, -88), (40.1, -88.1)])
    assert fence[0].p1 == 3 and fence[0].command == 5001
    assert C.classify(fence[0].to_msg(mav, 1)) == "CONFIG"
    assert C.classify(E.mission_count(mav, 1, 3, E.MISSION_TYPE_FENCE)) == "CONFIG"
    assert C.classify(E.gcs_heartbeat(mav)) == "CONFIG"
    assert C.classify(E.param_set(mav, 1, "GF_ACTION", 1)) == "CONFIG"
    assert C.classify(E.message_interval(mav, 1, 33, 100000)) == "CONFIG"
    assert C.classify(mav.statustext_encode(6, b"hi")) is None
    assert C.classify(E.command_int(mav, 1, 31000)) is None


def test_plan_search_vignette_nai1():
    assert leg_spacing_m(60) == pytest.approx(67.9, abs=0.2)
    wps = plan_search(square(0, 250, 300), 60)
    legs = sorted({round(e, 3) for e, _, _ in wps})
    assert legs == [-120, -60, 0, 60, 120]  # 5 legs (sim §7)
    assert wps[0][:2] == (-120, 100) and wps[1][:2] == (-120, 400)  # leg 1 flown north
    assert wps[2][:2] == (-60, 400) and all(a == 60 for *_, a in wps)
    length = sum(math.dist(a[:2], b[:2]) for a, b in zip(wps, wps[1:], strict=False))
    assert length == pytest.approx(1740)


def test_failsafe_delayed_hold_and_recovery_during_hold():
    fs = DllFailsafe(20, 5, 2)
    assert fs.update(1, True, True) == []  # never linked → no DLL
    fs.on_link(10)
    assert fs.update(29.9, True, True) == []
    out = fs.update(30.5, True, True)
    assert out == [(30.0, M.AUTO_LOITER, "dll_hold")]
    fs.on_link(32)  # link recovers DURING the hold: action is kept (OnModeChangeOrDisarm)
    assert fs.update(35.2, True, True) == [(35.0, M.AUTO_RTL, "dll_action")]
    assert fs.state == "action"


def test_failsafe_deadline_by_timestamp_before_recovering_packet():
    fs = DllFailsafe(20, 5, 2)
    fs.on_link(0)
    fs.update(20.0, True, True)
    # a recovering packet stamped after the deadline but processed late: update first
    trans = fs.update(25.3, True, True)
    fs.on_link(25.3)
    assert trans == [(25.0, M.AUTO_RTL, "dll_action")]


def test_failsafe_only_armed_in_air_and_mode_change_takeover():
    fs = DllFailsafe(20, 5, 2)
    fs.on_link(0)
    assert fs.update(60, False, False) == []
    assert fs.update(61, True, False) == []
    fs2 = DllFailsafe(20, 5, 2)
    fs2.on_link(0)
    fs2.update(21, True, True)
    fs2.on_mode_change()  # hold accepted during the delay
    assert fs2.update(30, True, True) == [] and fs2.state == "idle"


def test_failsafe_start_delay_refills_at_quarter_rate():
    fs = DllFailsafe(2, 5, 2)
    fs.on_link(0)
    fs.update(2, True, True)
    fs.update(7, True, True)  # hold consumed the whole delay
    fs.on_mode_change()
    fs.on_link(7)
    fs.update(9, True, True)  # second loss at t9: delay refilled only 2/4 s
    assert fs.deadline == pytest.approx(9.5)


def test_countdown():
    assert dll_countdown_s(8, 20, 5) == 17
