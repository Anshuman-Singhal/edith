"""YOLOX-Tiny adapter (official static 416² ONNX, ORT CPU, 1 thread) and the 2×2 tiler with
cross-tile IOS merge (PLAN §3.5, C58).

Tiles: 2×2 grid of 692×389 from 1280×720 (15% overlap), each letterboxed into 416² (scale
0.60, pad 114). Output floor 0.10. Classes: person; vehicle (car, motorcycle, bus, truck,
train); COCO animals → other. No other class is emitted (C16).
"""

from __future__ import annotations

import hashlib
import itertools
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

CONF_FLOOR = 0.10
NMS_IOU = 0.45
IOS_MERGE = 0.5
COCO_MAP: dict[int, str] = {0: "person", 2: "vehicle", 3: "vehicle", 5: "vehicle",
                            6: "vehicle", 7: "vehicle"}
COCO_MAP.update({i: "other" for i in range(14, 24)})  # bird … giraffe


@dataclass
class RawDet:
    x1: float
    y1: float
    x2: float
    y2: float
    conf: float
    cls: str
    tile: int | None = None

    @property
    def area(self) -> float:
        return max(0.0, self.x2 - self.x1) * max(0.0, self.y2 - self.y1)


def letterbox(img: np.ndarray, size: int = 416) -> tuple[np.ndarray, float]:
    h, w = img.shape[:2]
    r = min(size / h, size / w)
    out = np.full((size, size, 3), 114, np.uint8)
    nh, nw = int(round(h * r)), int(round(w * r))
    out[:nh, :nw] = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    return out, r


def _grids(size: int, strides=(8, 16, 32)) -> tuple[np.ndarray, np.ndarray]:
    gs, ss = [], []
    for s in strides:
        n = size // s
        xv, yv = np.meshgrid(np.arange(n), np.arange(n))
        gs.append(np.stack((xv, yv), 2).reshape(-1, 2))
        ss.append(np.full((n * n, 1), s))
    return np.concatenate(gs).astype(np.float32), np.concatenate(ss).astype(np.float32)


def decode_yolox(out: np.ndarray, size: int, ratio: float, floor: float = CONF_FLOOR
                 ) -> list[RawDet]:
    """Decode raw YOLOX head output (N, 85) at input ``size`` back to source pixels."""
    grids, strides = _grids(size)
    xy = (out[:, :2] + grids) * strides
    wh = np.exp(np.clip(out[:, 2:4], -10, 10)) * strides
    cls_scores = out[:, 5:] * out[:, 4:5]
    cid = cls_scores.argmax(1)
    score = cls_scores[np.arange(len(cid)), cid]
    keep = score >= floor
    dets: list[RawDet] = []
    boxes = np.concatenate([xy - wh / 2, xy + wh / 2], 1)[keep] / ratio
    for b, s, c in zip(boxes, score[keep], cid[keep], strict=True):
        name = COCO_MAP.get(int(c))
        if name is not None:
            dets.append(RawDet(float(b[0]), float(b[1]), float(b[2]), float(b[3]), float(s), name))
    return nms(dets, NMS_IOU)


def _iou(a: RawDet, b: RawDet) -> float:
    iw = max(0.0, min(a.x2, b.x2) - max(a.x1, b.x1))
    ih = max(0.0, min(a.y2, b.y2) - max(a.y1, b.y1))
    inter = iw * ih
    return inter / max(a.area + b.area - inter, 1e-9)


def ios(a: RawDet, b: RawDet) -> float:
    """Intersection over the smaller box."""
    iw = max(0.0, min(a.x2, b.x2) - max(a.x1, b.x1))
    ih = max(0.0, min(a.y2, b.y2) - max(a.y1, b.y1))
    return iw * ih / max(min(a.area, b.area), 1e-9)


def nms(dets: list[RawDet], thr: float) -> list[RawDet]:
    out: list[RawDet] = []
    for d in sorted(dets, key=lambda d: -d.conf):
        if all(o.cls != d.cls or _iou(o, d) < thr for o in out):
            out.append(d)
    return out


