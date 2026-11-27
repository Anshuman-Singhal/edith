"""OffloadDetector: ``[Detection]`` JSON datagrams on UDP 5800+i from gt_detector (sim) or a P3
offload server (C59). One datagram per processed frame; an empty frame is ``[]`` and is
attributed to the newest FrameMeta of that feed. A JSON object ``{"detections": [...],
"frame_id": ...}`` is accepted too."""

from __future__ import annotations

import json
import socket

from edith_common.ports import port

OFFLOAD_PORT = 5800


def parse_datagram(raw: bytes) -> tuple[int | None, list[dict]]:
    doc = json.loads(raw)
    if isinstance(doc, dict):
        dets = list(doc.get("detections", []))
        fid = doc.get("frame_id")
    else:
        dets = list(doc)
        fid = None
    if fid is None and dets:
        fid = dets[0].get("frame_id")
    for d in dets:
        if d.get("cls") not in ("person", "vehicle", "other"):
            raise ValueError(f"bad class {d.get('cls')!r}")
    return (int(fid) if fid is not None else None), dets


class OffloadDetector:
    def __init__(self, instance: int = 0, host: str = "127.0.0.1", bind: bool = True):
        self.instance = instance
        self.sock = None
        self.bad = 0
        if bind:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind((host, port("detections", instance)))
            self.sock.setblocking(False)

    def poll(self, max_datagrams: int = 256) -> list[tuple[int | None, list[dict]]]:
        out = []
        if self.sock is None:
            return out
        for _ in range(max_datagrams):
            try:
                raw = self.sock.recv(65535)
            except BlockingIOError:
                break
            try:
                out.append(parse_datagram(raw))
            except (ValueError, TypeError, AttributeError):
                self.bad += 1
        return out

    def close(self) -> None:
        if self.sock is not None:
            self.sock.close()
