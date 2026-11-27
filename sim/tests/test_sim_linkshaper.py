import json
import socket
import time

import pytest
from edith_common.clock import ScaledClock
from edith_common.ports import port
from edith_common.px4 import encode as E
from edith_sim.linkshaper import Shaper, Window, WireLog, jam_windows
from edith_sim.linkshaper.relay import Relay
from edith_sim.mock import MockVehicle
from edith_sim.mock.udp import UdpMock
from edith_sim.mock.vehicle import _Sink
from edith_sim.profile import load_profile
from pymavlink.dialects.v20 import common as mavlink


def _gcs():
    sink = _Sink()
    return mavlink.MAVLink(sink, srcSystem=245, srcComponent=190), sink


def _bytes(mav, sink, msg):
    mav.send(msg)
    b = b"".join(sink.chunks)
    sink.chunks.clear()
    return b


def test_zero_packets_pass_in_window_and_wire_log_classifies(tmp_path):
    log = tmp_path / "mavlink_wire.jsonl"
    sh = Shaper(jam_windows(10.0, 5.0, ["mavlink:drone2", "tak:*"]), wire_log=WireLog(log))
    mav, sink = _gcs()
    msgs = [E.gcs_heartbeat(mav), E.hold(mav, 2), E.orbit(mav, 2, 40.07, -88.63, 270, 150),
            E.param_set(mav, 2, "GF_ACTION", 1), mav.statustext_encode(6, b"x")]
    passed_in = 0
    for k, m in enumerate(msgs * 4):
        t = 10.0 + k * 0.2  # all inside [10, 15)
        passed_in += len(sh.process("mavlink:drone2", "up", _bytes(mav, sink, m), t))
        passed_in += len(sh.process("tak:companion", "up", b"<event/>", t))
    assert passed_in == 0
    # outside the window, and on another asset, packets pass
    assert len(sh.process("mavlink:drone2", "up", _bytes(mav, sink, msgs[0]), 15.0)) == 1
    assert len(sh.process("mavlink:drone1", "up", _bytes(mav, sink, msgs[0]), 12.0)) == 1
    v = MockVehicle(load_profile(), 1, telemetry=True)
    v.advance(1.0)
    for b in v.drain():
        sh.process("mavlink:drone2", "down", b, 12.0)
    sh.wire.close()
    recs = [json.loads(ln) for ln in log.read_text().splitlines()]
    assert len(recs) == len(sh.wire.records)
    assert sum(r["dir"] == "up" for r in recs) == 22  # every uplink message, dropped or not
    up = [r for r in recs if r["dir"] == "up" and r["asset"] == "drone2" and r["t_sim_ms"] < 15000]
    assert [r["class"] for r in up[:5]] == ["CONFIG", "SAFE", "MOTION", "CONFIG", None]
    assert all(r["dropped"] for r in up)
    down = [r for r in recs if r["dir"] == "down"]
    assert down and all(r["class"] == "TELEM" for r in down)
    assert {"t_sim_ms", "dir", "asset", "msgid", "class", "dropped"} <= set(recs[0])


def test_delay_and_bandwidth_windows():
    sh = Shaper([Window("video:drone1", 0, 10, drop=0.0, delay_ms=250),
                 Window("tak:*", 0, 10, drop=0.0, bw_bps=8 * 100)])
    assert sh.process("video:drone1", "down", b"x" * 10, 1.0) == [(1.25, b"x" * 10)]
    got = [len(sh.process("tak:companion", "up", b"y" * 60, 1.0)) for _ in range(3)]
    assert got == [1, 0, 0]  # 100 B bucket
    assert sh.active("video:drone1", 5) and not sh.active("video:drone2", 5)


@pytest.mark.integration
def test_udp_mock_through_linkshaper(tmp_path, monkeypatch):
    monkeypatch.setenv("EDITH_PORT_BASE", "3000")
    clock = ScaledClock(time.time_ns(), 20.0)
    sh = Shaper(wire_log=WireLog(tmp_path / "w.jsonl"))
    relay = Relay(sh, clock, {"drone1": 0}, tak=False)
    comp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    comp.bind(("127.0.0.1", port("companion_mavlink", 0)))
    comp.settimeout(2.0)
    v = MockVehicle(load_profile(), 0)
    um = UdpMock(v, clock, port("vehicle", 0), port("shaper_from_vehicle", 0))
    relay.start()
    um.start()
    try:
        data, shaper_addr = comp.recvfrom(65535)
        rx = mavlink.MAVLink(None)
        mav, sink = _gcs()
        comp.sendto(_bytes(mav, sink, E.gcs_heartbeat(mav)), shaper_addr)
        comp.sendto(_bytes(mav, sink, E.arm(mav, 1)), shaper_addr)
        acks, hb = [], []
        deadline = time.time() + 3
        while time.time() < deadline and not acks:
            data, _ = comp.recvfrom(65535)
            for m in rx.parse_buffer(data) or []:
                if m.get_type() == "COMMAND_ACK":
                    acks.append(m)
                if m.get_type() == "HEARTBEAT":
                    hb.append(m)
        assert acks and acks[0].result == 0 and v.armed
        assert all(h.autopilot == 12 and h.type == 2 for h in hb)
        sh.add(Window("mavlink:drone1", um.sim_s(), um.sim_s() + 1000))  # partition
        time.sleep(0.2)
        comp.settimeout(0.3)
        n = 0
        try:
            while True:
                comp.recvfrom(65535)
                n += 1
        except TimeoutError:
            pass
        assert n <= 3  # only packets already in flight
    finally:
        um.stop()
        relay.stop()
        comp.close()
    classes = {r["class"] for r in sh.wire.records if r["dir"] == "up"}
    assert {"CONFIG", "MOTION"} <= classes
