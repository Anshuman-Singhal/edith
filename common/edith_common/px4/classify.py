"""Outbound MAVLink classifier table (interfaces §6, C50).

Shared by the companion's ``assets/outbound.py`` (WS-B) and the linkshaper wire log (WS-D).
``classify(msg)`` returns ``"MOTION"``, ``"SAFE"``, ``"CONFIG"`` or ``None`` (anything else:
the adapter drops it and logs ``outbound.blocked``). Works on pymavlink message objects or on
any object with ``get_type()`` and the same field names.
"""

from __future__ import annotations

from edith_common.px4 import encode as E
from edith_common.px4 import modes

MOTION, SAFE, CONFIG = "MOTION", "SAFE", "CONFIG"

MOTION_COMMANDS = frozenset({
    E.CMD_COMPONENT_ARM_DISARM, E.CMD_NAV_TAKEOFF, E.CMD_DO_REPOSITION, E.CMD_DO_ORBIT,
    E.CMD_MISSION_START, E.CMD_NAV_RETURN_TO_LAUNCH, E.CMD_NAV_LAND, E.CMD_DO_CHANGE_SPEED,
})
CONFIG_COMMANDS = frozenset({E.CMD_SET_MESSAGE_INTERVAL})
MISSION_UPLOAD_TYPES = frozenset({"MISSION_COUNT", "MISSION_ITEM_INT", "MISSION_CLEAR_ALL"})
CONFIG_TYPES = frozenset({"HEARTBEAT", "SET_MESSAGE_INTERVAL", "PARAM_SET",
                          "PARAM_REQUEST_READ"})

# Human-readable table (for docs and the god-view).
TABLE: dict[str, tuple[str, ...]] = {
    MOTION: ("arm/disarm 400", "NAV_TAKEOFF 22", "DO_REPOSITION 192", "DO_ORBIT 34",
             "MISSION_START 300", "MISSION_COUNT/ITEM_INT/CLEAR_ALL (mission type)",
             "NAV_RETURN_TO_LAUNCH 20", "NAV_LAND 21", "DO_CHANGE_SPEED 178",
             "DO_SET_MODE 176 != AUTO.LOITER"),
    SAFE: ("DO_SET_MODE 176 AUTO.LOITER (hold) and its retries",),
    CONFIG: ("HEARTBEAT", "SET_MESSAGE_INTERVAL (msg or cmd 511)", "PARAM_SET",
             "PARAM_REQUEST_READ", "MISSION_COUNT/ITEM_INT/CLEAR_ALL (fence type)"),
}


def _set_mode_target(msg) -> int:
    return modes.encode_mode(int(msg.param2), int(msg.param3))


def classify_command(command: int, msg=None) -> str | None:
    if command == E.CMD_DO_SET_MODE:
        if msg is not None and _set_mode_target(msg) == modes.AUTO_LOITER:
            return SAFE
        return MOTION
    if command in MOTION_COMMANDS:
        return MOTION
    if command in CONFIG_COMMANDS:
        return CONFIG
    return None


def classify(msg) -> str | None:
    t = msg.get_type()
    if t in ("COMMAND_INT", "COMMAND_LONG"):
        return classify_command(int(msg.command), msg)
    if t in MISSION_UPLOAD_TYPES:
        mt = int(getattr(msg, "mission_type", 0))
        if mt == E.MISSION_TYPE_FENCE:
            return CONFIG
        if mt == E.MISSION_TYPE_MISSION:
            return MOTION
        return MOTION if t == "MISSION_CLEAR_ALL" else None  # CLEAR_ALL of type ALL clears missions
    if t in CONFIG_TYPES:
        return CONFIG
    return None
