"""Load and validate against the v1 JSON Schemas (`schemas/v1/`, the source of truth, C27).

    from edith_common import schema
    schema.validate("head.pose", body)          # raises jsonschema.ValidationError
    schema.is_valid("Track", obj)
    schema.validate_message(envelope_dict)      # envelope + body by its `type`
"""

from __future__ import annotations

import json
import os
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError
from jsonschema.exceptions import best_match
from referencing import Registry, Resource

__all__ = ["SCHEMA_DIR", "ValidationError", "errors", "index", "is_valid", "load", "types",
           "validate", "validate_message", "validator"]


def _schema_dir() -> Path:
    env = os.environ.get("EDITH_SCHEMA_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "schemas" / "v1"


SCHEMA_DIR = _schema_dir()


@cache
def index() -> dict:
    return json.loads((SCHEMA_DIR / "index.json").read_text())


def types() -> list[str]:
    return list(index()["types"])


@cache
def _registry() -> Registry:
    resources = []
    for p in sorted(SCHEMA_DIR.glob("*.schema.json")):
        doc = json.loads(p.read_text())
        resources.append((doc["$id"], Resource.from_contents(doc)))
    return Registry().with_resources(resources)


@cache
def load(type_: str) -> dict:
    try:
        fname = index()["types"][type_]
    except KeyError:
        raise KeyError(f"no schema for type {type_!r}") from None
    return json.loads((SCHEMA_DIR / fname).read_text())


@cache
def validator(type_: str) -> Draft202012Validator:
    return Draft202012Validator(load(type_), registry=_registry(),
                                format_checker=Draft202012Validator.FORMAT_CHECKER)


def validate(type_: str, obj: Any) -> None:
    """Raise jsonschema.ValidationError (best match) if `obj` is not a valid `type_`."""
    err = best_match(validator(type_).iter_errors(obj))
    if err is not None:
        raise err


def errors(type_: str, obj: Any) -> list[str]:
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
            for e in validator(type_).iter_errors(obj)]


def is_valid(type_: str, obj: Any) -> bool:
    return validator(type_).is_valid(obj)


def validate_message(env: Any, *, allow_unknown_type: bool = True) -> None:
    """Validate an envelope dict and, when its type is known, its body."""
    validate("envelope", env)
    t = env["type"]
    if t in index()["messages"]:
        validate(t, env["body"])
    elif not allow_unknown_type:
        raise ValidationError(f"unknown message type {t!r}")
