VERDICT: CHANGES REQUIRED

Probes run here with Kokoro TTS plus white noise. On Py 3.13, `moonshine-voice==0.1.6`, `sherpa-onnx==2.0.3`, `vosk==0.3.45` and `lark==1.3.1` all install, and both models download.

1. **MAJOR · §3.3, §3.2, D4: the grammar assumes spoken-form tokens, but the primary ASR outputs written form.** Moonshine output on clean TTS: "two o'clock four hundred" → `Drone 2 Orbit 2, a clock 400.`; the grid → `Drone 1 Orbit Grid 6 1423705`; "radius one five zero" → `Radius 150.` §3.3 as written fails 3 of the 10 probe commands, and the "mixed number styles" rule can't be applied. **Fix:** give the normalizer two profiles, `spoken` (zipformer) and `written` (Moonshine). `written` does the following: case-fold; strip punctuation; map `a clock|o clock|oclock|2:00` → `o'clock`; join adjacent digit tokens inside a grid slot; take a distance as exactly one numeric token; parse `1k|1 km|klick(s)`. Homophones (`to/too→2`, `for→4`, `won→1`, `ate→8`) are mapped only in callsign and number slots. Add to D4: **≥150 fixtures captured from real Moonshine output** of TTS commands, committed as text. Acceptance: 100% pass.

2. **MAJOR · §3.3 named points, §7.3 demo: "NAI" isn't recognized.** "drone one scout N A I one" → `scout n i1` (clean) / `and i1` (10 dB) / `shot and idle` (0 dB). That's the demo's headline line. **Fix:** add `aliases[]` to gazetteer entries (`nai one: [n i 1, and i 1, nay 1, n a i 1]`). Add a D10 acceptance: every gazetteer name in `demo_vignette.yaml` parses from Moonshine at clean and at 10 dB on 3 TTS voices.

3. **MAJOR · §3.2 confirm recognizer, §3.4, G1: the confirmation confidence has no real source.** Moonshine's `TranscriptLine` has no confidence field, so "conf ≥ 0.80" can't be computed. Vosk's closed grammar `["confirm","cancel","say again","[unk]"]` decoded **conform, confirmed, can firm, come from, inform and concern as `confirm` at conf 1.0**. Moonshine transcribed all of those correctly. The 10,000-utterance text suite can't support G1's "0 executions". **Fix:** (a) a voice confirm requires the normalized open-ASR text to equal `confirm` exactly. No stemming, so "confirmed" is rejected. (b) In P1, the Vosk grammar gets decoys: `["confirm","cancel","say again","conform","confirmed","inform","concern","come from","firm","[unk]"]`, and AND-agreement is required. (c) Add to D10: an **audio lure suite** of ≥40 confusables × 3 voices × {clean, 10, 5, 0 dB} through the real engine and confirm rule. Acceptance: **0 confirms**, with the FR rate reported. For engines without confidence, drop `τ_confirm` and set `asr_conf=null` (sherpa has `ys_probs`).

4. **MAJOR · §3.4 valid Confirmation: the read-back may never have been seen, and press outcomes during the card are undefined.** TTS is off (C19), so the card is the only read-back. A companion can't know the operator saw a card the glasses never rendered. "Anything ambiguous counts as cancel" doesn't define the outcome of `watch` or `map 500` spoken mid-card. **Fix:** a confirm is valid only after `hud.event{card_shown, ref=proposal_id}` has been received, and only from a press with `ptt_down` ≥ `lockout_until_ms` (companion clock). Expiry is judged on `ptt_up ≤ expires_ms`, with a 1.5 s grace for the ASR final. Define what a press does during AWAIT_CONFIRM:

   | Press result | Effect |
   |---|---|
   | `confirm` | CONFIRMED |
   | cancel | CANCELLED |
   | stop | stop + SUPERSEDED |
   | a new command | SUPERSEDED, new card |
   | `say again` | re-render the card, expiry unchanged |
   | `hud_cmd` or alert response | applied, card kept |
   | empty / unparsed / press started in lockout | no change |

   `fake_glasses` must emit `card_shown`. Add each row as a D3 test.

5. **MAJOR · §3.7 temple gestures, C08: a triple-tap stop can first dismiss the alert.** If double-tap fires on taps 1–2, the triple-tap STOP also DISMISSes the shown alert, which suppresses it for 10 min. That alert may be a WARNING `contact_close`, which can't escalate any further. **Fix:** the companion holds `double_tap` actions for 400 ms and drops them if a `triple_tap` arrives (raw events per C15). Add a D3 test for the sequence double_tap@0, triple_tap@250 ms → stop only, no Feedback.

6. **MAJOR · §3.3 `safety_stop`: the grammar misses common ways of saying stop.** People under stress say "abort abort", "stop, stop", "all stop", "hold position", or "drone two orbit… abort". All of these fail the grammar, so the stop is missed, which L1/C31 treat as the bad error. At 0 dB, "all drones hold" came back as `All grown tolls`. **Fix:** `safety_stop := [("all" ["drones"|"assets"]) | callsign] stop_word+ ["position"]`. Also run token spotting as a fallback: if an utterance doesn't parse as any other rule and contains a standalone stop word, it's a stop, scoped to the callsign directly before the word, otherwise all. Add these to the D4 fixtures.

7. **MAJOR · §3.4 I1, §2.6 search: mission upload isn't confirm-gated.** If the vehicle is in AUTO.MISSION, uploading `MISSION_COUNT/MISSION_ITEM_INT` changes its path even without `MISSION_START`. **Fix:** I1's list becomes "…mission start, **mission-type upload or clear**…". Lawnmower items are uploaded only after Confirmation, and the upload time counts in confirm→sent (still ≤500 ms locally).

8. **MAJOR · §3.8 MicSource, §1.4 loop 1: PTT clips the first word.** `ptt_down` fires at 300 ms, so the first ~300 ms of speech is lost. That's usually "drone", which turns most commands into a SAY_AGAIN for a missing callsign. **Fix:** on a single-pointer DOWN, start `AudioRecord` into a 500 ms local ring buffer. On `PttDown`, send the buffer and then live frames. On a tap, gesture or two-finger touch, discard it. Nothing leaves the device without PTT. Add to D12: a JVM test that frames from DOWN−0 ms are included in `audio.up`.

9. **MAJOR · D10, §6.1: the noise sources can't be fetched as specified.** MUSAN is a single 11.09 GB tarball. Freesound's API returns 401 without a key. The ESC-50 archive URL returns 403, though `git clone` works. **Fix:** source noise from procedural noise (pink, wind, rotor harmonics), babble mixed from 4–6 Kokoro voices, OpenSLR 28 `rirs_noises.zip` (1.31 GB) and ESC-50 via `git clone` (NC, eval only). MUSAN and Freesound become opt-in `fetch noise --musan|--freesound-key`. Extend the SNR sweep to −5 dB.

10. **MINOR · §3.2 latency, C32 CPU budget.** Measured on 2 idle CPUs: Moonshine Small streaming finalize took 133–174 ms, inside the 250 ms budget. But each partial update took ~230 ms, and at a 0.25 s interval that's about one core during speech. The detector also takes about one core here (2 feeds × 2 Hz × 250 ms). **Fix:** set `voice.partial` to ≤2 Hz (0.5 s interval), and drop the detector to 1 Hz while PTT is down. D10 should report p95 latency both idle and under `edith up`.

11. **MINOR · §4.2 pins.** Pin `moonshine-voice==0.1.6`. It has **no Intel macOS wheel** (manylinux_2_34, macOS 15 arm64, win only), so `doctor` should say so. Pin `sherpa-onnx==2.0.3` and `vosk==0.3.45`. Put the Moonshine model (`small-streaming-en/quantized_26_11_02`, from download.moonshine.ai) into `models.yaml` with its sha256. **Never add the `piper-tts` package**: on PyPI it's piper1-gpl (GPL-3.0). Use sherpa-onnx or moonshine-voice for Piper and Kokoro voices.

12. **MINOR · G1 / §6.1 definitions.** Pre-register "intent success" as a correct proposal with every slot exact, allowing ≤1 say-again. Define "confident-wrong" as a wrong proposal reaching the card; Moonshine turned "one five zero" into `152` at 0 dB. The corpus generator needs its own verbalizer, not the normalizer's inverse, plus ≥100 human-written paraphrases.

13. **MINOR · §3.7 two-finger hold vs PTT.** A two-finger hold passes 300 ms, so it would open PTT. The PTT FSM must check the pointer count before 300 ms, and a two-finger touch must never open a voice session. Add this to the D12 JVM tests.
