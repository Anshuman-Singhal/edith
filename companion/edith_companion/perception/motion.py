"""Inter-tick camera-motion homography for pseudo (replay) feeds (C95).

ORB + RANSAC at 640×360; if that fails (too few keypoints/inliers, e.g. motion blur or a
textureless frame) fall back to ECC (homography model, coarse-to-fine, initialised from the
last good homography). Returned homographies map previous-frame pixels to current-frame
pixels at the working resolution (default 1280×720).
"""

from __future__ import annotations

import cv2
import numpy as np

WORK = (640, 360)


class MotionEstimator:
    def __init__(self, out_size: tuple[int, int] = (1280, 720), min_inliers: int = 25):
        self.out_size = out_size
        self.min_inliers = min_inliers
        self.orb = cv2.ORB_create(nfeatures=1500, fastThreshold=12)
        self.bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        self._prev: np.ndarray | None = None
        self._prev_kp = None
        self._prev_des = None
        self._last_h = np.eye(3)
        self.stats = {"orb": 0, "ecc": 0, "fail": 0}
        sx, sy = out_size[0] / WORK[0], out_size[1] / WORK[1]
        self._S = np.diag([sx, sy, 1.0])
        self._Si = np.linalg.inv(self._S)

    def reset(self) -> None:
        self._prev = None
        self._last_h = np.eye(3)

    def _gray(self, frame: np.ndarray) -> np.ndarray:
        g = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return cv2.resize(g, WORK, interpolation=cv2.INTER_AREA)

    def update(self, frame: np.ndarray) -> tuple[np.ndarray | None, str]:
        """Feed the next frame; returns (H prev→cur at out_size, method) or (None, 'first'|'fail')."""
        g = self._gray(frame)
        kp, des = self.orb.detectAndCompute(g, None)
        prev, pkp, pdes = self._prev, self._prev_kp, self._prev_des
        self._prev, self._prev_kp, self._prev_des = g, kp, des
        if prev is None:
            return None, "first"
        Hs = self._orb(pkp, pdes, kp, des)
        method = "orb"
        if Hs is None:
            Hs = self._ecc(prev, g)
            method = "ecc"
        if Hs is None:
            self.stats["fail"] += 1
            return None, "fail"
        self.stats[method] += 1
        self._last_h = Hs
        return self._S @ Hs @ self._Si, method

    def _orb(self, kp1, d1, kp2, d2) -> np.ndarray | None:
        if d1 is None or d2 is None or len(kp1) < self.min_inliers or len(kp2) < self.min_inliers:
            return None
        matches = self.bf.match(d1, d2)
        if len(matches) < self.min_inliers:
            return None
        src = np.float32([kp1[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
        dst = np.float32([kp2[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
        H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 3.0)
        if H is None or mask is None or int(mask.sum()) < self.min_inliers:
            return None
        return H

    def _ecc(self, prev: np.ndarray, cur: np.ndarray) -> np.ndarray | None:
        """ECC (homography) coarse-to-fine; initialised from the last good homography and, if
        that does not converge, from a phase-correlation translation."""
        a32, b32 = prev.astype(np.float32), cur.astype(np.float32)
        (dx, dy), _ = cv2.phaseCorrelate(a32, b32)
        for init in (self._last_h, np.array([[1, 0, dx], [0, 1, dy], [0, 0, 1.0]])):
            H = self._ecc_from(a32, b32, init)
            if H is not None:
                return H
        return None

    @staticmethod
    def _ecc_from(a32: np.ndarray, b32: np.ndarray, init: np.ndarray) -> np.ndarray | None:
        H = init.copy()
        crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 80, 1e-5)
        try:
            for scale in (0.5, 1.0):
                S = np.diag([scale, scale, 1.0])
                a = cv2.resize(a32, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
                b = cv2.resize(b32, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
                # ECC estimates W with prev(x) ≈ cur(W x), i.e. W maps prev → cur pixels.
                W = (S @ H @ np.linalg.inv(S)).astype(np.float32)
                cc, W = cv2.findTransformECC(a, b, W, cv2.MOTION_HOMOGRAPHY, crit, None, 5)
                H = np.linalg.inv(S) @ W.astype(np.float64) @ S
        except cv2.error:
            return None
        if cc < 0.5:
            return None
        return H / H[2, 2]
