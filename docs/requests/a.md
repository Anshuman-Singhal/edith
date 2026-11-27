# WS-A requests and replies

## 2026-11-26 · WS-A → WS-F · CoT fixtures
- what: CoT XML fixtures, one per row of the interfaces §7 entity table (self, sim teammate,
  own quad, machine vehicle, machine person, human MARK, SPI, NAI point, delete `t-x-d-d`,
  ping/pong), plus one inbound XML and one inbound TAK v1 mesh frame (hex or base64 text, no
  binaries). Paste them (or point at files in `companion/tests/tak/`) in `docs/requests/f.md`.
- why: `schemas/cot/` is WS-A-owned; WS-A will commit them under `schemas/cot/fixtures/`.
- blocking: nothing in D1; D5 tests can use their own copies meanwhile.

## 2026-11-26 · WS-A · D1 contract notes for every workstream
- `voice.session.start|stop.trigger` is `ptt|bt_ptt|touch|text` (was `bt`; r4 voice n1).
- `sys.hello` role adds `companion`; the companion's reply is `{role: companion, proto: [1]}`.
- `perception.detections` body is `{detections: [...]}`; UDP 5800+i stays a bare array
  (`udp.detections`).
- `Alert.bearing_deg` / `range_m` and `HudState.alert.bearing_deg|range_m|ce_m` are nullable
  (kinds with no bearing). `Execution.verb` also allows `arm`.
- Models drop optional (`?`) fields that are None when dumping; parse wire JSON with
  `envelope.parse` or `Model.model_validate_json(raw, strict=True)`.
- `edith_common` now declares pydantic, jsonschema, pymap3d and mgrs (uv.lock updated).
