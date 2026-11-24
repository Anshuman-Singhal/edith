VERDICT: CHANGES REQUIRED

1. **MAJOR — §3.5 fusion/alerts, §2.7, D5/D8: no friendly-force association.** "Drone two overwatch my position radius 150" points D2's camera at RAVEN 1–4. Every teammate then becomes an `a-u-G` PERSON, and anything within 150 m raises a `contact_close` WARNING. A WARNING invalidates any pending proposal (§3.4), so the vignette breaks itself. It also puts an unknown symbol on top of a friendly on the TOC's ATAK. To an operator that is the first thing that makes a system look untrustworthy. **Fix:** add §3.5 row "Friendly association: a `person` track within max(15 m, 2·ce_m) of a friendly PLI fresher than 30 s is tagged `assoc_friend_uid`. It raises no alert, is not published to CoT, and is drawn only as the existing friendly symbol. Affiliation stays `unknown` (I6 untouched)." In the sim, render teammates as person sprites. Add a D8 test: teammate in FOV gives 0 alerts and 0 CoT. Add a D6 expect: 0 WARNINGs during the overwatch segment.

2. **MAJOR — §1.4 loop 3, D5, D6: outbox can't know the mesh is down.** UDP multicast has no delivery feedback. The only signal is silence from peers, and with PLI every 10 s it takes about 20–30 s to notice. That is the whole 25 s jam. So events are lost rather than queued, and `outbox: {flushed: true}` passes without testing anything. **Fix:** define `status.tak` explicitly:
   - **TCP/TOC link:** the companion sends a TAK ping `t-x-c-t` every 3 s. After 2 missed `t-x-c-t-r` replies it is `lost`, and the outbox queues. The fake router on :18087 must answer pings. OTS ping support is UNVERIFIED.
   - **Mesh only:** the link is `lost` after 12 s with no inbound CoT from any peer, with teammate-sim PLI at 4 s. On recovery, re-send the latest state of every live track.
   - **At flush:** drop any queued event whose `stale` is already in the past. SPI at 10 s and drone PLI at 30 s will mostly be dropped.
   - **D6 expect:** `outbox: {queued_min: 5, flushed: true, order_preserved: true}`.

3. **MAJOR — §3.6 example and D6: the vignette timeline doesn't fit the kinematics, and the D2 replay floods it.**
   - **Timing:** D1 spawns at (−300,−280) and NAI 1 is at (400,250), 878 m away. With PX4 defaults (takeoff 1.5 m/s, cruise about 5 m/s, then a lawnmower pattern), D1 reaches the NAI around t≈250 s. `alert by_t: 90` cannot pass.
   - **D2 replay:** D2 runs a VisDrone urban clip registered onto an overwatch orbit of the operator. That geolocates dozens of persons and vehicles within 150 m of the operator, which means a WARNING storm.
   - **Fix:** `demo_vignette.yaml` uses `camera.mode: synth` for both drones. Replay is confined to `goal2_*.yaml`. Add `px4_params: {MPC_XY_CRUISE: 8, MPC_TKO_SPEED: 3}` and have MockVehicle mirror them. Move NAI 1 to {e: 150, n: 50}. Replace the absolute alert expect with a GT-relative one: `{after: {gt: entity_in_fov, entity: veh-7}, within_s: 10, alert: {kind: new_contact, cls: vehicle}}`. Add a scenario-lint test that every `by_t` is reachable from climb rate, cruise speed and path length.

4. **MAJOR — §2.6 `observe/follow(track)`, §3.3 `follow contact`, D21: continuous custody of a contact.** Re-issuing DO_ORBIT/DO_REPOSITION at ≤1 Hz on a track after a single confirm is autonomous pursuit of a person or vehicle. A reviewer will call it "Fix/Track" custody, the exact reading that L3 removed "track" to avoid. It is also a privacy problem for the SAR and police re-skins. My r1 FOLLOW meant "follow me". **Fix:**
   - `observe contact N` orbits the contact's fused position **frozen at confirm time** and does not re-target. A new position needs a new confirmed proposal.
   - Grammar becomes `"follow" ("me" | teammate_callsign) ["standoff" distance]`.
   - Remove `follow(track_stream)` from `AssetAdapter`; replace it with `follow(uid_stream)`, restricted to friendly PLI.
   - D21 acceptance: Mock follows the RAVEN 2 PLI at 30 m ±5 m. A gate test shows that a follow proposal referencing a track is REJECTED.

5. **MAJOR — §2.7, C04, D5: a DISMISS doesn't retract the CoT.** Machine tracks are published by default with a 300 s stale. When the operator dismisses the planted deer, the TOC keeps seeing an unknown PERSON for 5 minutes. That fails the vignette's credibility beat and pollutes the team picture. **Fix:**
   - On DISMISS, or when a published machine track is lost, emit a delete for that uid: `t-x-d-d` with `<link uid=… relation="none"/>` and `<__forcedelete/>`. Mark it UNVERIFIED for ATAK-CIV and add it to the week-1 LAN checks. Fallback: re-send the same uid with `stale` = now.
   - Specify uids: `EDITH-<companion>-D<n>` and `EDITH-<companion>-trk-<track_id>`.
   - D5 test: dismiss leads to a delete event within 1 s. D6 expect: after `dismiss(per-deer)`, `cot: {uid_live: false}`.

6. **MINOR — §2.7 `how`.** `m-g` asserts the entity's own GPS, which is wrong for a video-geolocated contact. Default to a machine-derived/fused code (`m-p`/`m-f`, UNVERIFIED against the CoT how taxonomy). That is a spec read, not an ATAK test. Define `ce_m` once (CEP50 or 1σ) and its mapping to CoT `ce`. hae = MSL + geoid N (≈ −33 m here, UNVERIFIED; EGM96).

7. **MINOR — D5 inbound.** ATAK-CIV may send TAK Protocol v1 mesh frames (`0xBF 0x01 0xBF` + protobuf). An XML-only parser would silently drop the real phone's PLI. Accept both via `takproto` (Apache-2.0), with a fixture for each.

8. **MINOR — D4.** REJECTED lexicon adds `target, designate, lase, paint, neutralize, destroy, kill, eliminate, hit, take out, cleared hot, call for fire, splash`. Never add "repeat" as a say-again synonym (fires usage: "fire again").

9. **MINOR — §3.5.** "≤2 alerts/min" is 120/h, far past what a dismounted leader tolerates, and conflicts with FA ≤6/h/drone. Use "≤2/min peak (any 60 s); ≤20/h mission mean; interviews set the budget."

10. **MINOR — §7.1.** The r1 guardrails are missing. Add: "Interviews: unclassified, personal capacity, no TTPs/unit specifics/CUI; no ITAR-marked documents; sponsor agreements via Penn Export Compliance (fundamental-research exclusion)."

11. **MINOR — §8.** State TRL 4 for Phase 0 and TRL 5–6 for the Phase 1 range flights. Cite "IVAS ~$80k/unit" or tag it UNVERIFIED (D19's own rule). DETAILS should push a SALUTE draft (Size, Activity, Location MGRS, Unit=UNKNOWN, DTG Z, Equipment) to `/ui/touch`.

12. **MINOR — §2.7.** "RAVEN" collides with the RQ-11 Raven sUAS; use "VIKING 1-1…1-4". Sim-sourced CoT gets `remarks` prefixed "EXERCISE", and sim teammates use `how="m-s"`.
