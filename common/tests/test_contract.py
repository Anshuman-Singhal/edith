"""Contract tests (`./edith test contract`, PLAN §5.3 D1).

Every valid fixture passes jsonschema AND pydantic (strict JSON mode); every invalid one fails
both, except fixtures marked `_schema_only` (a rule the models don't express), which must fail
the schema. Pydantic round-trips are byte-stable and the dump is itself schema-valid.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from edith_common import envelope, schema
from edith_common.models import MESSAGE_MODELS, MODELS, model_for
from pydantic import ValidationError

pytestmark = pytest.mark.contract

FIX = Path(schema.SCHEMA_DIR).parent / "fixtures"


def _fixtures(kind: str) -> list[tuple[str, Path]]:
    return sorted((p.parent.name, p) for p in (FIX / kind).glob("*/*.json"))


VALID = _fixtures("valid")
INVALID = _fixtures("invalid")


def _id(x):
    return f"{x[0]}/{x[1].stem}" if isinstance(x, tuple) else str(x)


def test_fixture_counts():
    assert len(VALID) + len(INVALID) >= 50
    types = set(schema.types())
    have_valid = {t for t, _ in VALID}
    have_invalid = {t for t, _ in INVALID}
    assert types - have_valid == set(), "types without a valid fixture"
    assert types - have_invalid == set(), "types without an invalid fixture"
    assert (have_valid | have_invalid) <= types, "fixture dir for an unknown type"


def test_models_cover_every_schema_type():
    assert set(MODELS) == set(schema.types())


@pytest.mark.parametrize("case", VALID, ids=_id)
def test_valid_fixture_passes_schema_and_model(case):
    type_, path = case
    raw = path.read_text()
    obj = json.loads(raw)
    schema.validate(type_, obj)
    model = model_for(type_)
    m = model.model_validate_json(raw, strict=True)
    # byte-stable round trip, canonical (declaration) key order
    a = m.model_dump_json()
    b = model.model_validate_json(a, strict=True).model_dump_json()
    c = model.model_validate_json(b, strict=True).model_dump_json()
    assert a == b == c
    # the dump is itself schema-valid
    schema.validate(type_, json.loads(a))


@pytest.mark.parametrize("case", INVALID, ids=_id)
def test_invalid_fixture_fails(case):
    type_, path = case
    raw = path.read_text()
    obj = json.loads(raw)
    errs = schema.errors(type_, obj)
    assert len(errs) == 1, f"{path.name} must break exactly one schema rule, got {errs}"
    if isinstance(obj, dict) and obj.get("_schema_only"):
        return
    with pytest.raises(ValidationError):
        model_for(type_).model_validate_json(raw, strict=True)


@pytest.mark.parametrize("case", [c for c in VALID if c[0] == "envelope"], ids=_id)
def test_envelope_parse_types_body(case):
    _, path = case
    raw = path.read_text()
    obj = json.loads(raw)
    schema.validate_message(obj)
    env = envelope.parse(raw)
    if env.type in MESSAGE_MODELS:
        assert isinstance(env.body, MESSAGE_MODELS[env.type])
    else:
        assert isinstance(env.body, dict)  # forward compat: unknown types pass through
    out = env.model_dump_json()
    assert envelope.parse(out).model_dump_json() == out
    schema.validate_message(json.loads(out))


def test_message_fixture_wrapped_in_envelope_validates():
    """Every valid message body, wrapped by envelope.make, is a valid wire message."""
    for type_, path in VALID:
        if type_ not in MESSAGE_MODELS:
            continue
        body = MESSAGE_MODELS[type_].model_validate_json(path.read_text(), strict=True)
        env = envelope.make(type_, body, src="contract-test", ts_ms=1795000000000)
        schema.validate_message(json.loads(env.model_dump_json()))


def test_unknown_fields_are_ignored():
    """Additive minor changes must be ignored by older readers (interfaces §1)."""
    for type_, path in VALID:
        obj = json.loads(path.read_text())
        if not isinstance(obj, dict):
            continue
        obj["x_future_field"] = {"nested": [1, 2]}
        schema.validate(type_, obj)
        model_for(type_).model_validate_json(json.dumps(obj), strict=True)


def test_index_messages_match_spec_table():
    msgs = set(schema.index()["messages"])
    assert msgs == {
        "sys.hello", "sys.ping", "sys.pong", "head.pose", "input.event", "voice.session.start",
        "voice.session.stop", "voice.text", "voice.partial", "voice.final", "hud.state",
        "hud.event", "glasses.telemetry", "perception.detections",
    }
    assert msgs == set(MESSAGE_MODELS)
