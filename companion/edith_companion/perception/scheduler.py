"""Detector rate policy (PLAN §3.5 Scheduler, C58).

Per feed: 2 Hz default; 4 Hz while tasked; 1 Hz after 30 s with no tracks; 4 Hz for 5 s after
any unconfirmed detection; capped at 1 Hz on all feeds while PTT is down (the cap wins).
"""

from __future__ import annotations

from dataclasses import dataclass

BASE_HZ, TASKED_HZ, IDLE_HZ, BOOST_HZ, PTT_CAP_HZ = 2.0, 4.0, 1.0, 4.0, 1.0
BOOST_MS, IDLE_AFTER_MS = 5000, 30_000


@dataclass
class _Feed:
    tasked: bool = False
    boost_until_ms: int = -1
    last_track_ms: int | None = None
    created_ms: int | None = None
    last_run_ms: int | None = None


class Scheduler:
    def __init__(self) -> None:
        self.feeds: dict[str, _Feed] = {}
        self.ptt_down = False

    def _f(self, feed: str, now_ms: int) -> _Feed:
        f = self.feeds.setdefault(feed, _Feed())
        if f.created_ms is None:
            f.created_ms = now_ms
        return f

    def set_ptt(self, down: bool) -> None:
        self.ptt_down = down

    def set_tasked(self, feed: str, tasked: bool, now_ms: int = 0) -> None:
        self._f(feed, now_ms).tasked = tasked

    def rate_hz(self, feed: str, now_ms: int) -> float:
        f = self._f(feed, now_ms)
        if now_ms < f.boost_until_ms:
            hz = BOOST_HZ
        elif f.tasked:
            hz = TASKED_HZ
        else:
            ref = f.last_track_ms if f.last_track_ms is not None else f.created_ms
            hz = IDLE_HZ if now_ms - ref >= IDLE_AFTER_MS else BASE_HZ
        return min(hz, PTT_CAP_HZ) if self.ptt_down else hz

    def due(self, feed: str, now_ms: int) -> bool:
        """True if a frame arriving now should be processed (and records the run)."""
        f = self._f(feed, now_ms)
        period = 1000.0 / self.rate_hz(feed, now_ms)
        if f.last_run_ms is not None and now_ms - f.last_run_ms < period - 1.0:
            return False
        f.last_run_ms = now_ms
        return True

    def note_result(self, feed: str, now_ms: int, n_tracks: int, n_unconfirmed_dets: int) -> None:
        f = self._f(feed, now_ms)
        if n_tracks:
            f.last_track_ms = now_ms
        if n_unconfirmed_dets:
            f.boost_until_ms = now_ms + BOOST_MS
