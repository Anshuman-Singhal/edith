# Selftest peer protocol v1 (`./edith glasses selftest --serve`)

Owner: WS-G. The host peer for T9, T11 and T13 (C104). Pure Python + aiohttp in
`tools/edith_tools/commands/g.py`; no companion dependency. Default port **7400** (`--port`,
`--port 0` picks a free one). Do not run the companion at the same time on the same port.

## Auth and URLs

Every request carries `?token=<t>` (or `Authorization: Bearer <t>`). The peer prints a random
token at start (`--token none` disables it on a trusted LAN). The APK gets both from the
provisioning extras: `--es peer ws://<ip>:7400/v1/selftest --es token <t>`.

| Endpoint | Use |
|---|---|
| `GET /healthz` | `{ok, run_dir}` |
| `GET /v1/selftest?test=t9\|t11\|t13&token=` | WebSocket, one per test run |
| `GET /v1/selftest/t11/down?bytes=N&token=` | T11 download: N bytes (≤512 MiB) |
| `POST /v1/selftest/t11/up?token=` | T11 upload: returns `{dir, bytes, secs, mbit_s_peer}` |

On open the peer sends `{"type":"hello","test":..., "peer_version":1, "run_dir":...}`.
Text frames are JSON with a `type`; unknown types get `{"type":"error"}`. `{"type":"bye"}` closes.

## T9 (mic → WAV)

```
C→P {"type":"t9.start","segment":"src_MIC","source":"MIC","rate":16000,"channels":1}
C→P binary: PCM s16le interleaved, any chunking (the APK sends 20 ms)
C→P {"type":"t9.end","segment":"src_MIC","samples":160000}
P→C {"type":"t9.saved","segment":"src_MIC","path":"runs/bringup/<ts>/t9_src_MIC.wav","samples":160000,"rms_dbfs":-31.2}
```

One WAV per segment in `runs/bringup/<ts>/`, plus a line per segment in `t9.jsonl`.

## T13 (inset JPEG → echo)

```
C→P {"type":"t13.start","fps":15,"width":320,"height":240,"seconds":60}
P→C binary: [0x0D][frame_id: u32 big-endian][JPEG bytes]      (paced at fps)
C→P {"type":"t13.echo","frame_id":17,"recv_to_decoded_ms":4.2,"ok":true}   (after decoding)
P→C {"type":"t13.result","sent":900,"echoed":899,"dropped":1,"drop_pct":0.11,
     "rtt_ms_p50":..,"rtt_ms_p95":..,"decode_ms_p95":..,"latency_ms_p95":..,"pass":true,...}
```

Latency is defined in [TESTS.md](TESTS.md#definitions-normative-r4-platform-nits). The peer
writes per-frame RTT and decode times to `t13.jsonl`.

## T11 (Wi-Fi)

HTTP down/up as above (the client times the transfer), and on the WebSocket:
`C→P {"type":"t11.ping","seq":n}` / `P→C {"type":"t11.pong","seq":n}` for RTT.
