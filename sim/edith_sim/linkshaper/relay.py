"""UDP relay around ``Shaper`` (sim spec §3 wiring, interfaces §5 ports).

    vehicle i ──► :14540+i ─shaped─► companion :14740+i       (+ unimpaired copy ► :14640+i)
    vehicle i ◄── :14580+i ◄─shaped─ companion replies
    companion :16968 ⇄ :16969 tak ⇄ fake CoT router :18088
"""

from __future__ import annotations

import argparse
import heapq
import selectors
import socket
import threading
from pathlib import Path

from edith_common.clock import ScaledClock
from edith_common.ports import port

from edith_sim.linkshaper.shaper import Shaper, WireLog

HOST = "127.0.0.1"


def _udp(bind: int | None = None) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind((HOST, bind or 0))
    s.setblocking(False)
    return s


class Relay:
    def __init__(self, shaper: Shaper, clock: ScaledClock, assets: dict[str, int],
                 tak: bool = True, base: int | None = None) -> None:
        self.shaper, self.clock = shaper, clock
        self._t0 = clock.now_ns()
        self.sel = selectors.DefaultSelector()
        self.socks: list[socket.socket] = []
        self._q: list[tuple[float, int, socket.socket, tuple, bytes]] = []
        self._n = 0
        self._stop = threading.Event()
        for asset, i in assets.items():
            sv = _udp(port("shaper_from_vehicle", i, base))
            sc = _udp()
            to_comp = (HOST, port("companion_mavlink", i, base))
            to_veh = (HOST, port("vehicle", i, base))
            tap = (HOST, port("truth_tap", i, base))
            self._reg(sv, f"mavlink:{asset}", "down", sc, to_comp, tap)
            self._reg(sc, f"mavlink:{asset}", "up", sv, to_veh, None)
        if tak:
            st = _udp(port("mesh_emu_shaper", 0, base))
            sr = _udp()
            self._reg(st, "tak:companion", "up", sr, (HOST, port("cot_router_udp", 0, base)), None)
            self._reg(sr, "tak:companion", "down", st,
                      (HOST, port("mesh_emu_companion", 0, base)), None)

    def _reg(self, sock, link, direction, out_sock, dest, tap) -> None:
        self.socks.append(sock)
        self.sel.register(sock, selectors.EVENT_READ, (link, direction, out_sock, dest, tap))

    def sim_s(self) -> float:
        return (self.clock.now_ns() - self._t0) / 1e9

    def poll(self, timeout: float = 0.002) -> None:
        for key, _ in self.sel.select(timeout):
            link, direction, out_sock, dest, tap = key.data
            try:
                data = key.fileobj.recv(65535)
            except OSError:
                continue
            if tap:
                out_sock.sendto(data, tap)  # truth tap: never impaired
            for t_deliver, b in self.shaper.process(link, direction, data, self.sim_s()):
                self._n += 1
                heapq.heappush(self._q, (t_deliver, self._n, out_sock, dest, b))
        now = self.sim_s()
        while self._q and self._q[0][0] <= now:
            _, _, s, dest, b = heapq.heappop(self._q)
            try:
                s.sendto(b, dest)
            except OSError:
                pass

    def run(self) -> None:
        while not self._stop.is_set():
            self.poll()

    def start(self) -> threading.Thread:
        th = threading.Thread(target=self.run, daemon=True)
        th.start()
        return th

    def stop(self) -> None:
        self._stop.set()
        for s in self.socks:
            s.close()
        self.shaper.wire.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="edith sim linkshaper")
    ap.add_argument("--asset", action="append", default=[], metavar="ID=INSTANCE",
                    help="e.g. drone1=0 (repeatable)")
    ap.add_argument("--wire-log", type=Path, default=Path("runs/latest/mavlink_wire.jsonl"))
    ap.add_argument("--no-tak", action="store_true")
    a = ap.parse_args(argv)
    assets = {k: int(v) for k, v in (x.split("=") for x in a.asset or ["drone1=0"])}
    r = Relay(Shaper(wire_log=WireLog(a.wire_log)), ScaledClock.from_env(), assets,
              tak=not a.no_tak)
    try:
        r.run()
    except KeyboardInterrupt:
        r.stop()
    return 0
