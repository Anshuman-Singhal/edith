package edith.selftest.tests

import android.os.SystemClock
import edith.platform.Gesture
import edith.platform.GestureEvent
import edith.platform.PcmStream
import edith.platform.RawTouch
import edith.platform.Stats
import edith.selftest.Screen
import edith.selftest.SelfTestActivity
import edith.selftest.proto.J
import edith.selftest.proto.Status
import java.io.File
import java.util.concurrent.Executors

/**
 * T7 PTT: press-and-hold trials on the right temple, left temple and with two fingers; a raw
 * triple-tap log; then a "normal wear" window that counts confirm-class false triggers.
 * For each press: DOWN → first captured audio frame (TESTS.md definition: event time of
 * ACTION_DOWN to the return of the first 20 ms AudioRecord.read after startRecording on a
 * pre-constructed recorder), hold duration, pointer count, device and the SDK DOWN/UP events.
 */
class T7Ptt(ctx: SelfTestActivity) : Screen(ctx, "T7", "PTT") {
    private data class Prompt(val key: String, val text: String, val presses: Int)
    private val wearS get() = ctx.intExtra("t7_wear_s", 300).takeIf { it > 0 } ?: 300
    private val prompts by lazy { listOf(
        Prompt("right_hold", "Hold the RIGHT temple ~1 s, release. 5 times.", 5),
        Prompt("left_hold", "Hold the LEFT temple ~1 s, release. 5 times. (No left pad? Skip from the laptop: adb shell input keyevent ENTER)", 5),
        Prompt("two_finger_hold", "Hold with TWO fingers ~1 s, release. 5 times.", 5),
        Prompt("triple_tap", "TRIPLE-TAP the temple. 3 times.", 3),
        Prompt("wear", "Wear normally for ${wearS / 60} min: adjust the frame, touch your face. Do NOT use the temple.", 0),
    ) }
    @Volatile private var p = 0
    private var presses = mutableListOf<MutableMap<String, Any?>>()
    private var cur: MutableMap<String, Any?>? = null
    private var curDownEt = 0L
    private var pressesInPrompt = 0
    private val latencies = mutableListOf<Double>()
    private val sdkSeen = sortedSetOf<String>()
    private var confirmClass = mutableListOf<Map<String, Any?>>()
    private var wearEndsAt = 0L
    private var rawLog: java.io.Writer? = null
    private var mic: PcmStream? = null
    private val audio = Executors.newSingleThreadExecutor()
    @Volatile private var lastLatency: Double? = null

    override fun intro() = listOf(
        "Press-and-hold trials (right, left, two-finger), a triple-tap log,",
        "then ${wearS / 60} min of normal wear counting false confirm-class triggers.",
        "Measures DOWN → first audio frame (pass ≤100 ms).",
    )

    override fun status(): List<String> {
        if (phase == Phase.DONE) return listOf("Result: ${result?.status?.wire?.uppercase()}",
            "DOWN→audio p95: ${result?.metrics?.get("down_to_first_frame_ms_p95")} ms",
            "false confirm-class triggers in wear: ${confirmClass.size}", "TAP = next")
        val pr = prompts[p]
        val extra = if (pr.key == "wear") "remaining ${((wearEndsAt - SystemClock.uptimeMillis()) / 1000).coerceAtLeast(0)} s   triggers ${confirmClass.size}"
        else "presses $pressesInPrompt / ${pr.presses}   last DOWN→audio ${lastLatency?.let { "%.1f".format(it) } ?: "-"} ms"
        return listOf("Step ${p + 1}/${prompts.size}:", pr.text, "", extra, "SDK events: ${sdkSeen.joinToString(" ")}")
    }

    override fun start() {
        val r = newResult()
        p = 0; presses.clear(); latencies.clear(); confirmClass.clear(); pressesInPrompt = 0
        rawLog = File(ctx.runDir, "t7_raw.jsonl").bufferedWriter()
        audio.execute {
            try { mic = ctx.platform.mic.open("VOICE_RECOGNITION", 16000, 1) }
            catch (t: Throwable) { r.error("mic.open", t) }
        }
        r.metrics["mic_source"] = "VOICE_RECOGNITION"
        save()
    }

    private fun log(o: Map<String, Any?>) { runCatching { rawLog?.write(J.of(o).toString() + "\n") } }

