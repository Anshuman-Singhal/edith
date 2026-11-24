# Voice, grammar and confirmation spec (PLAN v2)

Normative detail for [PLAN.md §3.2–3.4](../PLAN.md#32-voice-pipeline). Owner: WS-C (Om).

## 1. Normalizer profiles (C66)

The ASR engine declares its output style, and the normalizer runs the matching profile before the Lark grammar. Both profiles produce the same canonical token stream.

| Step | `spoken` (sherpa zipformer, Vosk) | `written` (Moonshine) |
|---|---|---|
| Case / punctuation | lower-case | lower-case; strip `.,;:!?` |
| Clock | `two o'clock` | map `a clock`, `o clock`, `oclock`, `2:00` → `o'clock` |
| Numbers | `niner→9`, `fife→5`, `tree→3`, digit words → digits, compounds ("one point five k" → 1500) | a distance is exactly one numeric token (`400`, `1.5k`, `1 km`, `klick(s)`); adjacent digit tokens inside a grid slot are joined (`6 1423705` → `61423705`) |
| Homophones | — | `to/too→2`, `for→4`, `won→1`, `ate→8`, **only in callsign and number slots** |
| Mixed styles | Mixing digit words and numerals in one slot is **rejected**, never guessed | n/a (written form is uniform) |
| Gazetteer | Aliases from the scenario (`aliases[]`) map to canonical names (C66) | same |

## 2. Grammar v2 (Lark Earley)

```
utterance   := safety_stop | command | response | query | hud_cmd
safety_stop := [ ("all" ["drones"|"assets"]) | callsign ] stop_word+ ["position"]     # C49
stop_word   := "hold" | "abort" | "stop"
command     := callsign verb_phrase
callsign    := "drone" ("one"|"two"|"three"|"four"|DIGIT)                            # no broadcast tasking
verb_phrase := ("take off"|"launch") [ "to" distance ]                                -> takeoff
             | ("go to"|"move to") location [alt_mod]                                 -> goto
             | ("orbit"|"circle") location [radius_mod] [alt_mod]                    -> orbit
             | ("watch"|"overwatch"|"observe"|"look at") (location|contact) [radius_mod] [alt_mod] -> observe
             | ("search"|"scout"|"scan") area [alt_mod]                               -> search
             | "follow" ("me" | teammate) [ "standoff" distance ]                     -> follow (stretch, L8; C51)
             | ("return"|"r t b"|"come home") ["home"]                                 -> rtl   (needs confirm)
             | "land"                                                                 -> land  (needs confirm)
location    := "my position" | teammate | clock_range | grid | named | relative
teammate    := TEAMMATE_CALLSIGN                                                       # "viking one two"
clock_range := CLOCK "o'clock" [","] distance                                         # heading snapshot at PTT release
grid        := ["grid"] [ GZD SQUARE ] DIGITS{4|6|8|10}                               # 16T CK preloaded
named       := GAZETTEER_NAME                                                         # incl. aliases
relative    := distance CARDINAL "of" named
area        := named | grid [ "size" distance ]                                       # default square 300 m
contact     := "contact" NUM | "the" ("vehicle"|"person")                            # only if unique; observe only
radius_mod  := "radius" distance                                                      # 30–300 m
alt_mod     := "altitude" distance                                                    # 30–120 m AGL
distance    := NUMBER [ "meters"|"metres"|"m"|"k"|"km"|"kilometers"|"klick"|"klicks" ]
response    := "confirm" | "cancel" | "watch" | "mark" | "dismiss" | "say again" | "details"
query       := [callsign] "status"
hud_cmd     := "show" callsign | "hide feed" | "map" ("two fifty"|"five hundred"|"one k"|"two k")
             | "declutter" | "night mode" | "day mode" | "brighter" | "dimmer"
```

- **Stop token spotting (C49).** If an utterance parses as no other rule and contains a standalone stop word, it is a safety stop. The scope is the callsign directly before the word, else all. `stop_via=spotting` is logged. A false stop only removes motion (L1).
- **Contacts (C51).** `observe contact N` resolves to the fused track position **frozen when the proposal is confirmed**. A new position needs a new confirmed proposal. `follow` accepts only `me` or a teammate callsign with PLI <30 s; `follow contact …` is REJECTED with "Follow is for friendly positions only".
- **Bare responses (C81).** `watch`, `mark`, `dismiss`, `details` and `say again` apply only to the alert currently displayed (the last `hud.event alert_shown`). With none displayed the result is NOOP and the toast `NO ALERT`. Bare `watch` never moves an asset (C03).

## 3. Rejected lexicon (C66)

These are rejected with `REJECTED: "Unsupported command"`, and nothing is sent: `attack, engage, fire, drop, strike, shoot, target, designate, lase, paint, neutralize, destroy, kill, eliminate, hit, take out, cleared hot, call for fire, splash`. "Track" is not a spoken verb (L3). **"Repeat" is never a synonym for say-again**, because in fires usage it means "fire again".

## 4. Examples (golden fixtures, canonical read-back rows)

Read-back rows are measured with the bundled B612-Bold at 20 px and must be ≤490 px (C65). MGRS values are illustrative; the geo module computes them.

| Utterance (spoken / Moonshine written) | Result: row A / row B |
|---|---|
| "drone one scout N A I one" / `Drone 1 scout and i1.` (D1 landed) | `DRONE 1 → LAUNCH + SEARCH NAI 1` / `16T CK 6100 3704 · 300 m sq · ALT 60 m` |
| "drone two overwatch my position radius one five zero" / `Drone 2 overwatch my position. Radius 150.` | `DRONE 2 → LAUNCH + OBSERVE ME` / `R 150 m · ALT 60 m` |
| "drone two orbit two o'clock four hundred" / `Drone 2 Orbit 2, a clock 400.` | `DRONE 2 → ORBIT BRG 062 400 m` / `16T CK 6137 3699 · R 100 m · ALT 60 m` |
| "drone one orbit grid six one four two three seven zero five" / `Drone 1 Orbit Grid 6 1423705` | `DRONE 1 → ORBIT GRID` / `16T CK 6142 3705 · R 100 m · ALT 60 m` |
| "drone two watch contact three" | `DRONE 2 → OBSERVE CONTACT 3` / `FIXED AT CONFIRM · R 100 m · ALT 60 m` |
| "abort abort" / "stop, stop" / "all stop" / "drone two hold position" / "all drones hold" | Immediate stop, scoped; pending proposal SUPERSEDED |
| "drone two orbit … abort" (unparseable + stop word) | Stop for DRONE 2 via spotting |
| "drone two return" | Proposal (RTL needs confirm, L1) |
| "drone one attack the vehicle" | REJECTED; 0 MOTION on the wire |
| "drone one follow contact two" | REJECTED (C51) |
| "drone two orbit grid six one four two three seven" | SAY_AGAIN on the grid slot (odd digit count) |
| "watch" with an alert displayed | Feedback watch; inset pinned; no motion |

D4 ships ≥400 synthetic fixtures plus ≥150 fixtures captured from real Moonshine output (moonshine-voice 0.1.6, `small-streaming-en`) on Kokoro TTS. The capture tool commits them as text.

## 5. Confirmation (C48; single owner `companion/edith_companion/safety/confirm_rule.py`)

A Confirmation is valid only if **all** of the following hold:

1. The proposal is live (`await_confirm`), the `proposal_id` matches, and the internal nonce matches.
2. `hud.event{card_shown, ref=proposal_id}` has been received from the active glasses session. (With fake_glasses, the fake emits it.)
3. The press is not during lockout: `est_start = t_recv(ptt_down) − held_ms − rtt/2 ≥ lockout_until_ms` (600 ms after `card_shown`; longer while TTS plays).
4. The press belongs to this card: `ptt_down.ctx.proposal_id == proposal_id`.
5. The press is in time: `ptt_up` is received ≤ `expires_ms` (10 s after `card_shown`, C06). The ASR final may arrive up to 1.5 s later.
6. Method:
   - **voice:** the normalized open-ASR final equals exactly `confirm`. There is no stemming, so `confirmed` fails, and there is no confidence threshold when the engine gives none (`asr_conf=null`). In P1, the Vosk closed grammar `["confirm","cancel","say again","conform","confirmed","inform","concern","come from","firm","[unk]"]` must also return `confirm` (AND-agreement).
   - **touch_temple:** only when `confirm.temple_enabled` (set after T7 passes with 0 false triggers); `two_finger_hold` with raw-timed `duration_ms ≥ 1000`.
   - **touch_companion:** a `/ui/touch` hold ≥1 s carrying the proposal_id.
7. The gate re-check passes immediately before dispatch.

"Yes", "okay" and "roger" never confirm.

**Press outcomes while a card is open** (each row is a D3b test):

| Press result | Effect |
|---|---|
| `confirm` (rule above) | CONFIRMED → gate re-check → DISPATCHED |
| `cancel` | CANCELLED |
| stop (grammar or spotting) | stop executed; proposal SUPERSEDED |
| a new command | SUPERSEDED; new card |
| `say again` | card re-rendered; expiry unchanged |
| `hud_cmd` or an alert response | applied; card kept |
| empty, unparsed, or a press that started in lockout | no change |

## 6. Corpus and noise (C67, C69)

- **Verbalizer.** The corpus generator has its own verbalizer (not the normalizer's inverse) and ≥100 human-written paraphrases.
- **Voices.** Kokoro-82M and Piper voices through sherpa-onnx or moonshine-voice. **Never the `piper-tts` PyPI package** (it is piper1-gpl, GPL-3.0).
- **Noise.** Procedural pink, wind and rotor-harmonic noise; babble mixed from 4–6 Kokoro voices; OpenSLR 28 `rirs_noises.zip` (1.31 GB); ESC-50 via `git clone` (NC, eval only). MUSAN and Freesound are opt-in (`fetch noise --musan`, `--freesound-key`). SNR sweep: clean / 20 / 10 / 5 / 0 / −5 dB, plus a glasses-channel step. Pins and hashes live in `bench/noise.lock.yaml`.
- **Audio lure suite (D10a).** ≥40 confusables (conform, confirmed, can firm, come from, inform, concern, …) × 3 voices × {clean, 10, 5, 0 dB}, run through the real engine and `confirm_rule`. Bar: **0 confirms**, with the false-reject rate on true "confirm" reported.
- **Definitions (pre-registered).** *Intent success* = a correct proposal with every slot exact, allowing ≤1 say-again. *Confident-wrong* = a wrong proposal reaching the card. SPL is reported as Leq over 30 s in dB(A), measured at the wearer's ear.
