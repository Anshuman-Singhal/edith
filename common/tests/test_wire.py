"""envelope, binframe, ports, models: unit behaviour."""

import json
import struct

import pytest
from edith_common import binframe, envelope, models, ports, schema
from edith_common.clock import ScaledClock
from pydantic import ValidationError


def test_make_and_parse_roundtrip():
    clk = ScaledClock(1795000000000_000000, 1)
    body = models.HudEvent(kind="card_shown", ref="prop-0007", ts_ms=5)
    e1 = envelope.make("hud.event", body, src="unit-a", clock=clk)
    e2 = envelope.make("hud.event", body.model_dump(), src="unit-a", clock=clk)
    assert e2.seq == e1.seq + 1
    assert envelope.make("hud.event", body, src="unit-b").seq == 0
    assert envelope.make("hud.event", body, src="unit-a", seq=99).seq == 99
    raw = envelope.dumps(e1)
    schema.validate_message(json.loads(raw))
    p = envelope.parse(raw)
    assert isinstance(p.body, models.HudEvent) and p.body == body
    assert p.model_dump_json() == raw


def test_make_rejects_wrong_body_type():
    with pytest.raises(TypeError):
        envelope.make("hud.event", models.SysPing(t0_ms=1), src="x")


def test_parse_rejects_other_version_and_bad_body():
    good = json.loads(envelope.dumps(envelope.make("sys.ping", models.SysPing(t0_ms=1), "x")))
    with pytest.raises(envelope.UnknownVersion):
        envelope.parse({**good, "v": 2})
    with pytest.raises(ValidationError):
        envelope.parse({**good, "body": {"t0_ms": "1"}})


def test_seq_counter():
    c = envelope.SeqCounter(5)
    assert [c.next(), c(), c.next()] == [5, 6, 7]


def test_binframe_roundtrip():
    hdr = {"stream": "video.down/drone1", "seq": 3, "ts_ms": 10, "codec": "jpeg", "w": 320,
           "h": 240, "frame_id": 7}
    payload = b"\xff\xd8" + bytes(range(256)) + b"\xff\xd9"
    buf = binframe.pack(hdr, payload)
    (n,) = struct.unpack(">I", buf[:4])
    assert json.loads(buf[4:4 + n]) == hdr
    assert binframe.unpack(buf) == (hdr, payload)
    h, p = binframe.unpack_header(binframe.pack(models.BinaryHeader(**hdr), payload))
    assert h.frame_id == 7 and p == payload
    assert binframe.unpack(binframe.pack(hdr)) == (hdr, b"")


def test_binframe_errors():
    with pytest.raises(ValueError):
        binframe.unpack(b"\x00\x00")
    with pytest.raises(ValueError):
        binframe.unpack(struct.pack(">I", 100) + b"{}")
    with pytest.raises(ValidationError):
        binframe.pack({"stream": "audio.up", "seq": 1, "ts_ms": 1, "codec": "opus"})
    bad = struct.pack(">I", 2) + b"[]"
    with pytest.raises(ValueError):
        binframe.unpack(bad)


def test_ports(monkeypatch):
    monkeypatch.delenv("EDITH_PORT_BASE", raising=False)
    assert ports.port("ws") == 7400
    assert ports.port("companion_mavlink", 1) == 14741
    assert ports.port("detections", 2) == 5802
    monkeypatch.setenv("EDITH_PORT_BASE", "1000")
    assert ports.port("ws") == 8400 and ports.port("vehicle", 1) == 15581
    assert ports.port("ws", base=0) == 7400
    with pytest.raises(ValueError):
        ports.port("ws", 1)
    with pytest.raises(KeyError):
        ports.port("nope")
    # every §5 port number is present
    assert {7400, 7401, 14540, 14580, 14740, 14640, 14550, 5600, 5700, 5800, 16968, 16969, 18088,
            18087, 6969, 8087, 8089, 8080} == set(ports.PORTS.values())
    assert ports.TAK_MCAST_GROUP == "239.2.3.1"


def test_ports_ranges_do_not_overlap():
    used = {}
    for name, p in ports.PORTS.items():
        n = ports.MAX_INSTANCES if name in ports.PER_INSTANCE else 1
        for i in range(n):
            assert p + i not in used, (name, used.get(p + i))
            used[p + i] = name


def test_optional_none_omitted_required_null_kept():
    vp = models.VoicePartial(session_id="s", text="x", conf=None)
    assert json.loads(vp.model_dump_json()) == {"session_id": "s", "text": "x", "conf": None}
    vs = models.VoiceSessionStart(session_id="s", trigger="ptt", reason=None)
    assert "reason" not in json.loads(vs.model_dump_json())
    ck = models.Check(name="n", pass_=True, msg="")
    assert json.loads(ck.model_dump_json()) == {"name": "n", "pass": True, "msg": ""}


def test_python_construction_is_lax_but_wire_is_strict():
    import numpy as np

    hp = models.HeadPose(yaw_deg=np.float64(1.5), pitch_deg=0, roll_deg=0,
                         heading_deg=np.float64(10), heading_unc_deg=2, source="rv")
    assert json.loads(hp.model_dump_json())["yaw_deg"] == 1.5
    with pytest.raises(ValidationError):
        models.SysPing.model_validate_json('{"t0_ms": "5"}', strict=True)


def test_safety_invariants_in_models():
    base = json.loads((schema.SCHEMA_DIR.parent / "fixtures/valid/Track/veh7_confirmed.json")
                      .read_text())
    with pytest.raises(ValidationError):
        models.Track.model_validate({**base, "affiliation": "hostile"})
    assert models.Track.model_validate({**base, "affiliation": "hostile",
                                        "affiliation_src": "human"})
    # no weapon / release verbs anywhere in the structural allowlist
    import typing

    verbs = set(typing.get_args(models.Verb))
    assert verbs == {"takeoff", "goto", "orbit", "observe", "search", "follow", "hold", "rtl",
                     "land"}
