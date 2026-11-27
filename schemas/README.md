# Wire schemas (source of truth, C27)

- `v1/*.schema.json` — JSON Schema 2020-12 for the envelope, binary frame header, every
  WebSocket message body ([interfaces §3](../docs/spec/interfaces.md#3-websocket-messages-7400-v1ws))
  and every core schema (§4). `v1/defs.schema.json` holds shared `$defs`; `v1/index.json` maps
  type name → schema file (and message direction).
- `fixtures/valid|invalid/<type>/*.json` — shared contract fixtures for Python (pydantic,
  `./edith test contract`) and Kotlin (`./edith glasses test`). Invalid fixtures break exactly
  one rule, named in `_why`; `_schema_only: true` marks a rule only the schema enforces
  (an optional field sent as explicit `null`). Regenerate with
  `uv run python schemas/fixtures/generate.py`.
- `cot/` — CoT fixtures (WS-F, via request).

Python: `edith_common.schema.validate(type, obj)`, models in `edith_common.models`.
Only WS-A edits this tree; ask in `docs/requests/<ws>.md`.
