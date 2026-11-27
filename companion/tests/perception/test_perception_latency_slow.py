"""D8 latency acceptance (slow; run on a quiet machine): YOLOX-Tiny@416, ORT CPU 1 thread,
measured in isolation within ±25% of 62 ms; 2×2 tiled 1280×720 frame p95 ≤ 350 ms."""

import os
import time
from pathlib import Path

import numpy as np
import pytest
from edith_companion.perception.detector import TiledDetector, YoloxOnnx

MODEL = Path(__file__).resolve().parents[3] / "models" / "yolox_tiny.onnx"
pytestmark = [pytest.mark.slow,
              pytest.mark.skipif(not MODEL.is_file(), reason="models/ not fetched")]


def test_yolox_tiny_416_single_thread():
    m = YoloxOnnx(MODEL, threads=1)
    x = np.random.default_rng(0).integers(0, 255, (416, 416, 3), np.uint8)
    for _ in range(5):
        m.infer(x)
    ts = []
    for _ in range(40):
        t0 = time.perf_counter()
        m.infer(x)
        ts.append((time.perf_counter() - t0) * 1000)
    p50 = float(np.median(ts))
    print(f"yolox_tiny@416 1thr p50={p50:.1f} ms p95={np.percentile(ts, 95):.1f} ms "
          f"load={os.getloadavg()}")
    assert 62 * 0.75 <= p50 <= 62 * 1.25


def test_tiled_frame_p95():
    td = TiledDetector(YoloxOnnx(MODEL, threads=1))
    frame = np.random.default_rng(1).integers(0, 255, (720, 1280, 3), np.uint8)
    td.detect(frame)
    ts = []
    for _ in range(20):
        td.detect(frame)
        ts.append(td.last_ms)
    p95 = float(np.percentile(ts, 95))
    print(f"tiled 2x2 p50={np.median(ts):.1f} ms p95={p95:.1f} ms load={os.getloadavg()}")
    assert p95 <= 350
