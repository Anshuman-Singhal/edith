"""In-process GCS ↔ MockVehicle link (bytes both ways, like the wire) for tests and the pre-run."""

from __future__ import annotations

from edith_common.px4 import encode as E
from edith_common.px4 import modes as M
from pymavlink.dialects.v20 import common as mavlink

from edith_sim.mock.vehicle import MockVehicle, _Sink


class InProcLink:
    """A minimal GCS (sysid 245) wired to one MockVehicle. ``up=False`` drops uplink bytes."""

    def __init__(self, vehicle: MockVehicle) -> None:
        self.v = vehicle
        self._sink = _Sink()
        self.mav = mavlink.MAVLink(self._sink, srcSystem=M.COMPANION_SYSID,
                                   srcComponent=M.COMPANION_COMPID)
        self._rx = mavlink.MAVLink(None)
        self._rx.robust_parsing = True
        self.up = True
        self.received: list = []

    @property
    def tsys(self) -> int:
        return self.v.sysid

    def send(self, msg, t: float) -> None:
        self.mav.send(msg)
        data = b"".join(self._sink.chunks)
        self._sink.chunks = []
        if self.up:
            self.v.feed(data, t)
        else:
            self.v.advance(t)

    def heartbeat(self, t: float) -> None:
        self.send(E.gcs_heartbeat(self.mav), t)

    def recv(self) -> list:
        out = []
        for chunk in self.v.drain():
            out += [m for m in (self._rx.parse_buffer(chunk) or []) if m.get_type() != "BAD_DATA"]
        self.received += out
        return out

    def upload(self, items: list[E.MissionItem], t: float,
               mission_type: int = E.MISSION_TYPE_MISSION) -> int:
        """Run the MISSION_COUNT/REQUEST_INT/ITEM_INT/ACK handshake; return the ACK result."""
        self.recv()
        self.send(E.mission_count(self.mav, self.tsys, len(items), mission_type), t)
        for _ in range(len(items) + 2):
            for m in self.recv():
                if m.get_type() == "MISSION_REQUEST_INT":
                    self.send(items[m.seq].to_msg(self.mav, self.tsys), t)
                elif m.get_type() == "MISSION_ACK":
                    return int(m.type)
        return -1

    def command(self, msg, t: float) -> int | None:
        """Send a command and return its COMMAND_ACK result (None if none)."""
        self.recv()
        self.send(msg, t)
        for m in self.recv():
            if m.get_type() == "COMMAND_ACK" and m.command == msg.command:
                return int(m.result)
        return None
