VERDICT: CHANGES REQUIRED

R2 review by the Robotics & Simulation expert. Every **[probed]** fact was checked against PX4 tag `v1.18.0-rc2`.

1. **BLOCKER. §3.6 and D6: `demo_vignette` is kinematically infeasible.**
   - PX4 defaults are `MPC_TKO_SPEED` 1.5 m/s and `MPC_XY_CRUISE` 5 m/s [probed]. At those speeds D1 reaches NAI 1 (878 m away) at about t≈250, so the vehicle alert's `by_t: 90` cannot be met.
   - D2 is never tasked. A disarmed PX4 takes no data-link-loss action, so "D2 lost → RTL" never happens.
   - The confirm-timeout case required by D6 is missing from the YAML.
   - The test passes only on an unfaithful Mock, which is exactly what breaks the PX4 swap.
   - Fix:
     - Add `px4_params: MPC_TKO_SPEED: 3, MPC_XY_CRUISE: 10, MIS_TAKEOFF_ALT: 60, RTL_RETURN_ALT: 60`. Mock reads these same keys.
     - Set NAI 1 to `{e: 0, n: 200}`.
     - Add `say` events at t40 "drone two overwatch my position", t43 "confirm", and t200 "drone one orbit nai two" (left unconfirmed).
     - Move the jam to t300.
     - Change the expects:
       - The alert is checked `within_s_of: {gt: entity_in_fov, asset: drone1, entity: veh-7, max_s: 5}`.
       - `{by_t: 75, asset: {id: drone2, mode: POSCTL.ORBIT}}`.
       - `{by_t: 211, proposal: {state: expired}, mavlink_commands_since: {t: 200, count: 0}}`.
       - `{by_t: 322, gt: {asset: drone2, mode: AUTO.RTL}}`.
       - `{by_t: 322, asset: {id: drone2, link: lost}}`.
     - Add a loader lint that fails any `by_t` that is infeasible under the `px4_params` kinematics.

2. **MAJOR. §2.6 and D2: Mock is only checked against our own adapter.**
   - Add `sim/edith_sim/px4_profile.py`, shared by Mock and the adapter. It covers:
     - Heartbeat `autopilot=12`, `type=2`, sysid i+1.
     - Mode encoding `custom_mode = main<<16 | sub<<24`, where **orbit = `POSCTL.ORBIT` (3/1), not AUTO** [probed].
     - `COMMAND_ACK` per command.
     - `COM_DISARM_PRFLT` 10 s auto-disarm [probed].
     - `DO_REPOSITION`→LOITER, mission end→LOITER, RTL→LAND→disarm.
     - The `MISSION_REQUEST_INT`/`ACK` handshake.
     - Byte-wise int32 `PARAM_SET`.
     - The SITL battery: it floors at 50% within 30 s [probed], so set `SIM_BAT_DRAIN: 1800, SIM_BAT_MIN_PCT: 10, COM_LOW_BAT_ACT: 0` (the SITL default is 3 [probed]).
   - C09 sequences:
     - Landed + search: upload `[NAV_TAKEOFF, waypoints]`, then arm, then `MISSION_START`.
     - Landed + goto/orbit: arm, send `NAV_TAKEOFF` immediately, then send the verb once `IN_AIR` and altitude ≥0.9 × target.
   - Define `completed` per verb:
     - takeoff: altitude within ±1.5 m.
     - goto: within 5 m and in LOITER.
     - search: last `MISSION_ITEM_REACHED`.
     - rtl/land: `ON_GROUND` and disarmed.
   - Parametrize the contract suite with `--assets mock|px4`. Add `edith sim record-px4` to capture a golden PX4 trace (modes + ACKs) on any laptop. CI diffs Mock against that trace.

3. **MAJOR. §2.1, §4.3 and C12: the time base.**
   - When `PX4_SIM_SPEED_FACTOR` is set, rcS runs `param set COM_DL_LOSS_T = 10×speed` [probed]. That overrides C12.
   - Fix:
     - The supervisor exports `EDITH_T0_NS` and `EDITH_SPEED`. Every process uses `SimClock = (wall−T0)×speed`, including the Mock step, the GCS heartbeat, linkshaper windows and the expects.
     - Scenario params are applied **after boot** and verified by read-back; abort on mismatch.
     - Cap the camera wall rate at 15 fps. D6 must not depend on video throughput.

