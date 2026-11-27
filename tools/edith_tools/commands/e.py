"""WS-E CLI: `./edith bench goal2|placement`.

goal2 is D9 (P1, not built yet). `placement --latency` runs the D8 detector timing
(YOLOX-Tiny@416, ORT CPU, 1 thread, isolated; 2×2 tiled 1280×720 frame).
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from edith_tools.cli.util import repo_root


def _latency(threads: int, n: int) -> int:
    import numpy as np
    from edith_companion.perception.detector import TiledDetector, YoloxOnnx

    model = repo_root() / "models" / "yolox_tiny.onnx"
    if not model.is_file():
        print("models/yolox_tiny.onnx missing: run ./edith fetch models", file=sys.stderr)
        return 1
    m = YoloxOnnx(model, threads=threads)
    x = np.random.default_rng(0).integers(0, 255, (416, 416, 3), np.uint8)
    for _ in range(5):
        m.infer(x)
    ts = []
    for _ in range(n):
        t0 = time.perf_counter()
        m.infer(x)
        ts.append((time.perf_counter() - t0) * 1000)
    td = TiledDetector(m)
    f = np.random.default_rng(1).integers(0, 255, (720, 1280, 3), np.uint8)
    tt = []
    for _ in range(max(5, n // 2)):
        td.detect(f)
        tt.append(td.last_ms)
    print(f"yolox_tiny@416 threads={threads}: p50 {np.median(ts):.1f} ms, "
          f"p95 {np.percentile(ts, 95):.1f} ms (target 62 ms ±25%)")
    print(f"tiled 2x2 frame: p50 {np.median(tt):.1f} ms, p95 {np.percentile(tt, 95):.1f} ms "
          f"(target p95 <= 350 ms); loadavg {os.getloadavg()}")
    return 0


def main(argv: list[str]) -> int:
    sub = argv[1] if len(argv) > 1 else "goal2"
    if sub == "placement":
        ap = argparse.ArgumentParser(prog="edith bench placement")
        ap.add_argument("--latency", action="store_true", default=True)
        ap.add_argument("--threads", type=int, default=1)
        ap.add_argument("-n", type=int, default=40)
        a = ap.parse_args(argv[2:])
        return _latency(a.threads, a.n)
    print(f"edith bench {sub}: not implemented yet (WS-E, D9 goal2 is P1)", file=sys.stderr)
    return 2
