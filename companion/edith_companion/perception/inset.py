"""Inset encoder (interfaces §3: ``video.down`` JPEG 320×240 q≈70, boxes not burned in;
``video.crop`` JPEG 96×72). Night mode renders a dim green luminance map so the inset does
not wreck dark adaptation. Frames are letterboxed (no crop), so boxes map with
``frame_norm_to_inset_norm``."""

from __future__ import annotations

import cv2
import numpy as np

from .geo import CamPose, Intrinsics, ground_to_pixel

INSET_W, INSET_H, CROP_W, CROP_H = 320, 240, 96, 72
NIGHT_GAIN = 0.6


def _letterbox(img: np.ndarray, w: int, h: int) -> tuple[np.ndarray, float, int, int]:
    ih, iw = img.shape[:2]
    s = min(w / iw, h / ih)
    nw, nh = int(round(iw * s)), int(round(ih * s))
    out = np.zeros((h, w, 3), np.uint8)
    ox, oy = (w - nw) // 2, (h - nh) // 2
    out[oy:oy + nh, ox:ox + nw] = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
    return out, s, ox, oy


def night_green(img: np.ndarray) -> np.ndarray:
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32) * NIGHT_GAIN
    out = np.zeros_like(img)
    out[..., 1] = np.clip(g, 0, 255).astype(np.uint8)
    return out


def encode_inset(frame_bgr: np.ndarray, night: bool = False, quality: int = 70) -> bytes:
    img, *_ = _letterbox(frame_bgr, INSET_W, INSET_H)
    if night:
        img = night_green(img)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    assert ok
    return buf.tobytes()


def encode_crop(frame_bgr: np.ndarray, bbox_norm, night: bool = False, pad: float = 0.5,
                quality: int = 80) -> bytes:
    h, w = frame_bgr.shape[:2]
    x, y, bw, bh = bbox_norm
    cx, cy = (x + bw / 2) * w, (y + bh / 2) * h
    side_w = max(bw * w, bh * h * CROP_W / CROP_H) * (1 + pad)
    side_h = side_w * CROP_H / CROP_W
    x0, y0 = int(max(0, cx - side_w / 2)), int(max(0, cy - side_h / 2))
    x1, y1 = int(min(w, cx + side_w / 2)), int(min(h, cy + side_h / 2))
    crop = frame_bgr[y0:max(y1, y0 + 1), x0:max(x1, x0 + 1)]
    img, *_ = _letterbox(crop, CROP_W, CROP_H)
    if night:
        img = night_green(img)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    assert ok
    return buf.tobytes()


def frame_norm_to_inset_norm(bbox_norm, frame_w: int = 1280, frame_h: int = 720):
    s = min(INSET_W / frame_w, INSET_H / frame_h)
    ox, oy = (INSET_W - frame_w * s) / 2, (INSET_H - frame_h * s) / 2
    x, y, bw, bh = bbox_norm
    return [(x * frame_w * s + ox) / INSET_W, (y * frame_h * s + oy) / INSET_H,
            bw * frame_w * s / INSET_W, bh * frame_h * s / INSET_H]


def reproject_box(e: float, n: float, last_bbox_norm, pose: CamPose, K: Intrinsics):
    """Box for a metric track in the *current* frame: bottom-centre at the reprojected ground
    position, size from the last detection (C56). None if out of view."""
    px = ground_to_pixel(pose, K, e, n)
    if px is None:
        return None
    u, v = px
    if not (0 <= u <= K.w and 0 <= v <= K.h):
        return None
    _, _, bw, bh = last_bbox_norm if last_bbox_norm else (0, 0, 0.02, 0.04)
    return [u / K.w - bw / 2, v / K.h - bh, bw, bh]
