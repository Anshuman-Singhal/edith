"""MAVLink encodings shared by the companion's AssetAdapter, MockVehicle and the lint (C62).

Every builder takes a pymavlink ``MAVLink`` instance (``mav``, whose ``srcSystem`` is the
sender) and returns a message object; callers ``mav.send(msg)`` or ``msg.pack(mav)``.
Commands use ``COMMAND_INT`` with ``MAV_FRAME_GLOBAL`` (AMSL); mission items use
``MAV_FRAME_GLOBAL_RELATIVE_ALT_INT`` (interfaces §6).
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass

from edith_common.px4 import modes

# MAV_CMD ids (common.xml)
CMD_NAV_WAYPOINT = 16
CMD_NAV_RETURN_TO_LAUNCH = 20
CMD_NAV_LAND = 21
CMD_NAV_TAKEOFF = 22
CMD_DO_ORBIT = 34
CMD_DO_SET_MODE = 176
CMD_DO_CHANGE_SPEED = 178
CMD_DO_REPOSITION = 192
CMD_MISSION_START = 300
CMD_COMPONENT_ARM_DISARM = 400
CMD_SET_MESSAGE_INTERVAL = 511
CMD_FENCE_POLYGON_VERTEX_INCLUSION = 5001

FRAME_GLOBAL = 0
FRAME_GLOBAL_RELATIVE_ALT = 3
FRAME_GLOBAL_INT = 5
FRAME_GLOBAL_RELATIVE_ALT_INT = 6

MISSION_TYPE_MISSION = 0
MISSION_TYPE_FENCE = 1
MISSION_TYPE_ALL = 255

RESULT_ACCEPTED = 0
RESULT_TEMPORARILY_REJECTED = 1
RESULT_DENIED = 2
RESULT_UNSUPPORTED = 3
RESULT_FAILED = 4

MISSION_ACCEPTED = 0
MISSION_ERROR = 1
MISSION_INVALID_SEQUENCE = 13

REPOSITION_FLAG_CHANGE_MODE = 1
ORBIT_YAW_TO_CENTRE = 0  # ORBIT_YAW_BEHAVIOUR_HOLD_FRONT_TO_CIRCLE_CENTER

INT32_MAX = 2**31 - 1  # "unset" x/y in COMMAND_INT


def _e7(deg: float) -> int:
    return int(round(deg * 1e7))


def command_int(mav, tsys: int, command: int, p1=0.0, p2=0.0, p3=0.0, p4=0.0,
                lat: float | None = None, lon: float | None = None, alt: float = 0.0,
                frame: int = FRAME_GLOBAL, tcomp: int = modes.VEHICLE_COMPID):
    x = INT32_MAX if lat is None else _e7(lat)
    y = INT32_MAX if lon is None else _e7(lon)
    return mav.command_int_encode(tsys, tcomp, frame, command, 0, 0, float(p1), float(p2),
                                  float(p3), float(p4), x, y, float(alt))


def arm(mav, tsys: int, on: bool = True):
    return command_int(mav, tsys, CMD_COMPONENT_ARM_DISARM, p1=1.0 if on else 0.0)


def takeoff(mav, tsys: int, alt_msl_m: float, lat: float | None = None,
            lon: float | None = None):
    """NAV_TAKEOFF; p7 (z) is AMSL."""
    return command_int(mav, tsys, CMD_NAV_TAKEOFF, p4=math.nan, lat=lat, lon=lon,
                       alt=alt_msl_m)


def reposition(mav, tsys: int, lat: float, lon: float, alt_msl_m: float,
               speed_mps: float = -1.0):
    return command_int(mav, tsys, CMD_DO_REPOSITION, p1=speed_mps,
                       p2=REPOSITION_FLAG_CHANGE_MODE, p4=math.nan, lat=lat, lon=lon,
                       alt=alt_msl_m)


def orbit(mav, tsys: int, lat: float, lon: float, alt_msl_m: float, radius_m: float,
          vel_mps: float = 5.0):
    return command_int(mav, tsys, CMD_DO_ORBIT, p1=radius_m, p2=vel_mps,
                       p3=ORBIT_YAW_TO_CENTRE, p4=math.nan, lat=lat, lon=lon, alt=alt_msl_m)


def set_mode(mav, tsys: int, custom_mode: int):
    main, sub = modes.decode_mode(custom_mode)
    return command_int(mav, tsys, CMD_DO_SET_MODE, p1=modes.BASE_CUSTOM_MODE_ENABLED,
                       p2=main, p3=sub)


def hold(mav, tsys: int):
    """The safety-stop hold: DO_SET_MODE AUTO.LOITER (main 4 / sub 3). Class SAFE."""
    return set_mode(mav, tsys, modes.AUTO_LOITER)


def rtl(mav, tsys: int):
    return command_int(mav, tsys, CMD_NAV_RETURN_TO_LAUNCH)


def land(mav, tsys: int):
    return command_int(mav, tsys, CMD_NAV_LAND, p4=math.nan)


def change_speed(mav, tsys: int, speed_mps: float):
    return command_int(mav, tsys, CMD_DO_CHANGE_SPEED, p1=1.0, p2=speed_mps, p3=-1.0)


def mission_start(mav, tsys: int):
    return command_int(mav, tsys, CMD_MISSION_START, p1=0.0, p2=-1.0)


def message_interval(mav, tsys: int, msgid: int, interval_us: int):
    return command_int(mav, tsys, CMD_SET_MESSAGE_INTERVAL, p1=msgid, p2=interval_us)


def gcs_heartbeat(mav):
    return mav.heartbeat_encode(modes.TYPE_GCS, 8, 0, 0, 4)  # MAV_AUTOPILOT_INVALID, ACTIVE


# --- mission / fence items ---------------------------------------------------------------

@dataclass(frozen=True)
class MissionItem:
    seq: int
    command: int
    frame: int
    x: int
    y: int
    z: float
    p1: float = 0.0
    p2: float = 0.0
    p3: float = 0.0
    p4: float = 0.0
    mission_type: int = MISSION_TYPE_MISSION

    @property
    def lat(self) -> float:
        return self.x / 1e7

    @property
    def lon(self) -> float:
        return self.y / 1e7

    def to_msg(self, mav, tsys: int, tcomp: int = modes.VEHICLE_COMPID):
        return mav.mission_item_int_encode(
            tsys, tcomp, self.seq, self.frame, self.command, 1 if self.seq == 0 else 0, 1,
            self.p1, self.p2, self.p3, self.p4, self.x, self.y, float(self.z),
            self.mission_type)

    @classmethod
    def from_msg(cls, m) -> MissionItem:
        return cls(m.seq, m.command, m.frame, m.x, m.y, m.z, m.param1, m.param2, m.param3,
                   m.param4, getattr(m, "mission_type", 0))


def search_mission(waypoints: list[tuple[float, float, float]],
                   takeoff_alt_rel_m: float | None = None) -> list[MissionItem]:
    """``[NAV_TAKEOFF if landed, waypoints…]``; waypoints are (lat, lon, alt_rel_m)."""
    items: list[MissionItem] = []
    if takeoff_alt_rel_m is not None:
        lat, lon, _ = waypoints[0]
        items.append(MissionItem(0, CMD_NAV_TAKEOFF, FRAME_GLOBAL_RELATIVE_ALT_INT, _e7(lat),
                                 _e7(lon), takeoff_alt_rel_m, p4=math.nan))
    for lat, lon, alt in waypoints:
        items.append(MissionItem(len(items), CMD_NAV_WAYPOINT, FRAME_GLOBAL_RELATIVE_ALT_INT,
                                 _e7(lat), _e7(lon), alt, p4=math.nan))
    return items


def fence_items(polygon_latlon: list[tuple[float, float]]) -> list[MissionItem]:
    """Inclusion polygon: items type 5001 with p1 = vertex count, MISSION_TYPE_FENCE."""
    n = len(polygon_latlon)
    return [MissionItem(i, CMD_FENCE_POLYGON_VERTEX_INCLUSION, FRAME_GLOBAL_INT, _e7(lat),
                        _e7(lon), 0.0, p1=float(n), mission_type=MISSION_TYPE_FENCE)
            for i, (lat, lon) in enumerate(polygon_latlon)]


def mission_count(mav, tsys: int, n: int, mission_type: int = MISSION_TYPE_MISSION):
    return mav.mission_count_encode(tsys, modes.VEHICLE_COMPID, n, mission_type)


def mission_clear_all(mav, tsys: int, mission_type: int = MISSION_TYPE_MISSION):
    return mav.mission_clear_all_encode(tsys, modes.VEHICLE_COMPID, mission_type)


# --- parameters (byte-wise int32 PARAM_SET encoding) ----------------------------------------

PARAM_TYPE_INT32 = 6  # MAV_PARAM_TYPE_INT32
PARAM_TYPE_REAL32 = 9  # MAV_PARAM_TYPE_REAL32

# PX4 types for the profile keys (UNVERIFIED until `edith sim record-px4` reads them back).
PARAM_TYPES: dict[str, int] = {
    "NAV_DLL_ACT": PARAM_TYPE_INT32,
    "COM_DL_LOSS_T": PARAM_TYPE_INT32,
    "COM_LOW_BAT_ACT": PARAM_TYPE_INT32,
    "GF_ACTION": PARAM_TYPE_INT32,
}


def param_type(name: str) -> int:
    return PARAM_TYPES.get(name, PARAM_TYPE_REAL32)


def int32_to_param_float(v: int) -> float:
    """Byte-wise: the int32's 4 bytes reinterpreted as a float32 (PX4 convention)."""
    return struct.unpack("<f", struct.pack("<i", int(v)))[0]


