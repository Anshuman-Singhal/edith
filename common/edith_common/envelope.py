"""Envelope helpers (interfaces §2).

    env = make("head.pose", HeadPose(...), src="glasses-01")       # seq auto per src
    raw = env.model_dump_json()
    env = parse(raw)            # env.body is the typed model for known types, else a dict
"""

from __future__ import annotations

import itertools
import json
import threading
import uuid
from typing import Any

from pydantic import BaseModel

from edith_common.clock import ScaledClock
from edith_common.models import MESSAGE_MODELS, Envelope

__all__ = ["SeqCounter", "make", "parse", "dumps", "UnknownVersion"]


class UnknownVersion(ValueError):
    pass


class SeqCounter:
    """Monotonic per-sender sequence numbers (thread-safe)."""

    def __init__(self, start: int = 0):
        self._it = itertools.count(start)
        self._lock = threading.Lock()

    def next(self) -> int:
        with self._lock:
            return next(self._it)

    __call__ = next


_counters: dict[str, SeqCounter] = {}
_counters_lock = threading.Lock()
_default_clock: ScaledClock | None = None


def _seq_for(src: str) -> int:
    with _counters_lock:
        c = _counters.setdefault(src, SeqCounter())
    return c.next()


def _clock() -> ScaledClock:
    global _default_clock
    if _default_clock is None:
        _default_clock = ScaledClock.from_env()
    return _default_clock


def make(type: str, body: BaseModel | dict, src: str, seq: int | None = None, *,
         ts_ms: int | None = None, clock: ScaledClock | None = None,
         id: str | None = None) -> Envelope:
    """Build an Envelope. `seq` defaults to a per-`src` counter; `ts_ms` to ScaledClock now.
    A dict body for a known type is validated into its model."""
    model = MESSAGE_MODELS.get(type)
    if isinstance(body, dict) and model is not None:
        body = model.model_validate(body)
    elif model is not None and not isinstance(body, model):
        raise TypeError(f"body for {type} must be {model.__name__}, got {type_name(body)}")
    return Envelope(
        v=1, type=type, id=id or str(uuid.uuid4()),
        ts_ms=(clock or _clock()).now_ms() if ts_ms is None else ts_ms,
        src=src, seq=_seq_for(src) if seq is None else seq, body=body,
    )


def type_name(x: Any) -> str:
    return x.__class__.__name__


def parse(raw: str | bytes | dict, *, strict: bool = True) -> Envelope:
    """Parse wire JSON into an Envelope; known bodies become their typed model.
    Raises pydantic.ValidationError on invalid input and UnknownVersion if v != 1."""
    obj = json.loads(raw) if isinstance(raw, str | bytes | bytearray) else raw
    if isinstance(obj, dict) and obj.get("v") != 1:
        raise UnknownVersion(f"unsupported envelope version {obj.get('v')!r}")
    env = Envelope.model_validate(obj, strict=strict)
    model = MESSAGE_MODELS.get(env.type)
    if model is not None and isinstance(env.body, dict):
        env.body = model.model_validate_json(json.dumps(env.body), strict=strict)
    return env


def dumps(env: Envelope) -> str:
    return env.model_dump_json()
