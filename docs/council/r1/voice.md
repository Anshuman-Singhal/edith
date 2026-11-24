# R1 · Voice & NLP — noisy speech → confirmed ISR tasking

Owner: Om (Voice & NLP). Scope is goal 1: one operator directs a drone by voice from the glasses. Verbs map onto the architect's structural allowlist (`takeoff, goto, orbit, observe, search, follow, hold, rtl, land`). This proposal adds no verbs.

## 1. Recommendations

### 1.1 Activation: push-to-talk only in Phase 0
- **Hold-to-talk on the temple touchpad.** The ring and the companion's button are alternates. Audio streams only between `voice.session.start/stop`, plus a 150 ms tail after release. With no open mic, radio chatter cannot start a command, and the demo gets a clean end-of-speech signal. Whether RayNeo delivers temple gestures to a glasses-native app is **UNVERIFIED** (week-1 test B1).
- **Wake word: not in Phase 0, and never enough to execute anything.**
  - **Porcupine is out.** Picovoice ended its Free Tier on 30 Jun 2026, and the SDK will not start without a valid AccessKey ([HA thread](https://community.home-assistant.io/t/fyi-picovoice-confirmed-free-tier-accesskeys-will-stop-working-after-june-30-2026/1012744)).
  - **openWakeWord** code is Apache-2.0, but its pretrained models are **CC BY-NC-SA 4.0**. Its target is <0.5 false accepts/hour, and it can be trained on synthetic TTS ([README](https://raw.githubusercontent.com/dscripka/openWakeWord/HEAD/README.md)).
  - **sherpa-onnx open-vocabulary KWS** (3.3M params, per-keyword boost and threshold, no training, Android APKs; [docs](https://k2-fsa.github.io/sherpa/onnx/kws/index.html)) is the semester-2 stretch path for hands-free use. It would only replace the press.

### 1.2 Audio capture and transport (glasses)
- **RayNeo mode.** The X3 doc lists a `VOICE_RECOGNITION` recording mode: three mics, "wearer's voice only", mono, typically 16 kHz. It is selected with `AudioManager.setParameters("audio_source_record=…")` and released with `=off` ([RayNeo audio doc](https://rayneo.gitbook.io/rayneo-devdoc/x-xi-lie/android-kai-fa/neng-li-jie-shao/yin-pin-kai-fa)). The exact X3 string is **UNVERIFIED**. The fallback is Android `AudioSource.VOICE_RECOGNITION`, which AOSP requires to be flat (±3 dB, 100 Hz–4 kHz) with preprocessing off ([AOSP](https://source.android.com/devices/audio/implement-pre-processing)). That is what ASR wants.
- **Format:** PCM16 16 kHz mono in 20 ms frames (640 B) on the architect's WebSocket binary stream (`audio.up`, `pcm_s16le`).
- **VAD on the companion:** Silero VAD (MIT, ~2 MB, <1 ms per 30 ms chunk on one thread; [README](https://raw.githubusercontent.com/snakers4/silero-vad/master/README.md)) trims silence and rejects no-speech presses.
- **Mic gating:** capture is muted while TTS plays. A press during TTS cancels the read-back and never confirms.

### 1.3 ASR: where it runs, primary and fallback
ASR runs on the **companion**, which is a laptop in Phase 0 per the architect, with ARM64 later. On-glasses ASR on the AR1 is only a measured fallback (B5), because of the 245 mAh battery and thermals.

Published comparison: response latency from phrase end to transcript, using faster-whisper CPU for Whisper ([Moonshine vs Whisper](https://moonshine-voice.readthedocs.io/en/latest/moonshine-vs-whisper/), [models](https://moonshine-voice.readthedocs.io/en/latest/models/available-models/)).

| Model | Params | WER (Open ASR avg) | Linux x86 | Pixel 10a | Licence |
|---|---|---|---|---|---|
| Moonshine Tiny Streaming | 34M | 12.00% | 69 ms | 92 ms | MIT |
| Moonshine Small Streaming | 123M | 7.84% | 165 ms | 234 ms | MIT |
| Whisper Tiny | 39M | 12.81% | 1,141 ms | — | MIT |
| Whisper Small | 244M | 8.59% | 3,425 ms | — | MIT |

These are vendor numbers. We re-run them on our 2-CPU box. Moonshine's library and English models are MIT ([repo](https://github.com/usefulsensors/moonshine)).

- **Primary: Moonshine Small Streaming** (Tiny Streaming on weak hardware). It decodes while the operator talks, which gives HUD partials, and has the best published CPU accuracy/latency. Whisper's latency comes from padding to 30 s windows.
- **Biased fallback: sherpa-onnx streaming zipformer** (`…-en-20M-2023-02-17` or `…-en-2023-06-26`) with **hotwords**. Hotwords are an Aho-Corasick boost in `modified_beam_search`, transducer models only, with no retraining ([hotwords](https://csukuangfj.github.io/sherpa/onnx/hotwords/index.html)). This is our lever for call signs, "niner" and the NATO alphabet if Moonshine's slot accuracy falls short. Transducers emit "FOUR ZERO ZERO" rather than a normalized "400", which suits a deterministic parser. sherpa-onnx is also a single Kotlin/Python runtime for VAD, KWS, Piper TTS and Moonshine on Android arm64 and Linux x64 ([README](https://cdn.jsdelivr.net/gh/k2-fsa/sherpa-onnx@master/README.md)), so it is the on-glasses fallback runtime.
- **Closed-grammar confirmation recognizer: Vosk `small-en-us-0.15`** (40 MB, Apache-2.0, runtime vocabulary; [models](https://alphacephei.com/vosk/models)). It runs on the confirmation press only, with the grammar `["confirm","cancel","say again","[unk]"]`. Anything else decodes to `[unk]`, which is what false-accept control needs.
- **Baselines only:** faster-whisper `base.en`/`small.en` int8 (MIT; [repo](https://github.com/SYSTRAN/faster-whisper)) and whisper.cpp with GBNF grammar-guided decoding (`--grammar`; [example](https://huggingface.co/datasets/echodict/whisper.cpp/blob/main/examples/command/command.cpp)). They stay off the live path because of latency and hallucination on noise.

Hotword/biasing list (shared across engines): call signs (`DRONE ONE…FOUR`), the NATO alphabet, digits plus `NINER`, prowords (`SAY AGAIN`, `CANCEL`, `CONFIRM`), verbs, named points from the world model, and alert names.

### 1.4 Parsing: deterministic first, LLM only to normalize
1. **Normalizer** (pure, exhaustively tested): `niner→9`, NATO alphabet→letters, digit strings ("four zero zero"→400) and compounds ("two thousand five hundred", "one point five kilometres"→1500 m). Mixed-style numbers ("two hundred fifty five zero") are **rejected**, never guessed. The default unit is metres, and the read-back always states the unit.
2. **Grammar parser:** a Lark (MIT) Earley grammar producing the architect's `CommandIntent.parsed`. Shape: `[callsign] verb [target] [modifiers]`. Spoken verbs → enum:

| Spoken | Enum | Target / params |
|---|---|---|
| launch / take off [to N] | takeoff | alt_m |
| go to / move to | goto | point |
| orbit / circle | orbit | point, radius_m, alt_m |
| watch / look at / observe | observe | track or point |
| search / scan [area] | search | area (named, or grid + size) |
| follow (only "follow contact N") | follow | track, standoff ≥ policy |
| hold / stop / abort | hold | — |
| return / RTB / come home | rtl | — |
| land | land | — |
| status | (query, no proposal) | — |

   Per the PM, "track" is not a spoken verb: use **watch**.
   Targets:
   - **MGRS:** zone + band + square + an even 2–10 digit count, validated with `mgrs`/`pyproj`.
   - **Clock + range:** "two o'clock, four hundred", resolved with the `head.pose` heading snapshot at end-of-speech.
   - **Named points:** "waypoint alpha".
   - **Relative:** "three hundred north of waypoint alpha".
   - **Alert references:** "contact one", or "the vehicle" when it is unique.
3. **Optional LLM normalizer** (only when step 2 fails). Qwen2.5-0.5B/1.5B-Instruct (Apache-2.0; [card](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct)) runs as GGUF under llama.cpp, GBNF-constrained to emit **canonical command text** only ([grammars](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md)). That text is re-parsed by the same Lark grammar. A **grounding check** then requires every number, letter and name in the output to appear in the normalized transcript, or the reply is "say again". This stops invented grid digits. `parser.method="llm"` caps confidence. A cloud LLM is benchmark-only.

### 1.5 Safety: confirmation state machine
These states feed the architect's `CommandProposal`:

`IDLE → LISTENING (PTT) → PARSED → READBACK → AWAIT_CONFIRM (10 s, nonce) → CONFIRMED → DISPATCHED`, with exits to `CANCELLED | EXPIRED | SAY_AGAIN | REJECTED(out-of-scope/invalid)`.

- **A single utterance never executes.** The command and its confirmation take two separate presses, and the confirmation press must start after read-back ends.
- **Read-back is canonical and absolute.** Example: "Drone two. Orbit. Bearing zero six zero, four hundred metres. Radius two hundred." The HUD shows the same text. Grids are read digit by digit in groups.
- **Confirmation** is "confirm" spoken alone, recognized by both the open ASR **and** the Vosk closed grammar, or a companion touch (`method: touch`). Other speech is a no-op. "Cancel" or a timeout discards the proposal. Only **one** proposal can be pending, and a new command visibly replaces it. "Yes/okay/roger" are excluded because they are too common in chatter.
- **Confidence gating.** A proposal requires a full grammar match, every critical slot (call sign, verb, numbers, grid letters) above threshold, and passing safety checks (asset state, geofence, altitude). The slot threshold uses token posteriors where the engine exposes them (**UNVERIFIED** per engine), or two-engine agreement otherwise. A failed slot gets a targeted "say again grid", up to twice, then the flow drops to touch.
- **Self-trigger hardening:** the mic is gated during TTS, and TTS never says the confirm word (the HUD shows "say CONFIRM").
- **Audit log:** append-only JSONL with the audio SHA-256, n-best, model hashes, the parse, the read-back, and every timestamped state transition plus the confirm method. It doubles as the latency trace.
- **HOLD/ABORT:** a companion touch STOP is itself an explicit human action. Voice "hold" stays confirm-gated (open question 1).

### 1.6 TTS read-back
- The **HUD text is primary**. TTS is secondary and can be switched off for silent operation.
- **Piper voices run in sherpa-onnx's runtime**, not `piper1-gpl`, which is GPL-3.0 ([repo](https://github.com/OHF-Voice/piper1-gpl)).
- **Voice licences follow their datasets.** `en_US-lessac` uses Blizzard-2013 Lessac data, which is research-only ([licence](https://www.cstr.ed.ac.uk/projects/blizzard/2013/lessac_blizzard2013/license.html)), so it is limited to eval. The product voice must have a permissive dataset (e.g. LJSpeech); check each MODEL_CARD.
- **Playback:** synthesized on the companion and sent as `audio.down`. On-glasses Android `TextToSpeech` works only if an engine is installed (B4, **UNVERIFIED**).

### 1.7 Latency budget (end-of-speech → read-back)

| Stage | Budget |
|---|---|
| PTT release + 150 ms tail, last frame over Wi-Fi | 200 ms |
| ASR finalize (streaming, already caught up) | 250 ms |
| Normalize + parse + safety checks + proposal | 30 ms |
| HUD card rendered | **≈ 500 ms p50** |
| TTS first audio (streamed) | +300 ms → **≈ 0.8 s p50** |
| LLM fallback path (when used) | +1–3 s, **UNVERIFIED on 2 CPU** |

Targets: p95 ≤ 1.5 s on the grammar path, within the PM's p95 ≤ 2.5 s budget. Confirm press → `Execution.sent` ≤ 500 ms.

## 2. Interfaces / needs from other experts
- **Architect:**
  - Add to `CommandIntent`: `utterance.nbest[]`, per-slot `slots[].{name, raw_tokens, value, conf}`, `heading_snapshot_deg`, `asr{engine, model_sha}`.
  - The nonce is never spoken.
  - Add `voice.partial/final`, `audio.down`, and `HudState.voice.state` (`idle|listening|processing|readback|await_confirm|say_again`).
  - The grammar's verb table is generated from the schema enum.
- **HUD (Alisha):** an indicator for each voice state; a proposal card (call sign, verb, absolute target, large numbers, 10 s countdown ring, "say CONFIRM / CANCEL"); a say-again state that highlights the failed slot; an executed/cancelled toast; nothing in the center.
- **Sim / assets (Arjun):** verbs map to `AssetAdapter`; expose asset state (no orbit when landed, battery, link), geofence, home, named points, and ack/nack reasons ("Drone two unable: geofence").
- **Vision/ML (Anshuman):** **speakable**, unique short names for active alerts (`contact one`, `vehicle two`).
- **Platform (Arjun):** the PTT event source, the RayNeo audio-mode string, mic mute during playback, and about one companion core for under 1 s per press.

## 3. Buildable pre-arrival, and how to verify
1. **`voice/grammar` + normalizer + Lark parser.** 400+ golden utterance→intent fixtures in `schemas/fixtures`, Hypothesis property tests (number round-trip: number→speech→number; MGRS round-trip), and negative fixtures: out-of-scope verbs (`fire`, `engage`, `drop`) must yield `REJECTED`, mixed number styles must yield rejection, and so must unknown call signs.
2. **Confirmation state machine** with a property test: no `DISPATCHED` without a matching unexpired nonce, a separate press, and a "confirm" recognized alone. An adversarial suite replays 10,000 non-confirm utterances plus chatter into AWAIT_CONFIRM. **Target 0 false confirms.**
3. **Synthetic noisy test set.**
   - **Text:** sample 2,000 commands from the grammar, stratified by verb, target type and number style, plus about 30 hand-written paraphrase templates per verb.
   - **Voices:** Kokoro-82M (Apache-2.0, 54 voices/8 languages, using its English voices; [card](https://huggingface.co/hexgrad/Kokoro-82M)) and several Piper voices, with 0.9/1.1 speed perturbation.
   - **Noise:**
     - MUSAN noise (CC BY 4.0, [OpenSLR 17](https://openslr.org/17)).
     - ESC-50 classes helicopter, engine, wind, rain, chainsaw and siren. ESC-50 is **CC BY-NC 3.0** overall. The ESC-10 subset, which includes helicopter, chainsaw and rain, is CC BY ([repo](https://github.com/karolpiczak/ESC-50)). We use NC clips for internal evaluation only and never redistribute them.
     - Freesound clips filtered to **CC0**: rotor/drone hum, gusting wind, diesel idle, distant gunfire/explosions as ambient noise.
     - A per-clip `noise_manifest.csv` records source, ID and licence.
   - **Mixing:** **clean, 20, 10, 5 and 0 dB SNR** on active-speech RMS, plus a "glasses channel" step (band-limit, wind bursts, mild clipping).
   - **Confirmation set:** "confirm"/"cancel" plus 1 h of distractors (babble, commands, read-back echo).
4. **ASR bake-off harness** on the 2-CPU box: Moonshine Tiny/Small Streaming; sherpa zipformer ±hotwords; Vosk small/lgraph; faster-whisper base.en/small.en int8 ±hotwords; whisper.cpp + GBNF.
   - Metrics:
     - WER (jiwer, on normalized text)
     - **intent accuracy** (verb + asset)
     - **slot exact-match** (critical slots digit-exact)
     - **confident-wrong rate** (a valid but wrong proposal, which is the safety metric)
     - say-again rate
     - confirmation FA/FR
     - p50/p95 latency and RTF
   - Output: a curve per SNR. Proposed bar at 10 dB: intent ≥95%, slot exact ≥90%, confident-wrong ≤0.5%.
5. **Companion voice service + replay client.** The client streams WAVs at real-time pace over the real WebSocket protocol to emulate the glasses, so CI runs E2E voice→proposal→confirm→MockAssetAdapter with no hardware. It feeds the HUD emulator.
6. **Android capture module (Kotlin).** `AudioRecord` + RayNeo mode set/reset + 20 ms framing + PTT session, with JVM unit tests for framing. It builds here and runs on day 1.

**Week-1 glasses tests (voice):**
- **B1:** log all temple/ring input events.
- **B2:** 10 s recordings in each RayNeo mode. Check the delivered rate and channels, wearer vs bystander level and SNR, and whether VOICE_RECOGNITION applies hidden NS/AGC.
- **B3:** frame round-trip and jitter to the companion.
- **B4:** `TextToSpeech` engines present, and speaker bleed into the mic during playback.
- **B5:** sherpa-onnx Moonshine-Tiny/zipformer RTF and battery drain on the AR1.
- **B6:** record team members reading 100 grammar commands, indoors and outdoors in wind, as the first real test set (consent recorded).

## 4. Risks and mitigations

| Risk | Mitigation |
|---|---|
| RayNeo audio mode string or behaviour differs from the doc (doc is partly Chinese) | Test B2 on day 1; fallback to standard `VOICE_RECOGNITION`/`MIC` + our own processing |
| Synthetic→real gap: Lombard speech, accents, stress, wind on the glasses mics | Treat synthetic results as ranking/regression only; collect B6 data and PM's dB(A) curve through the real mics; a close-talk BT headset fallback |
| Digits/grids misheard | Digit-by-digit read-back, per-slot say-again, hotwords; the demo favours named points and clock+range |
| Encoder-decoder hallucination on noise/silence | PTT + VAD trim, grammar must match, reject no-speech presses |
| LLM invents values | Constrained to canonical text, re-parsed, grounding check, capped confidence |
| Self-trigger / accidental confirm | Two presses, mic gating, confirm-alone AND two-recognizer agreement, nonce + 10 s expiry, one pending proposal |
| Confirmation fatigue slows operators | Short read-backs; touch confirm; measure in Alisha's study |
| CPU contention with Goal-2 inference | Voice runs only during PTT; pin a core; Tiny Streaming fallback |
| Licence traps: Porcupine gone, openWakeWord models NC, ESC-50 NC, Lessac research-only, piper1 GPL | Licence manifest in repo; product path uses MIT/Apache/CC BY/CC0 only |

## 5. Open questions
1. Voice `hold/abort`: does a touch STOP count as the explicit confirmation? I propose yes. Voice hold stays confirm-gated. Needs PM/SME sign-off.
2. Confirm vocabulary: "confirm/cancel" or operator prowords ("execute/disregard")? Validate with operators.
3. Call-sign scheme and multi-asset utterances ("all drones"). I propose that Phase 0 has no broadcast commands.
4. Units: altitude in metres or feet AGL? MGRS precision required in the demo (8 vs 10 digits)?
5. Is the TTS read-back wanted at all in the demo, or is the HUD only, given the voice-discipline objection?
6. Does RayNeo expose temple gestures and the speaker/mic routing to glasses-native apps? (B1/B4)
7. Is the optional cloud LLM path worth benchmarking in Phase 0, or is it deferred?
