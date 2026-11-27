"""Run a MockVehicle as a UDP process on ScaledClock (interfaces §5 ports).

The vehicle binds ``vehicle`` (14580+i) and sends to ``shaper_from_vehicle`` (14540+i). Without
a linkshaper, point ``--send-port`` at the companion's 14740+i instead.
"""

from __future__ import annotations

import argparse
import socket
import threading

from edith_common.clock import ScaledClock
from edith_common.geo import SCENARIO_ORIGIN
from edith_common.ports import port

from edith_sim.mock.vehicle import MockVehicle
from edith_sim.profile import load_profile


class UdpMock:
    def __init__(self, vehicle: MockVehicle, clock: ScaledClock, bind_port: int,
                 send_port: int, host: str = "127.0.0.1") -> None:
        self.v, self.clock = vehicle, clock
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((host, bind_port))
        self.sock.settimeout(0.002)
        self.dest = (host, send_port)
        self._t0_ns = clock.now_ns()
        self._stop = threading.Event()
        self.lock = threading.Lock()

    def sim_s(self) -> float:
        return (self.clock.now_ns() - self._t0_ns) / 1e9

    def run(self, duration_s: float | None = None) -> None:
        while not self._stop.is_set():
            try:
                data, _ = self.sock.recvfrom(65535)
            except (TimeoutError, BlockingIOError):
                data = None
            except OSError:
                break
            now = self.sim_s()
            with self.lock:
                if data:
                    self.v.feed(data, now)
                self.v.advance(now)
                out = self.v.drain()
            for b in out:
                try:
                    self.sock.sendto(b, self.dest)
                except OSError:
                    pass
            if duration_s is not None and now >= duration_s:
                break

    def start(self) -> threading.Thread:
        th = threading.Thread(target=self.run, daemon=True)
        th.start()
        return th

    def stop(self) -> None:
        self._stop.set()
        self.sock.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="edith sim mock", description=__doc__)
    ap.add_argument("--instance", type=int, default=0)
    ap.add_argument("--profile", default="quad_sim")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--spawn", type=float, nargs=2, default=(0.0, 0.0), metavar=("E", "N"))
    ap.add_argument("--bind-port", type=int)
    ap.add_argument("--send-port", type=int)
    ap.add_argument("--duration", type=float)
    a = ap.parse_args(argv)
    v = MockVehicle(load_profile(a.profile), a.instance, SCENARIO_ORIGIN, tuple(a.spawn), a.seed)
    m = UdpMock(v, ScaledClock.from_env(), a.bind_port or port("vehicle", a.instance),
                a.send_port or port("shaper_from_vehicle", a.instance))
    try:
        m.run(a.duration)
    except KeyboardInterrupt:
        pass
    return 0
