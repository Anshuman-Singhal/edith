# Third-party licenses (WS-A)

Phase 0 is a prototype; nothing here is distributed outside the team. This file still tracks
every dependency so the Phase 1 product can ship cleanly. Versions are the ones `uv.lock`
resolved on 2026-11-26 (Python 3.13, linux x86_64). Rule: no GPL code linked into anything we
ship (`piper-tts` is banned, C107); NC/research-only data and weights are `ship: false` in their
lockfiles and lint-checked (`tests/lint/test_nc_artifacts.py`).

## Python (uv workspace)

| Package | Version | License | Where used | Note |
|---|---|---|---|---|
| numpy | 2.5.3 | BSD-3-Clause (+0BSD, MIT, Zlib, CC0 parts) | everywhere | |
| onnxruntime | 1.29.0 | MIT | ml, perception | |
| opencv-python-headless | 5.0.0.93 | Apache-2.0 | sim, ml | |
| pydantic | 2.13.5 | MIT | common models | |
| jsonschema | 4.26.0 | MIT | contract tests | |
| aiohttp | 3.14.5 | Apache-2.0 AND MIT | gateway, selftest peer | |
| lark | 1.3.1 | MIT | intent grammar | |
| pymavlink | 2.4.50 | LGPL-3.0 | asset adapter, Mock | Dynamic use only; unmodified |
| pymap3d | 3.2.0 | BSD-2-Clause | geo | |
| mgrs | 1.7.1 | MIT | geo | |
| av (PyAV) | 19.0.2 | BSD-3-Clause; bundled FFmpeg reports "LGPL version 3 or later" | sim video (RTP H.264) | The bundled FFmpeg `configuration` lists `--enable-libx264 --enable-libx265` (GPL libraries) while reporting LGPLv3; GPL status **UNVERIFIED**. Encoding stays in `sim/` and is never shipped (C84). Record: `av._core.library_meta['libavcodec']` |
| pillow | 13.0.0 | MIT-CMU | text-fit tests, sprites | |
| fonttools | 4.69.1 | MIT | B612 cmap checks | |
| pyyaml | 6.0.4 | MIT | scenarios, lockfiles | |
| psutil | 7.2.2 | BSD-3-Clause | supervisor CPU sampling | |
| moonshine-voice (extra `voice`) | 0.1.6 | MIT | ASR | Model weights pinned in `voice/models.lock.yaml` |
| sherpa-onnx (extra `voice`) | 2.0.3 | Apache-2.0 | ASR alt, TTS (P2) | |
| vosk (extra `voice`) | 0.3.45 | Apache-2.0 | decoy grammar | |
| kokoro-onnx (extra `voice`) | 0.6.1 | MIT (package; UNVERIFIED from metadata) | TTS for test corpora only | Kokoro-82M weights Apache-2.0 (UNVERIFIED), hashed in `voice/models.lock.yaml` |
| pytak (extra `tak`) | 7.6.1 | Apache-2.0 | TAK transports | |
| takproto (extra `tak`) | 3.0.1 | MIT | TAK protobuf | |
| pytest | 9.1.1 | MIT | dev | |
| hypothesis | 6.170.x | MPL-2.0 | dev | |

## Android / Kotlin (see `glasses/gradle/libs.versions.toml`)

| Component | License | Note |
|---|---|---|
| AGP 8.13.2, AndroidX, Compose Multiplatform 1.9.3 | Apache-2.0 | |
| Kotlin 2.2.21, kotlinx.serialization 1.9.0, coroutines 1.10.2, Ktor 3.3.3 | Apache-2.0 | |
| OkHttp 4.12 (`:selftest` only) | Apache-2.0 | |
| Robolectric 4.16.1 | MIT | test only |
| RayNeo MercuryAndroidSDK 0.2.6 | **No license file** | Fetched by `tools/fetch_rayneo_sdk.sh`, never committed (L13). Phase 1 moves to trusted hardware |
| B612 1.008 font | OFL-1.1 | Bundled TTF (allowlisted) |

## Data and models (fetched, never committed)

| Artifact | License | Ship? |
|---|---|---|
| YOLOX nano/tiny/s weights | Apache-2.0 | yes |
| D-FINE-N, RT-DETRv2-R18 | Apache-2.0 | yes |
| VisDrone | CC BY-NC-SA 3.0 | **no** (eval/research only) |
| UAVDT | research-only | **no** |
| Okutama-Action | no stated license | **no** |
| NAIP imagery | US public domain | yes |
| Noise corpora | per row in `bench/noise.lock.yaml` | per row |

## Tools

| Tool | License | Note |
|---|---|---|
| PX4 SIH 1.18 | BSD-3-Clause | Approval-gated in this workspace (L14) |
| OpenTAKServer | GPL-3.0 | Optional, separate process, never linked |
