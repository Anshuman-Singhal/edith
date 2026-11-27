"""schemas/v1 hygiene: every schema is valid JSON Schema 2020-12, has the right $id, is listed in
index.json, and every $ref resolves. Every fixture is parseable JSON."""

import json

from _repo import ROOT
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

V1 = ROOT / "schemas" / "v1"
FIX = ROOT / "schemas" / "fixtures"


def _schemas():
    return {p.name: json.loads(p.read_text()) for p in sorted(V1.glob("*.schema.json"))}


def test_schemas_are_valid_2020_12():
    for name, s in _schemas().items():
        assert s["$schema"] == "https://json-schema.org/draft/2020-12/schema", name
        assert s["$id"].endswith("/v1/" + name), name
        Draft202012Validator.check_schema(s)


def test_index_lists_every_schema_and_only_existing_files():
    idx = json.loads((V1 / "index.json").read_text())
    listed = set(idx["types"].values()) | {idx["shared"]}
    on_disk = set(_schemas())
    assert listed == on_disk
    for m, meta in idx["messages"].items():
        assert idx["types"][m] == meta["schema"]
        assert meta["dir"] in {"up", "down", "both"}


def test_refs_resolve():
    schemas = _schemas()
    reg = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in schemas.values())

    def refs(node):
        if isinstance(node, dict):
            if "$ref" in node:
                yield node["$ref"]
            for v in node.values():
                yield from refs(v)
        elif isinstance(node, list):
            for v in node:
                yield from refs(v)

    for s in schemas.values():
        resolver = reg.resolver(base_uri=s["$id"])
        for r in refs(s):
            resolver.lookup(r)


def test_fixtures_are_json():
    files = list(FIX.glob("*/*/*.json"))
    assert files
    for p in files:
        json.loads(p.read_text())
