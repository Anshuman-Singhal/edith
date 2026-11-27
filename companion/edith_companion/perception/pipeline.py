"""Perception orchestrator: detections + FrameMeta → tracks (PLAN §1.4 loop 2, §3.5).

``Perception.process(asset_id, meta, detections, frame=None)`` runs one detector tick of one
feed (callers gate it with ``Perception.scheduler.due``). ``PerceptionService`` wires the UDP
inputs (OffloadDetector on 5800+i, FrameSource on 5600+i/5700+i) for the companion runtime.

Outputs are interfaces §4 ``Track`` dicts. Machine tracks are always
``affiliation: unknown, affiliation_src: machine`` (I6); ``assoc_friend_uid`` set ⇒ the track
is neither alert- nor CoT-eligible (C52).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

import cv2
import numpy as np
from edith_common.geo import Origin

from .friendly import FriendlyAssociator, Pli
from .fusion import FusedTrack, Fusion
from .geo import (
    GeoNoise,
    ce90_from_cov,
    enu_to_latlon,
    in_frame,
    intrinsics_from_meta,
    latlon_to_enu,
    locate,
    pose_from_meta,
)
from .motion import MotionEstimator
from .novelty import Novelty
from .scheduler import Scheduler
from .tracker import KTrack, Meas, Tracker, TrackerParams, pixel_sigma

ALERT_CLASSES = ("person", "vehicle")
PSEUDO_SIZE = (1280, 720)
MIN_R_M2 = 0.25


@dataclass
class FeedConfig:
    asset_id: str
    geo_quality: str = "metric"         # metric | pseudo (replay, C95)
    instance: int = 0


@dataclass
class _Feed:
    cfg: FeedConfig
    tracker: Tracker
    motion: MotionEstimator | None = None
    seen_lost: int = 0
    pseudo_novelty: dict[int, float] = field(default_factory=dict)


class Perception:
    def __init__(self, origin: Origin, companion_id: str = "companion-01",
                 noise: GeoNoise | None = None):
        self.origin = origin
        self.companion_id = companion_id
        self.noise = noise or GeoNoise()
        self.feeds: dict[str, _Feed] = {}
        self.fusion = Fusion()
        self.friendly = FriendlyAssociator()
        self.novelty = Novelty()
        self.scheduler = Scheduler()
        self._pub: dict[tuple, int] = {}
        self._next_pub = 1
        self._alias: dict[int, int] = {}
        self._next_alias = 1
        self._nov: dict[int, float] = {}
        self._assoc: dict[int, str | None] = {}
        self._out: dict[int, dict] = {}

    # ---------------------------------------------------------------- config / inputs
    def add_feed(self, cfg: FeedConfig) -> None:
        params = TrackerParams.image() if cfg.geo_quality == "pseudo" else TrackerParams()
        self.feeds[cfg.asset_id] = _Feed(cfg, Tracker(params),
                                         MotionEstimator(PSEUDO_SIZE)
                                         if cfg.geo_quality == "pseudo" else None)

    def on_teammate(self, tp: dict, is_self: bool = False) -> None:
        """``TeammatePosition`` dict (interfaces §4) → friendly PLI."""
        e, n = latlon_to_enu(tp["pos"]["lat"], tp["pos"]["lon"], self.origin)
        self.friendly.on_pli(Pli(tp["uid"], e, n, float(tp.get("course_deg") or 0.0),
                                 float(tp.get("speed_mps") or 0.0), int(tp["ts_ms"]), is_self))

    def on_tak_status(self, state: str, t_ms: int) -> None:
        self.friendly.on_tak_status(state, t_ms)

    def on_ptt(self, down: bool) -> None:
        self.scheduler.set_ptt(down)

    def splice(self, asset_id: str) -> None:
        f = self.feeds[asset_id]
        f.tracker.reset()
        if f.motion:
            f.motion.reset()

    # ---------------------------------------------------------------- processing
    def _pid(self, key: tuple) -> int:
        if key not in self._pub:
            self._pub[key] = self._next_pub
            self._next_pub += 1
        return self._pub[key]

    def process(self, asset_id: str, meta: dict, dets: Iterable[dict],
                frame: np.ndarray | None = None, t_ms: int | None = None) -> list[dict]:
        feed = self.feeds.get(asset_id) or self._auto_feed(asset_id)
        t = int(t_ms if t_ms is not None else meta.get("t_capture_ms") or meta["t_sim_ms"])
        dets = list(dets)
        if feed.cfg.geo_quality == "pseudo":
            out = self._process_pseudo(feed, meta, dets, frame, t)
        else:
            out = self._process_metric(feed, meta, dets, t)
        unconf = sum(1 for k in feed.tracker.tracks if not k.confirmed and k.last_ms == t)
        self.scheduler.note_result(asset_id, t, len(feed.tracker.tracks), unconf)
        return out

    def _auto_feed(self, asset_id: str) -> _Feed:
        self.add_feed(FeedConfig(asset_id))
        return self.feeds[asset_id]

    def _process_metric(self, feed: _Feed, meta: dict, dets: list[dict], t: int) -> list[dict]:
        pose = pose_from_meta(meta, self.origin)
        K = intrinsics_from_meta(meta)
        meas = []
        for d in dets:
            x, y, w, h = d["bbox_norm"]
            u, v = (x + w / 2) * K.w, (y + h) * K.h
            fix = locate(pose, K, u, v, h * K.h, self.noise)
            if fix is None:
                continue
            meas.append(Meas(d["det_id"], d["cls"], float(d["conf"]), np.array([fix.e, fix.n]),
                             fix.cov + np.eye(2) * MIN_R_M2, t, tuple(d["bbox_norm"])))
        tr = feed.tracker
        tr.step(t, meas, visible=lambda p: in_frame(pose, K, float(p[0]), float(p[1])))
        new_lost = tr.lost[feed.seen_lost:]
        feed.seen_lost = len(tr.lost)
        self.fusion.update(feed.cfg.asset_id, tr.tracks, new_lost, t)
        out = []
        for ft in self.fusion.tracks.values():
            pid = self._pid(("f", ft.track_id))
            if ft.lost:
                if pid in self._out and self._out[pid]["status"] != "lost":
                    self.friendly.on_track_lost(pid)
                    self._out[pid]["status"] = "lost"
                    out.append(self._out[pid])
                continue
            if feed.cfg.asset_id not in ft.members:
                continue
            out.append(self._emit_fused(pid, ft, t))
        return out

    def _emit_fused(self, pid: int, ft: FusedTrack, t: int) -> dict:
        e, n = float(ft.x[0]), float(ft.x[1])
        ce = ft.ce_m
        assoc = self.friendly.evaluate(pid, ft.cls, e, n, ce, t)
        if ft.confirmed:
            if pid not in self._nov:
                self._nov[pid] = self.novelty.score(pid, ft.cls, e, n, ce, t)
                self._alias[pid] = self._next_alias
                self._next_alias += 1
            self.novelty.observe(pid, ft.cls, e, n, t)
        lat, lon = enu_to_latlon(e, n, self.origin)
        d = self._track_dict(pid, ft.cls, ft.conf, ft.hits, lat, lon, ce,
                             (float(ft.x[2]), float(ft.x[3])), "metric", ft.first_seen_ms,
                             ft.last_seen_ms, list(ft.source_assets), ft.confirmed,
                             self._nov.get(pid, 1.0), assoc, ft.det_ids)
        d["_enu"] = (e, n)
        d["_confirmed_ms"] = ft.confirmed_ms
        self._out[pid] = d
        return d

    def _process_pseudo(self, feed: _Feed, meta: dict, dets: list[dict],
                        frame: np.ndarray | None, t: int) -> list[dict]:
        W, H = PSEUDO_SIZE
        Hm = None
        if frame is not None and feed.motion is not None:
            img = frame if frame.shape[1::-1] == PSEUDO_SIZE else cv2.resize(frame, PSEUDO_SIZE)
            Hm, method = feed.motion.update(img)
            if method == "fail":
                feed.tracker.reset()
        meas = []
        for d in dets:
            x, y, w, h = d["bbox_norm"]
            s = pixel_sigma(w * W, h * H)
            meas.append(Meas(d["det_id"], d["cls"], float(d["conf"]),
                             np.array([(x + w / 2) * W, (y + h) * H]), np.eye(2) * s * s, t,
                             tuple(d["bbox_norm"])))
        tr = feed.tracker
        tr.step(t, meas, visible=lambda p: 0 <= p[0] <= W and 0 <= p[1] <= H, warp=Hm)
        out = []
        for k in tr.lost[feed.seen_lost:]:
            pid = self._pid(("p", feed.cfg.asset_id, k.id))
            if pid in self._out:
                self._out[pid]["status"] = "lost"
                out.append(self._out[pid])
        feed.seen_lost = len(tr.lost)
        pose = K = None
        try:
            pose, K = pose_from_meta(meta, self.origin), intrinsics_from_meta(meta)
        except (KeyError, TypeError):
            pass
        for k in tr.tracks:
            out.append(self._emit_pseudo(feed, k, pose, K, t))
        return out

    def _emit_pseudo(self, feed: _Feed, k: KTrack, pose, K, t: int) -> dict:
        pid = self._pid(("p", feed.cfg.asset_id, k.id))
        lat = lon = None
        ce = 0.0
        if pose is not None:
            fix = locate(pose, K.scaled(*PSEUDO_SIZE) if (K.w, K.h) != PSEUDO_SIZE else K,
                         float(k.x[0]), float(k.x[1]), noise=self.noise)
            if fix is not None:
                lat, lon = enu_to_latlon(fix.e, fix.n, self.origin)
                ce = fix.ce_m
        if k.confirmed and pid not in self._alias:
            self._alias[pid] = self._next_alias
            self._next_alias += 1
        d = self._track_dict(pid, k.cls, k.conf, k.hits, lat, lon, ce,
                             (float(k.x[2]), float(k.x[3])), "pseudo", k.first_ms, k.last_ms,
                             [feed.cfg.asset_id], k.confirmed, 1.0, None, k.det_ids)
        d["_px"] = (float(k.x[0]), float(k.x[1]))
        d["_confirmed_ms"] = k.confirmed_ms
        self._out[pid] = d
        return d

    def _track_dict(self, pid, cls, conf, hits, lat, lon, ce, vel, quality, first, last,
                    assets, confirmed, novelty, assoc, det_ids) -> dict:
        alias = self._alias.get(pid)
        if lat is None:                       # pseudo track with no usable pose: origin
            lat, lon = self.origin.lat, self.origin.lon
        d = {
            "track_id": str(pid),
            "alias": f"contact {alias}" if alias else f"tentative {pid}",
            "cls": cls, "conf": round(min(max(float(conf), 0.0), 1.0), 4), "hits": int(hits),
            "window": 5,
            "geo": {"lat": float(lat), "lon": float(lon), "ce_m": round(float(ce), 2)},
            "vel": {"e_mps": vel[0], "n_mps": vel[1]},   # px/s for pseudo tracks
            "geo_quality": quality,
            "first_seen_ms": int(first), "last_seen_ms": int(last),
            "source_assets": assets,
            "status": "confirmed" if confirmed else "new",
            "novelty": novelty,
            "affiliation": "unknown", "affiliation_src": "machine",
            "cot_uid": f"EDITH-{self.companion_id}-trk-{pid}",
            "det_ids": [str(x) for x in list(det_ids)[-8:]],
        }
        if assoc is not None:
            d["assoc_friend_uid"] = assoc
        return d

    # ---------------------------------------------------------------- views
    def tracks(self, include_lost: bool = False) -> list[dict]:
        return [d for d in self._out.values() if include_lost or d["status"] != "lost"]


def to_wire(track: dict) -> dict:
    """Schema-valid ``Track`` (interfaces §4) without the private ``_*`` debug keys."""
    return {k: v for k, v in track.items() if not k.startswith("_")}


def alert_eligible(track: dict) -> bool:
    """Perception-side gate for the alert ranker (C52, I6)."""
    return (track["status"] == "confirmed" and track.get("assoc_friend_uid") is None
            and track["cls"] in ALERT_CLASSES and track["affiliation"] == "unknown")


def cot_eligible(track: dict) -> bool:
    """Perception-side gate for CoT publication (C52): metric, confirmed, not friend-associated."""
    return alert_eligible(track) and track["geo_quality"] == "metric"


def track_ce90(P: np.ndarray) -> float:
    return ce90_from_cov(P[:2, :2])
