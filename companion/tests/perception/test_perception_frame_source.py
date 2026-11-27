"""D8 FrameSource: RTP H.264 + SEI frame_id, self-generated with PyAV (test-only encoder; the
runtime encoder lives in sim/, C84). Frame↔sidecar sync is verified by a frame-ID barcode
burned into each test frame; a receiver joining mid-stream matches ≥99% of frames; the pts
anchor fallback is exercised by stripping SEI."""

import json
import socket
import struct
import time
from fractions import Fraction

import av
import numpy as np
from edith_common.ports import port
from edith_companion.perception.frame_source import (
    FrameSource,
    build_sei_nal,
    parse_sei_frame_id,
)

W, H, FPS = 320, 240, 15
BITS = 16


def barcode(fid: int) -> np.ndarray:
    img = np.full((H, W, 3), 90, np.uint8)
    img[60:, :] = (np.arange(W)[None, :, None] * 3 % 255).astype(np.uint8)  # some texture
    for b in range(BITS):
        if fid >> b & 1:
            img[0:20, b * 20:(b + 1) * 20] = 255
        else:
            img[0:20, b * 20:(b + 1) * 20] = 0
    return img


def read_barcode(img: np.ndarray) -> int:
    v = 0
    for b in range(BITS):
        if img[4:16, b * 20 + 4:b * 20 + 16].mean() > 128:
            v |= 1 << b
    return v


def split_nals(data: bytes) -> list[bytes]:
    out, i, n = [], 0, len(data)
    starts = []
    while i < n - 3:
        if data[i:i + 3] == b"\x00\x00\x01":
            starts.append(i + 3)
            i += 3
        else:
            i += 1
    for k, s in enumerate(starts):
        e = starts[k + 1] - 3 if k + 1 < len(starts) else n
        nal = data[s:e]
        while nal.endswith(b"\x00"):
            nal = nal[:-1]
        out.append(nal)
    return out


def rtp_packets(nals: list[bytes], seq: int, ts: int, mtu: int = 1000) -> list[bytes]:
    pkts = []
    for j, nal in enumerate(nals):
        last = j == len(nals) - 1
        if len(nal) <= mtu:
            chunks = [(nal, None)]
        else:
            hdr, body = nal[0], nal[1:]
            parts = [body[i:i + mtu] for i in range(0, len(body), mtu)]
            chunks = []
            for k, part in enumerate(parts):
                fu_ind = (hdr & 0xE0) | 28
                fu_hdr = (0x80 if k == 0 else 0) | (0x40 if k == len(parts) - 1 else 0) | (hdr & 0x1F)
                chunks.append((bytes([fu_ind, fu_hdr]) + part, k == len(parts) - 1))
        for c, endflag in chunks:
            m = last and (endflag is None or endflag)
            pkts.append(struct.pack(">BBHII", 0x80, (0x80 if m else 0) | 96, seq & 0xFFFF,
                                    ts & 0xFFFFFFFF, 0x1234) + c)
            seq += 1
    return pkts


def stream(n_frames: int, sei_until: int | None = None, ts0: int = 0xFFFF0000):
    """Yields (frame_id, [rtp packets]) — pts = frame_id·90000/fps + ts0 (wraps 32 bits)."""
    enc = av.CodecContext.create("libx264", "w")
    enc.width, enc.height, enc.pix_fmt = W, H, "yuv420p"
    enc.time_base = Fraction(1, FPS)
    enc.options = {"tune": "zerolatency", "preset": "ultrafast", "bframes": "0",
                   "x264-params": "repeat-headers=1:keyint=15:min-keyint=15:scenecut=0"}
    seq = 100
    for fid in range(n_frames):
        vf = av.VideoFrame.from_ndarray(barcode(fid), format="bgr24").reformat(format="yuv420p")
        vf.pts = fid
        data = b"".join(bytes(p) for p in enc.encode(vf))
        nals = split_nals(data)
        if sei_until is None or fid < sei_until:
            nals = [build_sei_nal(fid)] + nals
        pk = rtp_packets(nals, seq, ts0 + fid * 90000 // FPS)
        seq += len(pk)
        yield fid, pk


def meta(fid):
    return {"frame_id": fid, "t_capture_ms": 1000 + fid * 66, "t_sim_ms": fid * 66,
            "asset_id": "D1"}


def test_sei_round_trip_with_emulation_prevention():
    for fid in (0, 1, 3, 0x000003, 0x0300000000, 2**40 + 7, 2**63):
        nal = build_sei_nal(fid)
        assert b"\x00\x00\x00" not in nal[1:] and b"\x00\x00\x01" not in nal[1:]
        assert parse_sei_frame_id(nal) == fid
    assert parse_sei_frame_id(b"\x06\x05\x10" + b"X" * 16 + b"\x80") is None


def test_mid_stream_join_sei_sync():
    fs = FrameSource("D1", fps=FPS)
    total = good = 0
    for fid, pkts in stream(90):
        fs.push_meta(json.dumps(meta(fid)).encode())
        if fid < 22:                 # join mid-stream (mid-GOP)
            continue
        for p in pkts:
            for f in fs.push_rtp(p):
                total += 1
                good += (f.frame_id == read_barcode(f.image) and f.meta
                         and f.meta["frame_id"] == f.frame_id and f.via == "sei")
    assert total >= 55             # decoding starts at the next IDR (keyint 15 → frame 30)
    assert good / total >= 0.99
    assert fs.latest.frame_id == 89


def test_pts_anchor_fallback_across_rtp_wrap():
    fs = FrameSource("D1", fps=FPS)
    total = good = 0
    for fid, pkts in stream(60, sei_until=5):
        fs.push_meta(meta(fid))
        for p in pkts:
            for f in fs.push_rtp(p):
                total += 1
                good += f.frame_id == read_barcode(f.image)
                if fid >= 5:
                    assert f.via == "pts"
    assert total == 60 and good / total >= 0.99


def test_udp_receive():
    fs = FrameSource("D1", instance=3, fps=FPS, bind=True)
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        for fid, pkts in stream(20):
            tx.sendto(json.dumps(meta(fid)).encode(), ("127.0.0.1", port("frame_meta", 3)))
            for p in pkts:
                tx.sendto(p, ("127.0.0.1", port("rtp_video", 3)))
            time.sleep(0.002)
            fs.poll()
        deadline = time.time() + 2
        while (fs.latest is None or fs.latest.frame_id != 19) and time.time() < deadline:
            fs.poll()
            time.sleep(0.01)
        assert fs.latest.frame_id == 19 and fs.latest.meta["frame_id"] == 19
        assert read_barcode(fs.latest.image) == 19
    finally:
        tx.close()
        fs.close()
