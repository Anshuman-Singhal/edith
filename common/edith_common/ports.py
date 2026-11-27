"""Every port in interfaces §5 (C77). `port(name, i)` adds the per-instance offset `i` and
`EDITH_PORT_BASE` (int env, default 0) so parallel test runs don't collide."""

from __future__ import annotations

import os

__all__ = ["PORTS", "PER_INSTANCE", "TAK_MCAST_GROUP", "port", "port_base"]

WS = 7400                  # TCP/WS companion /v1/ws
HTTP = 7401                # TCP/HTTP companion /healthz /metrics god-view /ui/touch
SHAPER_FROM_VEHICLE = 14540  # +i UDP linkshaper binds; PX4/Mock i sends (vehicle -> shaper)
VEHICLE = 14580            # +i UDP PX4/Mock binds; linkshaper sends (shaper -> vehicle)
COMPANION_MAVLINK = 14740  # +i UDP companion udpin (sysid 245); linkshaper sends
TRUTH_TAP = 14640          # +i UDP simd (cameras + gt) binds; linkshaper unimpaired copy
GCS_RESERVED = 14550       # UDP must be free (doctor fails if bound)
RTP_VIDEO = 5600           # +i UDP/RTP companion FrameSource; camera i sends
FRAME_META = 5700          # +i UDP companion; camera i sends FrameMeta sidecar
DETECTIONS = 5800          # +i UDP companion OffloadDetector; gt_detector / offload sends
MESH_EMU_COMPANION = 16968  # UDP companion binds (mesh-emu CoT)
MESH_EMU_SHAPER = 16969    # UDP linkshaper `tak` binds (mesh-emu CoT)
COT_ROUTER_UDP = 18088     # UDP fake CoT router fan-out
COT_ROUTER_TCP = 18087     # TCP fake CoT router (companion --tak tcp)
TAK_MCAST = 6969           # UDP multicast field mesh (group below)
TAK_MCAST_GROUP = "239.2.3.1"
OTS_PLAIN = 8087
OTS_TLS = 8089
OTS_WEB = 8080

PORTS: dict[str, int] = {
    "ws": WS,
    "http": HTTP,
    "shaper_from_vehicle": SHAPER_FROM_VEHICLE,
    "vehicle": VEHICLE,
    "companion_mavlink": COMPANION_MAVLINK,
    "truth_tap": TRUTH_TAP,
    "gcs_reserved": GCS_RESERVED,
    "rtp_video": RTP_VIDEO,
    "frame_meta": FRAME_META,
    "detections": DETECTIONS,
    "mesh_emu_companion": MESH_EMU_COMPANION,
    "mesh_emu_shaper": MESH_EMU_SHAPER,
    "cot_router_udp": COT_ROUTER_UDP,
    "cot_router_tcp": COT_ROUTER_TCP,
    "tak_mcast": TAK_MCAST,
    "ots_plain": OTS_PLAIN,
    "ots_tls": OTS_TLS,
    "ots_web": OTS_WEB,
}

PER_INSTANCE = frozenset(
    {"shaper_from_vehicle", "vehicle", "companion_mavlink", "truth_tap", "rtp_video",
     "frame_meta", "detections"}
)
MAX_INSTANCES = 10  # per-instance ranges are 10 wide before they would overlap a neighbour


def port_base() -> int:
    v = os.environ.get("EDITH_PORT_BASE", "")
    return int(v) if v.strip() else 0


def port(name: str, i: int = 0, base: int | None = None) -> int:
    """Port for `name` (a key of PORTS), instance `i`, plus EDITH_PORT_BASE (or `base`)."""
    try:
        p = PORTS[name]
    except KeyError:
        raise KeyError(f"unknown port {name!r}; known: {sorted(PORTS)}") from None
    if i:
        if name not in PER_INSTANCE:
            raise ValueError(f"port {name!r} is not per-instance")
        if not 0 <= i < MAX_INSTANCES:
            raise ValueError(f"instance {i} out of range 0..{MAX_INSTANCES - 1}")
    return p + i + (port_base() if base is None else base)