def param_float_to_int32(f: float) -> int:
    return struct.unpack("<i", struct.pack("<f", f))[0]


def encode_param_value(name: str, value: float) -> tuple[float, int]:
    t = param_type(name)
    return (int32_to_param_float(int(value)) if t == PARAM_TYPE_INT32 else float(value)), t


def decode_param_value(value: float, ptype: int) -> float | int:
    return param_float_to_int32(value) if ptype == PARAM_TYPE_INT32 else value


def param_set(mav, tsys: int, name: str, value: float):
    v, t = encode_param_value(name, value)
    return mav.param_set_encode(tsys, modes.VEHICLE_COMPID, name.encode(), v, t)


def param_request_read(mav, tsys: int, name: str):
    return mav.param_request_read_encode(tsys, modes.VEHICLE_COMPID, name.encode(), -1)


# --- `completed` definitions (interfaces §6) ------------------------------------------------

def takeoff_completed(alt_rel_m: float, target_rel_m: float) -> bool:
    return abs(alt_rel_m - target_rel_m) <= 1.5


def goto_completed(dist_m: float, custom_mode: int) -> bool:
    return dist_m <= 5.0 and custom_mode == modes.AUTO_LOITER


def hold_completed(custom_mode: int) -> bool:
    return custom_mode == modes.AUTO_LOITER


def rtl_land_completed(on_ground: bool, armed: bool) -> bool:
    return on_ground and not armed


def search_completed(last_reached_seq: int, n_items: int) -> bool:
    return last_reached_seq >= n_items - 1
