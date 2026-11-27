"""Data-link-loss failsafe with PX4's delayed hold (C89; PX4 v1.18 ``failsafe/framework.cpp``).

Rules (sim spec §2, matching framework.cpp at v1.18.0-rc2, re-read 2026-11-26):

- The DLL failsafe triggers only while armed and in air, and only once a GCS link has been
  seen. It triggers at ``last_link_t + COM_DL_LOSS_T``.
- On trigger the vehicle holds AUTO.LOITER for the start delay (``COM_FAIL_ACT_T``), then takes
  ``NAV_DLL_ACT``. The DLL action's clear condition is ``OnModeChangeOrDisarm``: **a link that
  returns during the delay does not cancel it** (``removeAction`` keeps the action and only
  flags it; ``_current_delay`` keeps counting down), and the action, once taken, persists after
  the link returns.
- A user mode change (e.g. the safety-stop hold) is accepted during the delay and during the
  action; it is a takeover that drops the pending action. A disarm clears everything.
- The start delay refills at ``dt/4`` (capped at ``COM_FAIL_ACT_T``) while no delayed action
  is pending, so a second failsafe soon after the first gets a shorter hold (sim r4 nit 1).
- **Ordering (architect r4 nit 1):** callers evaluate ``update(t)`` with the packet's arrival
  time *before* calling ``on_link(t)`` for a recovering packet, so a deadline that has passed
  by timestamp is honoured even when the packet is processed late.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from edith_common.px4 import modes


def dll_countdown_s(silence_s: float, dl_loss_t: float, fail_act_t: float) -> float:
    """``AssetState.failsafe.dll_countdown_s`` (C89)."""
    return dl_loss_t + fail_act_t - silence_s


@dataclass
class DllFailsafe:
    dl_loss_t: float
    fail_act_t: float
    nav_dll_act: int = 2
    state: str = "idle"  # idle | hold | action
    deadline: float | None = None
    link_seen: bool = False
    last_link_t: float = 0.0
    _episode: bool = False  # this loss episode already handled (until the link returns)
    _start_delay: float = field(default=-1.0)
    _last_t: float | None = None

    def __post_init__(self) -> None:
        if self._start_delay < 0:
            self._start_delay = self.fail_act_t

    @property
    def action_mode(self) -> int | None:
        return modes.DLL_ACTION_MODE.get(self.nav_dll_act)

    def silence_s(self, t: float) -> float:
        return t - self.last_link_t if self.link_seen else 0.0

    def _refill(self, t: float) -> None:
        if self._last_t is not None and t > self._last_t:
            dt = t - self._last_t
            if self.state == "hold":
                self._start_delay = max(0.0, self._start_delay - dt)
            else:
                self._start_delay = min(self.fail_act_t, self._start_delay + dt / 4)
        self._last_t = t if self._last_t is None else max(self._last_t, t)

    def update(self, t: float, armed: bool, in_air: bool) -> list[tuple[float, int, str]]:
        """Advance to ``t``; return the mode transitions ``(t_exact, custom_mode, reason)``."""
        out: list[tuple[float, int, str]] = []
        if not armed:
            self.state, self.deadline = "idle", None
        if (self.state == "idle" and armed and in_air and self.link_seen
                and not self._episode and self.nav_dll_act != 0
                and t - self.last_link_t >= self.dl_loss_t):
            t_trig = self.last_link_t + self.dl_loss_t
            self._refill(t_trig)
            self._episode = True
            delay = self._start_delay if self.action_mode != modes.AUTO_LOITER else 0.0
            if delay > 0:
                self.state, self.deadline = "hold", t_trig + delay
                out.append((t_trig, modes.AUTO_LOITER, "dll_hold"))
            else:
                self.state, self.deadline = "hold", t_trig
        if self.state == "hold" and self.deadline is not None and t >= self.deadline:
            self._refill(self.deadline)
            self.state = "action"
            if self.action_mode is not None:
                out.append((self.deadline, self.action_mode, "dll_action"))
            self.deadline = None
        self._refill(t)
        return out

    def on_link(self, t: float) -> None:
        """A GCS heartbeat arrived at ``t`` (call ``update(t)`` first)."""
        self.link_seen = True
        self.last_link_t = max(self.last_link_t, t)
        self._episode = False  # the pending/active action is kept (OnModeChangeOrDisarm)

    def on_mode_change(self) -> None:
        """User takeover: drop the pending or active action."""
        self.state, self.deadline = "idle", None

    def on_disarm(self) -> None:
        self.state, self.deadline = "idle", None
