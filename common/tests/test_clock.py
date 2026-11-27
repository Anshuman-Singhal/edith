import asyncio
import json
import os
import subprocess
import sys
import time

import pytest
from edith_common.clock import ScaledClock

CHILD = r"""
import json, sys, time
from edith_common.clock import ScaledClock
target = int(sys.argv[1])
c = ScaledClock.from_env()
while time.time_ns() < target - 3_000_000:
    time.sleep(0.001)
while True:
    w = time.time_ns()
    if w >= target:
        break
v = c.now_ns()
print(json.dumps({"now_ns": v, "wall_ns": w, "speed": c.speed, "t0": c.t0_ns}))
"""


def test_formula_and_units():
    c = ScaledClock(1_000_000_000_000, 4)
    assert c.scale_wall_ns(1_000_000_000_000) == 1_000_000_000_000
    assert c.scale_wall_ns(1_000_001_000_000) == 1_000_004_000_000
    assert ScaledClock(0, 2.5).scale_wall_ns(10) == 25
    assert c.wall_to_sim_s(2) == 8 and c.sim_to_wall_s(8) == 2
    t = c.now_ms()
    assert abs(t - c.now_ns() // 1_000_000) < 50
    with pytest.raises(ValueError):
        ScaledClock(0, 0)


def test_from_env_and_env_roundtrip():
    env = ScaledClock.env(1795000000000000000, 4)
    assert env == {"EDITH_T0_NS": "1795000000000000000", "EDITH_SPEED": "4.0"}
    c = ScaledClock.from_env(env)
    assert c.t0_ns == 1795000000000000000 and c.speed == 4.0
    d = ScaledClock.from_env({})
    assert d.speed == 1.0 and d.t0_ns % 1_000_000_000 == 0
    assert abs(d.now_ns() - time.time_ns()) < 50_000_000  # speed 1 ≈ wall


def test_sleep_scaled():
    c = ScaledClock(time.time_ns(), 10)
    w0 = time.monotonic()
    c.sleep(0.5)  # 0.05 s wall
    assert 0.04 <= time.monotonic() - w0 < 0.3
    w0 = time.monotonic()
    asyncio.run(c.asleep(0.5))
    assert 0.04 <= time.monotonic() - w0 < 0.3


def test_two_processes_agree_at_speed_4():
    t0 = time.time_ns() - 3_000_000_000
    env = {**os.environ, **ScaledClock.env(t0, 4)}
    target = time.time_ns() + 2_000_000_000  # both children read at this wall instant
    procs = [subprocess.Popen([sys.executable, "-c", CHILD, str(target)], env=env,
                              stdout=subprocess.PIPE, text=True) for _ in range(2)]
    out = [json.loads(p.communicate(timeout=20)[0]) for p in procs]
    ref = ScaledClock(t0, 4)
    for o in out:
        assert o["speed"] == 4.0 and o["t0"] == t0
        # each child's reading equals the formula at its own wall read
        assert abs(o["now_ns"] - ref.scale_wall_ns(o["wall_ns"])) < 5_000_000
    assert abs(out[0]["now_ns"] - out[1]["now_ns"]) < 5_000_000  # < 5 ms scaled
