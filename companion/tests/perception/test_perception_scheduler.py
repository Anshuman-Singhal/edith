"""D8 scheduler (C58): 2 Hz default, 4 Hz tasked, 1 Hz idle after 30 s with no tracks, 4 Hz for
5 s after an unconfirmed detection, 1 Hz cap on all feeds while PTT is down."""

from edith_companion.perception.scheduler import Scheduler


def runs(s, feed, t0, t1, step=50):
    return sum(s.due(feed, t) for t in range(t0, t1, step))


def test_rates():
    s = Scheduler()
    s.note_result("D1", 0, n_tracks=1, n_unconfirmed_dets=0)
    assert s.rate_hz("D1", 0) == 2.0
    assert runs(s, "D1", 0, 10_000) == 20
    s.note_result("D1", 10_000, 0, 1)                    # unconfirmed detection → boost
    assert s.rate_hz("D1", 10_000) == 4.0 and s.rate_hz("D1", 14_999) == 4.0
    assert s.rate_hz("D1", 15_000) == 2.0
    assert runs(s, "D1", 10_000, 15_000) == 20
    s.set_ptt(True)                                      # PTT cap wins over the boost
    s.note_result("D1", 15_000, 0, 1)
    s.note_result("D2", 15_000, 0, 1)
    assert s.rate_hz("D1", 16_000) == 1.0 and s.rate_hz("D2", 16_000) == 1.0
    assert runs(s, "D2", 15_000, 20_000) == 5
    s.set_ptt(False)
    s.set_tasked("D3", True, 0)
    assert s.rate_hz("D3", 100_000) == 4.0
    assert s.rate_hz("D1", 15_000 + 30_000) == 1.0       # idle: 30 s with no tracks