4. **MAJOR. §3.4: a stop does not cancel adapter loops.**
   - The `observe/follow(track)` re-issue at ≤1 Hz, command retries and pending mission uploads can each override a hold.
   - Add **I7**: after a `SafetyStop` at t_s on asset *a*, no motion-adding message reaches *a* unless it comes from a proposal confirmed after t_s.
   - `stop()` cancels those tasks before it sends the hold. Hypothesis tests I7 against the wire log (item 9).

5. **MAJOR. §1.4 loop 3, D5 and D6: a TAK jam is undetectable.**
   - Multicast gives no feedback. A userspace proxy also cannot sit inside a multicast path. "Flushed, order preserved" is therefore unprovable.
   - Fix:
     - In sim runs the mesh transport targets linkshaper at `127.0.0.1:16969`, which forwards onward.
     - `tak.link=ok` only while inbound CoT or a `t-x-c-t` pong has arrived within 3 s (the teammate sim sends at 1 Hz).
     - The outbox replays the last 30 s of sent events plus the queue, in order, on recovery. CoT is idempotent on uid and time, so duplicates are harmless.
     - Assert flush on the **fake router's received log**.

6. **MAJOR. §2.4: camera interfaces.**
   - (a) `gt_detector` has no per-frame boxes. Add `FrameTruth{frame_id, t_sim_ms, asset_id, objects[{entity_id, cls, bbox_norm, visible_frac, range_m, lat, lon}]}` on UDP **5800+i**, opened only for gt and bench runs.
   - (b) Gimbal: add `gimbal.mode: stabilized|body_fixed`.
     - Stabilized is the default: pitch is relative to the horizon, yaw is relative to the body, and body roll/pitch are ignored.
     - Use the optical frame x-right, y-down, z-forward.
     - If the camera and projector disagree, CEP90 fails at orbit bank angles.

7. **MAJOR. §6.2 and G2: replay has no true pose.**
   - On replay, geo-based recall matching and CEP are undefined.
   - Fix: on replay, match recall in image space (IoU ≥0.3 against the annotated track within 10 s). Take CEP from the synthetic tier only.
   - Mark replay detections `geo_quality: pseudo`. They never raise `contact_close`.

8. **MINOR. §2.6: frames and units.**
   - Commands use `COMMAND_INT` `MAV_FRAME_GLOBAL` (AMSL). Mission items use `GLOBAL_RELATIVE_ALT_INT`.
   - Fence items are type 5001 with p1 = vertex count, plus `GF_ACTION: 1` and `GF_MAX_VER_DIST: 120`.
   - Orbit velocity is 5 m/s.
   - Search spacing = centre-line ground width × 0.7 (≈68 m).

9. **MINOR. §2.5: wiring.**
   - Linkshaper binds 14540+i. Mock binds 14580+i and sends to 14540+i, exactly like PX4.
   - The companion listens on `udpin` 14740+i.
   - An unimpaired truth tap on 14640+i feeds one `simd` process.
   - `runs/<ts>/mavlink_wire.jsonl` backs `mavlink_commands_since` and I1/I7.
   - The companion uses sysid 245.
   - Liveness counts any message, not just HEARTBEAT.
   - `doctor` fails if 14550 is bound (a foreign GCS masks link loss).
   - The camera honours `video:<asset>` jam windows.

10. **MINOR. D7: RTP pts.** The muxer randomizes the base timestamp. The sender sets `pts = frame_id·90000/fps`; the receiver anchors on the first sidecar pair. Acceptance is ≥99% correct, checked with a test-only frame-ID barcode.

11. **MINOR. D2: determinism.** Hash the mover and jam schedule, plus Mock stepped in-process (dt 20 ms, scripted commands). Socket runs use tolerances.

12. **MINOR. §3.7: hold during link loss.** A hold is never queued for a `lost` asset. The toast reads `D2 HOLD NOT SENT · LINK`.
