"""PX4 identity and custom-mode encoding (sim spec §2, interfaces §6).

``custom_mode = main << 16 | sub << 24``. Names are ``MAIN.SUB`` (``AUTO.LOITER``,
``POSCTL.ORBIT``) or just ``MAIN`` when the sub mode is 0.
"""

from __future__ import annotations

AUTOPILOT_PX4 = 12  # MAV_AUTOPILOT_PX4
TYPE_QUADROTOR = 2  # MAV_TYPE_QUADROTOR
TYPE_GCS = 6  # MAV_TYPE_GCS
COMPANION_SYSID = 245
COMPANION_COMPID = 190  # MAV_COMP_ID_MISSIONPLANNER
VEHICLE_COMPID = 1  # MAV_COMP_ID_AUTOPILOT1

BASE_CUSTOM_MODE_ENABLED = 1  # MAV_MODE_FLAG_CUSTOM_MODE_ENABLED
BASE_SAFETY_ARMED = 128  # MAV_MODE_FLAG_SAFETY_ARMED


def sysid_for(instance: int) -> int:
    """Vehicle sysid = instance + 1."""
    return instance + 1


MAIN = {"MANUAL": 1, "ALTCTL": 2, "POSCTL": 3, "AUTO": 4, "ACRO": 5, "OFFBOARD": 6,
        "STABILIZED": 7}
SUB = {
    "AUTO": {"READY": 1, "TAKEOFF": 2, "LOITER": 3, "MISSION": 4, "RTL": 5, "LAND": 6,
             "FOLLOW_TARGET": 8, "PRECLAND": 9},
    "POSCTL": {"POSCTL": 0, "ORBIT": 1},
}
_MAIN_NAME = {v: k for k, v in MAIN.items()}


def encode_mode(main: int, sub: int = 0) -> int:
    return (main << 16) | (sub << 24)


def decode_mode(custom_mode: int) -> tuple[int, int]:
    return (custom_mode >> 16) & 0xFF, (custom_mode >> 24) & 0xFF


def mode_from_name(name: str) -> int:
    main_s, _, sub_s = name.partition(".")
    main = MAIN[main_s]
    sub = SUB.get(main_s, {})[sub_s] if sub_s else 0
    return encode_mode(main, sub)


def mode_name(custom_mode: int) -> str:
    main, sub = decode_mode(custom_mode)
    main_s = _MAIN_NAME.get(main, f"MAIN{main}")
    if sub == 0:
        return main_s
    subs = {v: k for k, v in SUB.get(main_s, {}).items()}
    return f"{main_s}.{subs.get(sub, f'SUB{sub}')}"


# The modes the system uses (sim spec §2).
AUTO_TAKEOFF = mode_from_name("AUTO.TAKEOFF")
AUTO_LOITER = mode_from_name("AUTO.LOITER")  # main 4 / sub 3: the hold
AUTO_MISSION = mode_from_name("AUTO.MISSION")
AUTO_RTL = mode_from_name("AUTO.RTL")
AUTO_LAND = mode_from_name("AUTO.LAND")
POSCTL_ORBIT = mode_from_name("POSCTL.ORBIT")  # main 3 / sub 1

# NAV_DLL_ACT values (PX4 v1.18 [probed by sim r2]: 2 = Return).
DLL_ACTION_MODE = {1: AUTO_LOITER, 2: AUTO_RTL, 3: AUTO_LAND}
