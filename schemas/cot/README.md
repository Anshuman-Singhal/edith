# CoT fixtures (placeholder)

CoT is XML (TAK Protocol v0) out and XML + TAK Protocol v1 protobuf in, so it has no JSON Schema
here. The normative table (types, `how`, rates, stale, uids, retraction, scope guard) is
[interfaces §7](../../docs/spec/interfaces.md#7-cot-tak-protocol-v0-xml-out-v0-xml--v1-protobuf-in).

WS-F (TAK) authors the fixtures — one per row of the §7 entity table, plus one inbound XML and one
inbound v1 mesh frame — and hands them over through `docs/requests/f.md`. `schemas/**` is
WS-A-owned, so WS-A commits them under `schemas/cot/fixtures/` on the next contracts pass.
Every sim-sourced fixture's `remarks` starts with `EXERCISE` (C55).
