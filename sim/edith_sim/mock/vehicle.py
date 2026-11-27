"""MockVehicle: a pymavlink-speaking PX4-like quadcopter (Tier 0; sim spec §2, PLAN §3.6).

Steppable in sim seconds (``advance(t)``, fixed dt 20 ms, integer tick count so runs are
bit-for-bit deterministic). Bytes in through ``feed(buf, t)``; bytes out via ``drain()``.
``edith_sim.mock.udp`` wraps it in a UDP process on ScaledClock.

Kinematics come from the vehicle profile: vertical climb/descent at ``MPC_TKO_SPEED`` (constant
rate; landing at ``MPC_LAND_SPEED``), horizontal trapezoidal velocity with ``MPC_ACC_HOR`` and
``MPC_XY_CRUISE``; every mission waypoint is a corner (decelerate to 0, turn, accelerate).
"""

from __future__ import annotations

import hashlib
import json
import math
import random

from edith_common.geo import SCENARIO_ORIGIN, Origin, enu_to_lla, lla_to_enu
from edith_common.px4 import encode as E
from edith_common.px4 import modes as M
from edith_common.px4.failsafe import DllFailsafe
from pymavlink.dialects.v20 import common as mavlink

DT = 0.02
DISARM_LAND_S = 2.0  # PX4 COM_DISARM_LAND default (not a profile key)
ARRIVE_M = 0.05
DEFAULT_RATES_HZ = {"HEARTBEAT": 1.0, "GLOBAL_POSITION_INT": 10.0, "ATTITUDE": 10.0,
                    "SYS_STATUS": 1.0, "EXTENDED_SYS_STATE": 1.0}
_MSGID_NAME = {"HEARTBEAT": 0, "SYS_STATUS": 1, "ATTITUDE": 30, "GLOBAL_POSITION_INT": 33,
               "EXTENDED_SYS_STATE": 245}
LANDED_ON_GROUND, LANDED_IN_AIR, LANDED_TAKEOFF, LANDED_LANDING = 1, 2, 3, 4


class _Sink:
    def __init__(self) -> None:
        self.chunks: list[bytes] = []

    def write(self, b: bytes) -> None:
        self.chunks.append(bytes(b))