def merge_tiles(dets: list[RawDet], thr: float = IOS_MERGE) -> list[RawDet]:
    """Cross-tile merge: same class, IOS ≥ thr → union box, max conf."""
    out: list[RawDet] = []
    for d in sorted(dets, key=lambda d: -d.conf):
        for o in out:
            if o.cls == d.cls and o.tile != d.tile and ios(o, d) >= thr:
                o.x1, o.y1 = min(o.x1, d.x1), min(o.y1, d.y1)
                o.x2, o.y2 = max(o.x2, d.x2), max(o.y2, d.y2)
                break
        else:
            out.append(RawDet(d.x1, d.y1, d.x2, d.y2, d.conf, d.cls, d.tile))
    return out


def tile_grid(w: int = 1280, h: int = 720, tw: int = 692, th: int = 389
              ) -> list[tuple[int, int, int, int]]:
    xs = [0, w - tw]
    ys = [0, h - th]
    return [(x, y, tw, th) for y, x in itertools.product(ys, xs)]


class YoloxOnnx:
    """One ORT session; ``infer(bgr)`` letterboxes and decodes."""

    def __init__(self, path: str | Path, size: int = 416, threads: int = 1):
        import onnxruntime as ort

        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        so.inter_op_num_threads = 1
        so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        so.log_severity_level = 3
        self.path = Path(path)
        self.sess = ort.InferenceSession(str(path), so, providers=["CPUExecutionProvider"])
        self.inp = self.sess.get_inputs()[0].name
        self.size = size
        self.model = self.path.stem
        h = hashlib.sha256()
        with self.path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        self.sha = h.hexdigest()

    def infer(self, bgr: np.ndarray) -> list[RawDet]:
        img, r = letterbox(bgr, self.size)
        x = img.transpose(2, 0, 1)[None].astype(np.float32)
        out = self.sess.run(None, {self.inp: x})[0][0]
        return decode_yolox(out, self.size, r)


class TiledDetector:
    """2×2 tiles of 692×389 on a 1280×720 frame (frames of other sizes are resized first)."""

    def __init__(self, model: YoloxOnnx, frame_size: tuple[int, int] = (1280, 720)):
        self.model = model
        self.w, self.h = frame_size
        self.tiles = tile_grid(self.w, self.h)
        self.last_ms = 0.0

    def detect(self, bgr: np.ndarray) -> list[RawDet]:
        t0 = time.perf_counter()
        if bgr.shape[1] != self.w or bgr.shape[0] != self.h:
            bgr = cv2.resize(bgr, (self.w, self.h))
        allx: list[RawDet] = []
        for i, (x, y, tw, th) in enumerate(self.tiles):
            for d in self.model.infer(bgr[y:y + th, x:x + tw]):
                allx.append(RawDet(d.x1 + x, d.y1 + y, d.x2 + x, d.y2 + y, d.conf, d.cls, i))
        out = merge_tiles(allx)
        self.last_ms = (time.perf_counter() - t0) * 1000
        return out

    @property
    def tile_scale(self) -> float:
        tw, th = self.tiles[0][2:]
        return min(self.model.size / tw, self.model.size / th)

    def to_detections(self, raw: list[RawDet], frame_meta: dict, t_start_ms: int,
                      t_end_ms: int, det_prefix: str) -> list[dict]:
        """RawDet → interfaces §4 ``Detection`` dicts (placement companion)."""
        out = []
        for k, d in enumerate(raw):
            out.append({
                "det_id": f"{det_prefix}-{frame_meta.get('frame_id')}-{k}",
                "frame_id": frame_meta.get("frame_id"),
                "frame_ts_ms": frame_meta.get("t_capture_ms"),
                "source": {"asset_id": frame_meta.get("asset_id"), "sensor_id": "eo0"},
                "cls": d.cls, "conf": round(d.conf, 4),
                "bbox_norm": [d.x1 / self.w, d.y1 / self.h, (d.x2 - d.x1) / self.w,
                              (d.y2 - d.y1) / self.h],
                "tile": d.tile, "det_px_h": (d.y2 - d.y1) * self.tile_scale,
                "infer": {"placement": "companion", "model": self.model.model,
                          "model_sha": self.model.sha, "t_capture_ms": frame_meta.get("t_capture_ms"),
                          "t_start_ms": t_start_ms, "t_end_ms": t_end_ms},
            })
        return out
