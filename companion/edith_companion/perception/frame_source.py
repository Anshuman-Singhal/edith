"""Latest-frame FrameSource: RTP H.264 (RFC 6184) with an SEI ``frame_id`` on 5600+i, plus the
FrameMeta sidecar (JSON) on 5700+i (PLAN §1.4 loop 2, C60; sim spec §4).

Frame sync: every access unit is preceded by an SEI ``user_data_unregistered`` NAL whose
payload is ``SEI_UUID`` (16 bytes) + frame_id (uint64 big-endian). The SEI is parsed from the
packet bytes before decoding, so a receiver joining mid-stream syncs on the first SEI.
Fallback when an AU has no SEI: ``frame_id = anchor_id + round((rtp_ts − anchor_ts)·fps/90000)``
(the sender's pts is ``frame_id·90000/fps``), anchored on the first SEI-bearing AU or, if the
stream never carries SEI, on the first AU paired with the newest sidecar.

Decoding uses PyAV (FFmpeg h264 decoder); encoding is never done here (C84).
"""

from __future__ import annotations

import json
import socket
import struct
from collections import OrderedDict
from dataclasses import dataclass

import numpy as np

from ._compat import port

SEI_UUID = b"EDITH-FRAMEID-v1"  # 16 bytes; simd (D7) writes the same
assert len(SEI_UUID) == 16
RTP_PORT, SIDECAR_PORT = 5600, 5700
START = b"\x00\x00\x00\x01"


# ------------------------------------------------------------------------ SEI helpers -------

def _ebsp_to_rbsp(b: bytes) -> bytes:
    out = bytearray()
    zeros = 0
    for x in b:
        if zeros >= 2 and x == 3:
            zeros = 0
            continue
        out.append(x)
        zeros = zeros + 1 if x == 0 else 0
    return bytes(out)


def _rbsp_to_ebsp(b: bytes) -> bytes:
    out = bytearray()
    zeros = 0
    for x in b:
        if zeros >= 2 and x <= 3:
            out.append(3)
            zeros = 0
        out.append(x)
        zeros = zeros + 1 if x == 0 else 0
    return bytes(out)


def build_sei_nal(frame_id: int) -> bytes:
    """SEI NAL (no start code) carrying frame_id; for simd and tests."""
    payload = SEI_UUID + struct.pack(">Q", frame_id)
    body = bytearray([5])            # payloadType 5 = user_data_unregistered
    n = len(payload)
    while n >= 255:
        body.append(255)
        n -= 255
    body.append(n)
    body += payload + b"\x80"        # rbsp trailing bits
    return b"\x06" + _rbsp_to_ebsp(bytes(body))


def parse_sei_frame_id(nal: bytes) -> int | None:
    if not nal or (nal[0] & 0x1F) != 6:
        return None
    b = _ebsp_to_rbsp(nal[1:])
    i = 0
    while i < len(b) and b[i] != 0x80:
        pt = 0
        while i < len(b) and b[i] == 255:
            pt += 255
            i += 1
        if i >= len(b):
            return None
        pt += b[i]
        i += 1
        size = 0
        while i < len(b) and b[i] == 255:
            size += 255
            i += 1
        if i >= len(b):
            return None
        size += b[i]
        i += 1
        data = b[i:i + size]
        i += size
        if pt == 5 and data[:16] == SEI_UUID:
            rest = data[16:]
            if len(rest) >= 8:
                return struct.unpack(">Q", rest[:8])[0]
            if rest.strip().isdigit():
                return int(rest.strip())
    return None


# ------------------------------------------------------------------------ RTP ---------------

@dataclass
class AccessUnit:
    rtp_ts: int
    nals: list[bytes]
    frame_id: int | None = None

    def annexb(self) -> bytes:
        return b"".join(START + n for n in self.nals if (n[0] & 0x1F) != 6)

    @property
    def has_sps(self) -> bool:
        return any((n[0] & 0x1F) == 7 for n in self.nals)


class RtpH264Depacketizer:
    """Single NAL, STAP-A and FU-A; AU boundary on marker bit or timestamp change."""

    def __init__(self) -> None:
        self._nals: list[bytes] = []
        self._ts: int | None = None
        self._fu: bytearray | None = None
        self._last_seq: int | None = None
        self.lost_packets = 0

    def push(self, pkt: bytes) -> list[AccessUnit]:
        if len(pkt) < 12 or (pkt[0] >> 6) != 2:
            return []
        cc = pkt[0] & 0x0F
        has_ext = bool(pkt[0] & 0x10)
        marker = bool(pkt[1] & 0x80)
        seq, ts = struct.unpack(">HI", pkt[2:8])
        off = 12 + 4 * cc
        if has_ext:
            if len(pkt) < off + 4:
                return []
            off += 4 + 4 * struct.unpack(">H", pkt[off + 2:off + 4])[0]
        payload = pkt[off:]
        if pkt[0] & 0x20 and payload:  # padding
            payload = payload[:-payload[-1]]
        out: list[AccessUnit] = []
        if self._last_seq is not None and seq != (self._last_seq + 1) & 0xFFFF:
            self.lost_packets += 1
            self._fu = None
        self._last_seq = seq
        if self._ts is not None and ts != self._ts and self._nals:
            out.append(self._flush())
        self._ts = ts
        if not payload:
            return out
        t = payload[0] & 0x1F
        if 1 <= t <= 23:
            self._nals.append(bytes(payload))
        elif t == 24:  # STAP-A
            i = 1
            while i + 2 <= len(payload):
                n = struct.unpack(">H", payload[i:i + 2])[0]
                self._nals.append(bytes(payload[i + 2:i + 2 + n]))
                i += 2 + n
        elif t == 28 and len(payload) >= 2:  # FU-A
            s, e = payload[1] & 0x80, payload[1] & 0x40
            if s:
                self._fu = bytearray([(payload[0] & 0xE0) | (payload[1] & 0x1F)])
            if self._fu is not None:
                self._fu += payload[2:]
                if e:
                    self._nals.append(bytes(self._fu))
                    self._fu = None
        if marker and self._nals:
            out.append(self._flush())
        return out

    def _flush(self) -> AccessUnit:
        au = AccessUnit(self._ts or 0, self._nals)
        self._nals = []
        for n in au.nals:
            fid = parse_sei_frame_id(n)
            if fid is not None:
                au.frame_id = fid
                break
        return au