class MockVehicle:
    def __init__(self, profile: dict, instance: int = 0, origin: Origin = SCENARIO_ORIGIN,
                 spawn: tuple[float, float] = (0.0, 0.0), seed: int = 0, t0: float = 0.0,
                 telemetry: bool = True, trace_pose_hz: float = 1.0) -> None:
        self.p = {k: float(v) for k, v in profile.items()}
        self.instance = instance
        self.sysid = M.sysid_for(instance)
        self.origin = origin
        self.rng = random.Random(seed)
        self._sink = _Sink()
        self.mav = mavlink.MAVLink(self._sink, srcSystem=self.sysid,
                                   srcComponent=M.VEHICLE_COMPID)
        self._rx = mavlink.MAVLink(None)
        self._rx.robust_parsing = True
        self.t0 = t0
        self.tick = 0
        self.telemetry_on = telemetry
        self.rates = dict(DEFAULT_RATES_HZ)
        self._next_due = dict.fromkeys(self.rates, t0)
        self._trace_dt = 1.0 / trace_pose_hz if trace_pose_hz else 0.0
        self._next_pose = t0
        # state
        self.e, self.n = float(spawn[0]), float(spawn[1])
        self.u = 0.0  # m above home ground
        self.home = (self.e, self.n)
        self.heading = 0.0  # deg true
        self.v = 0.0  # horizontal speed along heading, m/s
        self.vu = 0.0
        self.armed = False
        self.landed = True
        self.mode = M.AUTO_LOITER
        self.cruise = self.p["MPC_XY_CRUISE"]
        self._target: tuple[float, float, float] | None = None  # (e, n, u) LOITER reposition
        self._takeoff_u = 0.0
        self._orbit: dict | None = None
        self._rtl_phase = ""
        self._land_t: float | None = None
        self._armed_t = 0.0
        self._idle_since: float | None = None
        self.mission: list[E.MissionItem] = []
        self.fence: list[E.MissionItem] = []
        self._mi = 0
        self._upload: dict | None = None
        self.params = {k: v for k, v in profile.items() if k != "orbit_vel_mps"}
        self.fs = DllFailsafe(self.p["COM_DL_LOSS_T"], self.p["COM_FAIL_ACT_T"],
                              int(self.p["NAV_DLL_ACT"]))
        self.battery = 100.0
        self.trace: list[dict] = []
        self._log("boot", mode=M.mode_name(self.mode))

    # ------------------------------------------------------------------ time / io
    @property
    def t(self) -> float:
        return self.t0 + self.tick * DT

    def _log(self, ev: str, t: float | None = None, **kw) -> None:
        self.trace.append({"t": round(self.t if t is None else t, 3), "ev": ev, **kw})

    def trace_sha256(self) -> str:
        return hashlib.sha256(json.dumps(self.trace, sort_keys=True).encode()).hexdigest()

    def feed(self, buf: bytes, t: float | None = None) -> None:
        """Bytes from the GCS arriving at sim time ``t``. Deadlines are evaluated first."""
        if t is not None:
            self.advance(t)
            self._failsafe(t)  # by timestamp, BEFORE the (possibly recovering) packet
        for msg in self._rx.parse_buffer(buf) or []:
            self.handle(msg, self.t if t is None else t)

    def drain(self) -> list[bytes]:
        out, self._sink.chunks = self._sink.chunks, []
        return out

    def send(self, msg) -> None:
        self.mav.send(msg)

    def advance(self, t: float) -> None:
        while self.t + DT <= t + 1e-9:
            self.tick += 1
            self._step(DT)

    # ------------------------------------------------------------------ derived
    @property
    def in_air(self) -> bool:
        return not self.landed

    @property
    def lla(self) -> tuple[float, float, float]:
        return enu_to_lla(self.e, self.n, self.u, self.origin)

    def enu_of(self, lat: float, lon: float) -> tuple[float, float]:
        e, n, _ = lla_to_enu(lat, lon, self.origin.alt_msl_m, self.origin)
        return e, n

    @property
    def mode_name(self) -> str:
        return M.mode_name(self.mode)

    def _set_mode(self, mode: int, reason: str, t: float | None = None,
                  force_log: bool = False) -> None:
        prev = self.mode
        self.mode = mode
        if mode != M.AUTO_LOITER:
            self._target = None
        if mode != M.POSCTL_ORBIT:
            self._orbit = None
        if mode == M.AUTO_RTL and prev != mode:
            self._rtl_phase = "climb"
        if prev != mode or force_log:
            self._log("mode", t, mode=M.mode_name(mode), reason=reason)

    def _set_armed(self, on: bool, reason: str) -> None:
        if on == self.armed:
            return
        self.armed = on
        if on:
            self._armed_t = self.t
            self._idle_since = self.t
            self.home = (self.e, self.n)
        else:
            self.fs.on_disarm()
            self._idle_since = None
            self._land_t = None
        self._log("armed" if on else "disarmed", reason=reason)

    # ------------------------------------------------------------------ physics
    def _failsafe(self, t: float) -> None:
        for t_ev, mode, reason in self.fs.update(t, self.armed, self.in_air):
            self._set_mode(mode, reason, t_ev, force_log=True)
            if mode == M.AUTO_LOITER:
                self._target = None

    def _climb(self, target_u: float, dt: float, rate: float | None = None) -> bool:
        rate = self.p["MPC_TKO_SPEED"] if rate is None else rate
        d = target_u - self.u
        if abs(d) <= rate * dt + 1e-9:
            self.u, self.vu = target_u, 0.0
            return True
        self.vu = math.copysign(rate, d)
        self.u += self.vu * dt
        if self.u > 0:
            self.landed = False
        return False

    def _move_to(self, te: float, tn: float, dt: float, vmax: float | None = None) -> bool:
        """Trapezoidal approach to (te, tn), stopping there. True when arrived."""
        vmax = self.cruise if vmax is None else vmax
        a = self.p["MPC_ACC_HOR"]
        de, dn = te - self.e, tn - self.n
        d = math.hypot(de, dn)
        if d <= ARRIVE_M:
            self.e, self.n, self.v = te, tn, 0.0
            return True
        self.heading = math.degrees(math.atan2(de, dn)) % 360.0
        self.v = min(vmax, self.v + a * dt, math.sqrt(2.0 * a * d))
        step = min(self.v * dt, d)
        self.e += de / d * step
        self.n += dn / d * step
        if d - step <= ARRIVE_M:
            self.e, self.n, self.v = te, tn, 0.0
            return True
        return False

    def _brake(self, dt: float) -> None:
        if self.v <= 0:
            return
        self.v = max(0.0, self.v - self.p["MPC_ACC_HOR"] * dt)
        h = math.radians(self.heading)
        self.e += math.sin(h) * self.v * dt
        self.n += math.cos(h) * self.v * dt

    def _step(self, dt: float) -> None:
        t = self.t
        self._failsafe(t)
        mode = self.mode
        if self.armed and self.in_air:
            if mode == M.AUTO_TAKEOFF:
                self._brake(dt)
                if self._climb(self._takeoff_u, dt):
                    self._set_mode(M.AUTO_LOITER, "takeoff_done")
            elif mode == M.AUTO_LOITER:
                if self._target is not None:
                    te, tn, tu = self._target
                    self._climb(tu, dt)
                    self._move_to(te, tn, dt)
                else:
                    self._brake(dt)
                    self.vu = 0.0
            elif mode == M.AUTO_MISSION:
                self._step_mission(dt)
            elif mode == M.POSCTL_ORBIT:
                self._step_orbit(dt)
            elif mode == M.AUTO_RTL:
                self._step_rtl(dt)
            elif mode == M.AUTO_LAND:
                self._step_land(dt)
        elif self.armed and self.landed:
            if mode == M.AUTO_TAKEOFF:
                self._climb(self._takeoff_u, dt)
            elif mode == M.AUTO_MISSION:
                self._step_mission(dt)
            if self.landed and self._idle_since is not None and \
                    t - self._idle_since >= self.p["COM_DISARM_PRFLT"] - 1e-9:
                self._set_armed(False, "auto_disarm_preflight")
        if self.landed and self.armed and self._land_t is not None and \
                t - self._land_t >= DISARM_LAND_S - 1e-9:
            self._set_armed(False, "landed")
        if self.armed:
            drain = max(1.0, self.p["SIM_BAT_DRAIN"])
            self.battery = max(self.p["SIM_BAT_MIN_PCT"],
                               100.0 - (100.0 - self.p["SIM_BAT_MIN_PCT"])
                               * (t - self._armed_t) / drain)
        if self._trace_dt and t >= self._next_pose - 1e-9:
            self._next_pose = t + self._trace_dt
            self._log("pose", e=round(self.e, 2), n=round(self.n, 2), u=round(self.u, 2),
                      mode=self.mode_name)
        if self.telemetry_on:
            self._telemetry(t)

    def _start_climb_from_ground(self) -> None:
        self.landed = False
        self._idle_since = None
        self._land_t = None

    def _step_mission(self, dt: float) -> None:
        if self._mi >= len(self.mission):
            self._set_mode(M.AUTO_LOITER, "mission_end")
            return
        it = self.mission[self._mi]
        if it.command == E.CMD_NAV_TAKEOFF:
            if self.landed:
                self._start_climb_from_ground()
            done = self.u >= it.z - 1e-9 or self._climb(it.z, dt)
        elif it.command == E.CMD_NAV_WAYPOINT:
            if self.landed:  # PX4 needs a takeoff item first; stay put
                return
            te, tn = self.enu_of(it.lat, it.lon)
            up = self._climb(it.z, dt)
            done = self._move_to(te, tn, dt) and (up or abs(self.u - it.z) < 0.5)
        else:
            done = True
        if done:
            self._log("reached", seq=it.seq)
            self.send(self.mav.mission_item_reached_encode(it.seq))
            self._mi += 1
            if self._mi >= len(self.mission):
                self._set_mode(M.AUTO_LOITER, "mission_end")

    def _step_orbit(self, dt: float) -> None:
        o = self._orbit
        assert o is not None
        self._climb(o["u"], dt)
        ce, cn, r = o["e"], o["n"], o["r"]
        de, dn = self.e - ce, self.n - cn
        d = math.hypot(de, dn)
        if not o["on"]:
            if d < 1e-6:
                de, dn, d = 0.0, 1.0, 1.0
            pe, pn = ce + de / d * r, cn + dn / d * r
            if self._move_to(pe, pn, dt) or abs(d - r) <= 2.0:
                o["on"], o["th"] = True, math.atan2(self.n - cn, self.e - ce)
            return
        o["th"] += o["vel"] / r * dt
        self.e, self.n = ce + r * math.cos(o["th"]), cn + r * math.sin(o["th"])
        self.v = o["vel"]
        self.heading = math.degrees(math.atan2(ce - self.e, cn - self.n)) % 360.0

    def _step_rtl(self, dt: float) -> None:
        if self._rtl_phase == "climb":
            self._brake(dt)
            if self.u >= self.p["RTL_RETURN_ALT"] - 1e-9 or \
                    self._climb(self.p["RTL_RETURN_ALT"], dt):
                self._rtl_phase = "return"
        elif self._rtl_phase == "return":
            if self._move_to(self.home[0], self.home[1], dt):
                self._set_mode(M.AUTO_LAND, "rtl_land")

    def _step_land(self, dt: float) -> None:
        self._brake(dt)
        if self._climb(0.0, dt, self.p["MPC_LAND_SPEED"]):
            if not self.landed:
                self.landed = True
                self._land_t = self.t
                self._log("landed")

    # ------------------------------------------------------------------ telemetry
    def _telemetry(self, t: float) -> None:
        for name, hz in self.rates.items():
            if hz <= 0 or t < self._next_due[name] - 1e-9:
                continue
            self._next_due[name] = t + 1.0 / hz
            self.send(self._telem_msg(name, t))

    def heartbeat_msg(self):
        base = M.BASE_CUSTOM_MODE_ENABLED | (M.BASE_SAFETY_ARMED if self.armed else 0)
        return self.mav.heartbeat_encode(M.TYPE_QUADROTOR, M.AUTOPILOT_PX4, base, self.mode,
                                         4 if self.armed else 3)

    def _telem_msg(self, name: str, t: float):
        tb = int((t - self.t0) * 1000) & 0xFFFFFFFF
        h = math.radians(self.heading)
        if name == "HEARTBEAT":
            return self.heartbeat_msg()
        if name == "GLOBAL_POSITION_INT":
            lat, lon, alt = self.lla
            return self.mav.global_position_int_encode(
                tb, int(round(lat * 1e7)), int(round(lon * 1e7)), int(round(alt * 1000)),
                int(round(self.u * 1000)), int(round(math.cos(h) * self.v * 100)),
                int(round(math.sin(h) * self.v * 100)), int(round(-self.vu * 100)),
                int(round(self.heading * 100)) % 36000)
        if name == "ATTITUDE":
            yaw = math.radians((self.heading + 180.0) % 360.0 - 180.0)
            return self.mav.attitude_encode(tb, 0.0, 0.0, yaw, 0.0, 0.0, 0.0)
        if name == "SYS_STATUS":
            mv = int(16800 - (100 - self.battery) * 20)
            return self.mav.sys_status_encode(0, 0, 0, 0, mv, -1, int(round(self.battery)),
                                              0, 0, 0, 0, 0, 0)
        if name == "EXTENDED_SYS_STATE":
            if self.landed:
                ls = LANDED_ON_GROUND
            elif self.mode == M.AUTO_LAND:
                ls = LANDED_LANDING
            elif self.mode == M.AUTO_TAKEOFF:
                ls = LANDED_TAKEOFF
            else:
                ls = LANDED_IN_AIR
            return self.mav.extended_sys_state_encode(0, ls)
        raise KeyError(name)

    # ------------------------------------------------------------------ inbound
    def handle(self, msg, t: float) -> None:
        typ = msg.get_type()
        if typ == "BAD_DATA":
            return
        if typ == "HEARTBEAT":
            if msg.type == M.TYPE_GCS:
                self.fs.on_link(t)
            return
        tsys = getattr(msg, "target_system", self.sysid)
        if tsys not in (0, self.sysid):
            return
        fn = getattr(self, f"_on_{typ.lower()}", None)
        if fn is not None:
            fn(msg)

    def _ack(self, msg, command: int, result: int) -> None:
        self._log("ack", cmd=command, result=result)
        self.send(self.mav.command_ack_encode(command, result, 0, 0, msg.get_srcSystem(),
                                              msg.get_srcComponent()))

    def _on_command_long(self, msg) -> None:
        self._command(msg, msg.command, (msg.param1, msg.param2, msg.param3, msg.param4),
                      None, None, msg.param7)

    def _on_command_int(self, msg) -> None:
        lat = None if msg.x == E.INT32_MAX else msg.x / 1e7
        lon = None if msg.y == E.INT32_MAX else msg.y / 1e7
        self._command(msg, msg.command, (msg.param1, msg.param2, msg.param3, msg.param4),
                      lat, lon, msg.z)

    def _alt_u(self, alt_msl: float) -> float:
        return self.u if alt_msl is None or math.isnan(alt_msl) else alt_msl - self.origin.alt_msl_m

    def _user_mode(self, mode: int) -> None:
        self.fs.on_mode_change()  # takeover: drops a pending/active DLL action
        self._set_mode(mode, "cmd")

    def _command(self, msg, cmd: int, p, lat, lon, z) -> None:  # noqa: C901
        ok, rej = E.RESULT_ACCEPTED, E.RESULT_DENIED
        r = E.RESULT_UNSUPPORTED
        if cmd == E.CMD_COMPONENT_ARM_DISARM:
            if p[0] >= 0.5:
                r = ok if (self.landed or self.armed) else rej
                if r == ok:
                    self._set_armed(True, "cmd")
            else:
                r = ok if (self.landed or int(p[1]) == 21196) else rej
                if r == ok:
                    self._set_armed(False, "cmd")
        elif cmd == E.CMD_NAV_TAKEOFF:
            r = ok if self.armed else rej
            if r == ok:
                u = self._alt_u(z)
                self._takeoff_u = self.p["MIS_TAKEOFF_ALT"] if (z is None or math.isnan(z)) else u
                if self.landed:
                    self._start_climb_from_ground()
                self._user_mode(M.AUTO_TAKEOFF)
        elif cmd == E.CMD_DO_REPOSITION:
            r = ok if (self.in_air and lat is not None) else rej
            if r == ok:
                te, tn = self.enu_of(lat, lon)
                if p[0] > 0:
                    self.cruise = p[0]
                self._user_mode(M.AUTO_LOITER)
                self._target = (te, tn, self._alt_u(z))
        elif cmd == E.CMD_DO_ORBIT:
            r = ok if (self.in_air and lat is not None) else rej
            if r == ok:
                ce, cn = self.enu_of(lat, lon)
                radius = abs(p[0]) if p[0] and not math.isnan(p[0]) else 50.0
                vel = abs(p[1]) if p[1] and not math.isnan(p[1]) else self.p.get("orbit_vel_mps", 5)
                self._user_mode(M.POSCTL_ORBIT)
                self._orbit = {"e": ce, "n": cn, "r": radius, "vel": vel,
                               "u": self._alt_u(z), "on": False, "th": 0.0}
        elif cmd == E.CMD_DO_SET_MODE:
            mode = M.encode_mode(int(p[1]), int(p[2]))
            if mode == M.AUTO_LOITER:
                r = ok
                self._user_mode(mode)
                self._target = None
            elif mode in (M.AUTO_RTL, M.AUTO_LAND):
                r = ok if self.in_air else rej
                if r == ok:
                    self._user_mode(mode)
            elif mode == M.AUTO_MISSION:
                r = ok if (self.armed and self.mission) else rej
                if r == ok:
                    self._user_mode(mode)
            else:
                r = rej
        elif cmd == E.CMD_NAV_RETURN_TO_LAUNCH:
            r = ok if self.in_air else rej
            if r == ok:
                self._user_mode(M.AUTO_RTL)
        elif cmd == E.CMD_NAV_LAND:
            r = ok if self.in_air else rej
            if r == ok:
                self._user_mode(M.AUTO_LAND)
        elif cmd == E.CMD_DO_CHANGE_SPEED:
            r = ok if p[1] > 0 else rej
            if r == ok:
                self.cruise = float(p[1])
        elif cmd == E.CMD_MISSION_START:
            can = self.armed and self.mission and (
                self.in_air or self.mission[0].command == E.CMD_NAV_TAKEOFF)
            r = ok if can else rej
            if r == ok:
                self._mi = max(0, int(p[0]))
                self._user_mode(M.AUTO_MISSION)
        elif cmd == E.CMD_SET_MESSAGE_INTERVAL:
            name = next((k for k, v in _MSGID_NAME.items() if v == int(p[0])), None)
            r = ok if name else rej
            if name:
                us = p[1]
                self.rates[name] = 0.0 if us < 0 else (DEFAULT_RATES_HZ[name] if us == 0
                                                       else 1e6 / us)
                self._next_due[name] = self.t
        self._ack(msg, cmd, r)

    # mission protocol -------------------------------------------------------------------
    def _on_mission_count(self, msg) -> None:
        mt = getattr(msg, "mission_type", 0)
        if msg.count == 0:
            self._commit(mt, [])
            self._mission_ack(msg, mt, E.MISSION_ACCEPTED)
            return
        self._upload = {"type": mt, "count": msg.count, "items": [], "src": msg}
        self._request(msg, mt, 0)

    def _request(self, msg, mt: int, seq: int) -> None:
        self.send(self.mav.mission_request_int_encode(msg.get_srcSystem(),
                                                      msg.get_srcComponent(), seq, mt))

    def _mission_ack(self, msg, mt: int, result: int) -> None:
        self._log("mission_ack", type=mt, result=result)
        self.send(self.mav.mission_ack_encode(msg.get_srcSystem(), msg.get_srcComponent(),
                                              result, mt))

    def _commit(self, mt: int, items: list) -> None:
        if mt == E.MISSION_TYPE_FENCE:
            self.fence = items
        else:
            self.mission, self._mi = items, 0

    def _on_mission_item_int(self, msg) -> None:
        up = self._upload
        mt = getattr(msg, "mission_type", 0)
        if up is None or mt != up["type"]:
            return
        exp = len(up["items"])
        if msg.seq != exp:
            self._request(msg, mt, exp)
            return
        up["items"].append(E.MissionItem.from_msg(msg))
        if len(up["items"]) < up["count"]:
            self._request(msg, mt, exp + 1)
        else:
            self._commit(mt, up["items"])
            self._upload = None
            self._mission_ack(msg, mt, E.MISSION_ACCEPTED)

    def _on_mission_clear_all(self, msg) -> None:
        mt = getattr(msg, "mission_type", 0)
        if mt in (E.MISSION_TYPE_MISSION, E.MISSION_TYPE_ALL):
            self._commit(E.MISSION_TYPE_MISSION, [])
        if mt in (E.MISSION_TYPE_FENCE, E.MISSION_TYPE_ALL):
            self._commit(E.MISSION_TYPE_FENCE, [])
        self._mission_ack(msg, mt, E.MISSION_ACCEPTED)

    def _on_mission_request_list(self, msg) -> None:
        mt = getattr(msg, "mission_type", 0)
        n = len(self.fence if mt == E.MISSION_TYPE_FENCE else self.mission)
        self.send(self.mav.mission_count_encode(msg.get_srcSystem(), msg.get_srcComponent(),
                                                n, mt))

    def _on_mission_request_int(self, msg) -> None:
        mt = getattr(msg, "mission_type", 0)
        items = self.fence if mt == E.MISSION_TYPE_FENCE else self.mission
        if 0 <= msg.seq < len(items):
            self.send(items[msg.seq].to_msg(self.mav, msg.get_srcSystem(),
                                            msg.get_srcComponent()))

    # params -----------------------------------------------------------------------------
    def _param_value(self, name: str, index: int):
        v, t = E.encode_param_value(name, self.params[name])
        return self.mav.param_value_encode(name.encode(), v, t, len(self.params), index)

    def _on_param_set(self, msg) -> None:
        name = msg.param_id if isinstance(msg.param_id, str) else msg.param_id.decode()
        name = name.rstrip("\x00")
        val = E.decode_param_value(msg.param_value, msg.param_type)
        self.params[name] = val
        self.p[name] = float(val)
        self.fs.dl_loss_t = self.p["COM_DL_LOSS_T"]
        self.fs.fail_act_t = self.p["COM_FAIL_ACT_T"]
        self.fs.nav_dll_act = int(self.p["NAV_DLL_ACT"])
        self._log("param_set", name=name, value=val)
        self.send(self._param_value(name, list(self.params).index(name)))

    def _on_param_request_read(self, msg) -> None:
        names = list(self.params)
        name = msg.param_id if isinstance(msg.param_id, str) else msg.param_id.decode()
        name = name.rstrip("\x00")
        if msg.param_index >= 0 and msg.param_index < len(names):
            name = names[msg.param_index]
        if name in self.params:
            self.send(self._param_value(name, names.index(name)))

    def _on_param_request_list(self, msg) -> None:
        for i, name in enumerate(self.params):
            self.send(self._param_value(name, i))
