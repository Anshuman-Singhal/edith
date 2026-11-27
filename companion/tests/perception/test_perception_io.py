"""D8 detector adapter, tiler/IOS merge, OffloadDetector and inset encoder."""

import json
import socket
import time
from pathlib import Path

import cv2
import numpy as np
import pytest
from edith_common import schema
from edith_common.ports import port
from edith_companion.perception import detector as det
from edith_companion.perception.inset import (
    encode_crop,
    encode_inset,
    frame_norm_to_inset_norm,
)
from edith_companion.perception.offload import OffloadDetector, parse_datagram

MODELS = Path(__file__).resolve().parents[3] / "models"


def test_tile_grid_matches_plan():
    tiles = det.tile_grid()
    assert tiles == [(0, 0, 692, 389), (588, 0, 692, 389), (0, 331, 692, 389),
                     (588, 331, 692, 389)]
    assert abs((692 - 588) / 692 - 0.15) < 0.01 and abs((389 - 331) / 389 - 0.15) < 0.01
    assert abs(416 / 692 - 0.60) < 0.01


def test_ios_merge_across_tiles():
    a = det.RawDet(580, 100, 600, 150, 0.8, "person", tile=0)      # cut at tile 0's edge
    b = det.RawDet(585, 100, 605, 150, 0.6, "person", tile=1)
    c = det.RawDet(585, 100, 605, 150, 0.6, "vehicle", tile=1)      # other class: kept
    out = det.merge_tiles([a, b, c])
    assert len(out) == 2
    p = next(d for d in out if d.cls == "person")
    assert (p.x1, p.x2, p.conf) == (580, 605, 0.8)
    assert det.ios(a, b) >= 0.5


def test_decode_yolox_synthetic_head():
    n = sum((416 // s) ** 2 for s in (8, 16, 32))
    out = np.zeros((n, 85), np.float32)
    out[:, 2:4] = -5
    # one strong person at stride-8 cell (10, 20): centre (84, 164)
    i = 20 * 52 + 10
    out[i, 0:2] = 0.5
    out[i, 2:4] = np.log(4.0)                     # 32 px
    out[i, 4] = 0.9
    out[i, 5] = 0.9                               # person
    j = 21 * 52 + 10                              # a "giraffe" → other; a "chair" → dropped
    out[j, 4], out[j, 5 + 23] = 0.8, 0.8
    k = 30 * 52 + 30
    out[k, 4], out[k, 5 + 56] = 0.9, 0.9
    dets = det.decode_yolox(out, 416, 0.5)
    by = {d.cls: d for d in dets}
    assert set(by) == {"person", "other"}
    p = by["person"]
    assert abs((p.x1 + p.x2) / 2 - 84 / 0.5) < 1e-3 and abs((p.x2 - p.x1) - 64) < 1e-3
    assert abs(p.conf - 0.81) < 1e-6


@pytest.mark.skipif(not (MODELS / "yolox_tiny.onnx").is_file(),
                    reason="models/ not fetched (./edith fetch models)")
def test_yolox_tiny_runs_tiled_and_emits_schema_valid_detections():
    m = det.YoloxOnnx(MODELS / "yolox_tiny.onnx")
    td = det.TiledDetector(m)
    frame = np.random.default_rng(0).integers(0, 255, (720, 1280, 3), np.uint8)
    raw = td.detect(frame)
    meta = {"frame_id": 7, "t_capture_ms": 1000, "asset_id": "D1"}
    for d in td.to_detections(raw, meta, 1000, 1100, "D1"):
        schema.validate("Detection", d)
    assert all(d.cls in ("person", "vehicle", "other") for d in raw)


def test_offload_detector_udp():
    rx = OffloadDetector(instance=2)
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        d = {"det_id": "gt-D3-5-0", "frame_id": 5, "frame_ts_ms": 1, "cls": "person",
             "conf": 0.5, "bbox_norm": [0.1, 0.1, 0.01, 0.02]}
        tx.sendto(json.dumps([d]).encode(), ("127.0.0.1", port("detections", 2)))
        tx.sendto(b"[]", ("127.0.0.1", port("detections", 2)))
        tx.sendto(json.dumps([dict(d, cls="hostile")]).encode(),
                  ("127.0.0.1", port("detections", 2)))
        got = []
        deadline = time.time() + 2
        while len(got) < 2 and time.time() < deadline:
            got += rx.poll()
            time.sleep(0.01)
        assert got[0] == (5, [d]) and got[1] == (None, [])
        time.sleep(0.05)
        rx.poll()
        assert rx.bad == 1
    finally:
        tx.close()
        rx.close()
    assert parse_datagram(b'{"frame_id": 3, "detections": []}') == (3, [])


def test_inset_jpeg_and_night_green():
    frame = np.full((720, 1280, 3), (40, 120, 200), np.uint8)
    for night in (False, True):
        jpg = encode_inset(frame, night=night)
        img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
        assert img.shape == (240, 320, 3)
        mid = img[120, 160].astype(int)
        if night:
            assert mid[0] < 12 and mid[2] < 12 and mid[1] > 40
        else:
            assert abs(mid[2] - 200) < 12
    crop = cv2.imdecode(np.frombuffer(encode_crop(frame, [0.5, 0.5, 0.02, 0.05]), np.uint8),
                        cv2.IMREAD_COLOR)
    assert crop.shape == (72, 96, 3)
    x, y, w, h = frame_norm_to_inset_norm([0.0, 0.0, 1.0, 1.0])
    assert abs(x) < 1e-9 and abs(y - 30 / 240) < 1e-9 and abs(h - 180 / 240) < 1e-9