    override fun onRawTouch(e: RawTouch) {
        if (phase != Phase.RUNNING) return
        val pr = prompts[p]
        log(mapOf("k" to "touch", "step" to pr.key, "t" to e.tMonoMs, "et" to e.eventTimeMs, "a" to e.action, "n" to e.pointerCount,
            "x" to e.x, "y" to e.y, "dev" to e.deviceId, "dev_name" to e.deviceName))
        when (e.action) {
            "ACTION_DOWN" -> {
                val m = linkedMapOf<String, Any?>("step" to pr.key, "device" to "${e.deviceId}:${e.deviceName}", "x0" to e.x, "y0" to e.y, "pointers_max" to 1)
                cur = m; curDownEt = e.eventTimeMs
                if (pr.key != "wear") measureAudio(m, e.eventTimeMs)
            }
            "ACTION_POINTER_DOWN", "ACTION_MOVE" -> cur?.let { it["pointers_max"] = maxOf(it["pointers_max"] as Int, e.pointerCount); it["x1"] = e.x; it["y1"] = e.y }
            "ACTION_UP", "ACTION_CANCEL" -> cur?.let { m ->
                m["hold_ms"] = e.eventTimeMs - curDownEt; m["x1"] = e.x; m["y1"] = e.y; m["up"] = e.action
                audio.execute { runCatching { (mic as? edith.platform.generic.AudioRecordStream)?.record?.stop() } }
                presses += m; cur = null
                if (pr.key == "wear") {
                    if ((m["hold_ms"] as Long) >= 1000) confirmClass += mapOf("kind" to "raw_hold_ge_1s", "hold_ms" to m["hold_ms"], "pointers" to m["pointers_max"])
                } else {
                    pressesInPrompt++
                    if (pressesInPrompt >= pr.presses) ctx.view.postDelayed({ advance() }, 800)
                }
                update()
            }
        }
    }

    private fun measureAudio(m: MutableMap<String, Any?>, downEt: Long) {
        audio.execute {
            val s = mic ?: run { m["audio_error"] = "mic unavailable"; return@execute }
            try {
                val buf = ShortArray(320)
                s.start()
                var n = 0
                while (n == 0) n = s.read(buf, 0, buf.size)
                val lat = (SystemClock.uptimeMillis() - downEt).toDouble()
                if (n < 0) m["audio_error"] = "read=$n" else { m["down_to_first_frame_ms"] = lat; synchronized(latencies) { latencies += lat }; lastLatency = lat }
            } catch (t: Throwable) { m["audio_error"] = "${t.javaClass.simpleName}: ${t.message}" }
        }
    }

    override fun onGesture(e: GestureEvent): Boolean {
        if (phase != Phase.RUNNING) return false
        val pr = prompts[p]
        log(mapOf("k" to "gesture", "step" to pr.key, "t" to e.tMonoMs, "g" to e.gesture.wire, "src" to e.source, "raw" to e.raw))
        if (!isTemple(e)) { if (e.gesture == Gesture.TAP) advance(); return true }
        sdkSeen += e.gesture.wire
        cur?.let { m -> m["sdk"] = ((m["sdk"] as? List<*>) ?: emptyList<Any>()) + e.gesture.wire }
        if (pr.key == "wear" && e.gesture in CONFIRM_CLASS) confirmClass += mapOf("kind" to e.gesture.wire, "raw" to e.raw)
        return true
    }

    private fun advance() {
        if (phase != Phase.RUNNING) return
        p++; pressesInPrompt = 0
        if (p >= prompts.size) { complete(); return }
        if (prompts[p].key == "wear") { wearEndsAt = SystemClock.uptimeMillis() + wearS * 1000L; wearTick() }
        update()
    }

    private fun wearTick() {
        if (phase != Phase.RUNNING || prompts[p].key != "wear") return
        if (SystemClock.uptimeMillis() >= wearEndsAt) { result?.metrics?.set("wear_completed", true); advance(); return }
        ctx.view.postDelayed({ wearTick() }, 500)
    }

    private fun update() {
        val r = result ?: return
        val lat = synchronized(latencies) { latencies.toList() }
        r.metrics["presses"] = presses.map { it.toMap() }
        r.metrics["down_to_first_frame_ms_p50"] = Stats.percentile(lat, 50.0)
        r.metrics["down_to_first_frame_ms_p95"] = Stats.percentile(lat, 95.0)
        r.metrics["down_to_first_frame_ms_max"] = lat.maxOrNull()
        r.metrics["sdk_events_seen"] = sdkSeen.toList()
        r.metrics["wear_s"] = wearS
        r.metrics["wear_confirm_class_triggers"] = confirmClass.toList()
        r.metrics["raw_log"] = "t7_raw.jsonl"
        save()
    }

    private fun complete() {
        update()
        val r = result ?: return
        runCatching { rawLog?.close() }; rawLog = null
        audio.execute { runCatching { mic?.close() }; mic = null }
        val p95 = r.metrics["down_to_first_frame_ms_p95"] as Double?
        val gotDownUp = presses.any { it["hold_ms"] != null }
        r.metrics["got_down_up"] = gotDownUp
        p = prompts.lastIndex
        val wearDone = r.metrics["wear_completed"] == true
        finish(when {
            !gotDownUp || p95 == null || p95 > 100.0 || confirmClass.isNotEmpty() -> Status.FAIL
            !wearDone -> Status.MEASURED
            else -> Status.PASS
        })
    }

    override fun stop() { runCatching { rawLog?.close() }; audio.execute { runCatching { mic?.close() } }; audio.shutdown() }

    companion object {
        /** Gestures that could confirm or stop if the HUD mapped them (C106/D12 input FSM). */
        val CONFIRM_CLASS = setOf(Gesture.LONG_PRESS, Gesture.TWO_FINGER_LONG_PRESS, Gesture.TRIPLE_TAP, Gesture.TWO_FINGER_TAP)
    }
}