# ------------------------------------------------------------------------ decode + sync ------

@dataclass
class Frame:
    frame_id: int
    rtp_ts: int
    image: np.ndarray            # BGR
    meta: dict | None
    via: str                     # sei | pts


class FrameSync:
    """frame_id from SEI, else the pts anchor; holds the latest sidecars by frame_id."""

    def __init__(self, fps: float, keep: int = 256):
        self.fps = fps
        self.anchor: tuple[int, int] | None = None   # (unwrapped rtp_ts, frame_id)
        self.metas: OrderedDict[int, dict] = OrderedDict()
        self.keep = keep
        self._ts_hi = 0
        self._ts_last: int | None = None

    def _unwrap(self, ts: int) -> int:
        if self._ts_last is not None and ts < self._ts_last and self._ts_last - ts > 1 << 31:
            self._ts_hi += 1 << 32
        self._ts_last = ts
        return ts + self._ts_hi

    def on_meta(self, meta: dict) -> None:
        self.metas[int(meta["frame_id"])] = meta
        while len(self.metas) > self.keep:
            self.metas.popitem(last=False)

    def frame_id(self, au: AccessUnit) -> tuple[int | None, str]:
        ts = self._unwrap(au.rtp_ts)
        if au.frame_id is not None:
            if self.anchor is None:
                self.anchor = (ts, au.frame_id)
            return au.frame_id, "sei"
        if self.anchor is None and self.metas:
            self.anchor = (ts, next(reversed(self.metas)))
        if self.anchor is None:
            return None, "none"
        return self.anchor[1] + round((ts - self.anchor[0]) * self.fps / 90000.0), "pts"


class H264Decoder:
    def __init__(self) -> None:
        import av

        self._av = av
        self.ctx = av.CodecContext.create("h264", "r")
        self.ready = False
        self.errors = 0

    def decode(self, au: AccessUnit) -> list[np.ndarray]:
        if not self.ready:
            if not au.has_sps:
                return []
            self.ready = True
        try:
            frames = self.ctx.decode(self._av.Packet(au.annexb()))
        except self._av.error.FFmpegError:
            self.errors += 1
            return []
        return [f.to_ndarray(format="bgr24") for f in frames]


class FrameSource:
    """Receives RTP and sidecar datagrams (sockets or ``push_*``) and keeps the latest frame."""

    def __init__(self, asset_id: str, instance: int = 0, fps: float = 15.0,
                 bind: bool = False, host: str = "127.0.0.1"):
        self.asset_id = asset_id
        self.depay = RtpH264Depacketizer()
        self.sync = FrameSync(fps)
        self.dec = H264Decoder()
        self.latest: Frame | None = None
        self.pending: list[Frame] = []
        self.frames_out = 0
        self.rtp_sock = self.meta_sock = None
        if bind:
            self.rtp_sock = _udp(host, port(RTP_PORT, instance))
            self.meta_sock = _udp(host, port(SIDECAR_PORT, instance))

    def push_meta(self, raw: bytes | dict) -> None:
        meta = json.loads(raw) if isinstance(raw, bytes | str) else raw
        self.sync.on_meta(meta)
        still = []
        for f in self.pending:
            f.meta = self.sync.metas.get(f.frame_id)
            if f.meta is None:
                still.append(f)
        self.pending = still[-8:]

    def push_rtp(self, pkt: bytes) -> list[Frame]:
        out = []
        for au in self.depay.push(pkt):
            fid, via = self.sync.frame_id(au)
            for img in self.dec.decode(au):
                if fid is None:
                    continue
                f = Frame(fid, au.rtp_ts, img, self.sync.metas.get(fid), via)
                if f.meta is None:
                    self.pending.append(f)
                self.latest = f
                self.frames_out += 1
                out.append(f)
        return out

    def poll(self, max_packets: int = 512) -> Frame | None:
        """Drain both sockets (non-blocking) and return the latest frame."""
        for sock, fn in ((self.meta_sock, self.push_meta), (self.rtp_sock, self.push_rtp)):
            if sock is None:
                continue
            for _ in range(max_packets):
                try:
                    data = sock.recv(65535)
                except BlockingIOError:
                    break
                fn(data)
        return self.latest

    def close(self) -> None:
        for s in (self.rtp_sock, self.meta_sock):
            if s is not None:
                s.close()


def _udp(host: str, p: int) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 << 20)
    s.bind((host, p))
    s.setblocking(False)
    return s
