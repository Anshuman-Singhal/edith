"""Binary WS frames (interfaces §2): `[u32 BE header_len][UTF-8 JSON header][payload]`."""

from __future__ import annotations

import json
import struct

from pydantic import BaseModel

from edith_common.models import BinaryHeader

__all__ = ["pack", "unpack", "unpack_header", "MAX_HEADER"]

_LEN = struct.Struct(">I")
MAX_HEADER = 64 * 1024


def pack(header: dict | BaseModel, payload: bytes = b"", *, validate: bool = True) -> bytes:
    if isinstance(header, BaseModel):
        hdr = header.model_dump_json().encode()
    else:
        if validate:
            BinaryHeader.model_validate(header)
        hdr = json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode()
    if len(hdr) > MAX_HEADER:
        raise ValueError("binary header too large")
    return _LEN.pack(len(hdr)) + hdr + bytes(payload)


def unpack(buf: bytes | bytearray | memoryview, *, validate: bool = True) -> tuple[dict, bytes]:
    """-> (header dict, payload bytes). Raises ValueError on a malformed frame."""
    mv = memoryview(buf)
    if len(mv) < 4:
        raise ValueError("frame shorter than its length prefix")
    (n,) = _LEN.unpack_from(mv, 0)
    if n > MAX_HEADER or 4 + n > len(mv):
        raise ValueError(f"bad header length {n} for a {len(mv)}-byte frame")
    header = json.loads(bytes(mv[4:4 + n]).decode("utf-8"))
    if not isinstance(header, dict):
        raise ValueError("binary header must be a JSON object")
    if validate:
        BinaryHeader.model_validate(header, strict=True)
    return header, bytes(mv[4 + n:])


def unpack_header(buf: bytes | bytearray | memoryview) -> tuple[BinaryHeader, bytes]:
    h, p = unpack(buf, validate=False)
    return BinaryHeader.model_validate(h, strict=True), p
