package edith.selftest.tests

import android.os.SystemClock
import android.provider.Settings
import edith.platform.Gesture
import edith.platform.GestureEvent
import edith.platform.RawKey
import edith.platform.RawTouch
import edith.selftest.Screen
import edith.selftest.SelfTestActivity
import edith.selftest.proto.J
import edith.selftest.proto.Status
import java.io.File

/**
 * T6 touch: for each gesture, prompt 20 trials; count classified gestures (hits = equal to the
 * prompt). Logs every raw MotionEvent, KeyEvent and classified gesture to t6_raw.jsonl, records
 * keycodes and input devices seen, the raw x-direction of SLIDE FORWARD, and any system
 * "natural mode" settings found (the SDK says slide direction follows it).
 */
class T6Touch(ctx: SelfTestActivity) : Screen(ctx, "T6", "Touch") {
    private val prompts = listOf(
        Gesture.TAP to "TAP the temple once",
        Gesture.DOUBLE_TAP to "DOUBLE-TAP",
        Gesture.TRIPLE_TAP to "TRIPLE-TAP",
        Gesture.LONG_PRESS to "LONG-PRESS (hold ~1 s)",
        Gesture.SLIDE_FORWARD to "SLIDE FORWARD (toward your eyes/front)",
        Gesture.SLIDE_BACKWARD to "SLIDE BACK (toward your ear)",
        Gesture.SLIDE_UP to "SLIDE UP",
        Gesture.SLIDE_DOWN to "SLIDE DOWN",
        Gesture.TWO_FINGER_TAP to "TWO-FINGER TAP",
        Gesture.TWO_FINGER_LONG_PRESS to "TWO-FINGER HOLD (~1 s)",
    )
    private val trials get() = ctx.intExtra("t6_trials", 20).takeIf { it > 0 } ?: 20
    @Volatile private var p = 0
    private var hits = 0; private var detections = 0; private var lastEvent = 0L
    private val confusion = linkedMapOf<String, MutableMap<String, Int>>()
    private val summary = mutableListOf<Map<String, Any?>>()
    private var raw: java.io.Writer? = null
    private val keycodes = sortedSetOf<String>()
    private val devices = sortedSetOf<String>()
    private var downX: Float? = null
    private val slideDx = mutableListOf<Float>()

    override fun intro() = listOf(
        "10 gestures × $trials trials each. Do each one $trials times, at a normal pace.",
        "The screen advances by itself after $trials gestures (or 8 s idle).",
        "Stuck? Laptop: adb shell input keyevent ENTER skips a prompt.",
    )

    override fun status(): List<String> {
        if (phase == Phase.DONE) return listOf("Result: ${result?.status?.wire?.uppercase()}") +
            summary.map { "${it["gesture"]}: ${it["hits"]}/${it["trials"]}" }.chunked(2).map { it.joinToString("   ") } + listOf("TAP = next")
        val (g, text) = prompts[p]
        return listOf("Prompt ${p + 1}/${prompts.size}:", text, "", "hits $hits / $trials   detected $detections",
            "last: ${lastGesture ?: "-"}", "(gesture: ${g.wire})")
    }
    @Volatile private var lastGesture: String? = null

    override fun start() {
        val r = newResult()
        p = 0; hits = 0; detections = 0; summary.clear(); confusion.clear()
        raw = File(ctx.runDir, "t6_raw.jsonl").bufferedWriter()
        r.metrics["natural_mode_settings"] = naturalModeSettings()
        r.metrics["trials"] = trials
        lastEvent = SystemClock.uptimeMillis()
        tick()
    }

    private fun tick() {
        if (phase != Phase.RUNNING) return
        if (detections > 0 && SystemClock.uptimeMillis() - lastEvent > 8000) advance("idle")
        ctx.view.postDelayed({ tick() }, 500)
    }

    private fun log(o: Map<String, Any?>) { runCatching { raw?.write(J.of(o).toString() + "\n") } }

    override fun onRawTouch(e: RawTouch) {
        if (phase != Phase.RUNNING) return
        devices += "${e.deviceId}:${e.deviceName}:src=0x${e.source.toString(16)}"
        log(mapOf("k" to "touch", "prompt" to prompts[p].first.wire, "t" to e.tMonoMs, "et" to e.eventTimeMs, "a" to e.action,
            "n" to e.pointerCount, "x" to e.x, "y" to e.y, "dev" to e.deviceId))
        if (e.action == "ACTION_DOWN") downX = e.x
        if (e.action == "ACTION_UP" && prompts[p].first == Gesture.SLIDE_FORWARD) downX?.let { slideDx += e.x - it }
    }

    override fun onKey(e: RawKey) {
        if (phase != Phase.RUNNING) return
        keycodes += "${e.keyCode}:${e.keyName}:${e.deviceName}"
        log(mapOf("k" to "key", "prompt" to prompts[p].first.wire, "t" to e.tMonoMs, "a" to e.action, "code" to e.keyCode, "name" to e.keyName))
    }

    override fun onGesture(e: GestureEvent): Boolean {
        if (phase != Phase.RUNNING) return false
        log(mapOf("k" to "gesture", "prompt" to prompts[p].first.wire, "t" to e.tMonoMs, "g" to e.gesture.wire, "src" to e.source, "raw" to e.raw))
        if (!isTemple(e)) { if (e.gesture == Gesture.TAP) advance("skipped_by_key"); return true }
        if (!e.gesture.isClassified) return true
        lastEvent = SystemClock.uptimeMillis(); lastGesture = e.gesture.wire
        detections++
        val target = prompts[p].first
        if (e.gesture == target) hits++
        confusion.getOrPut(target.wire) { linkedMapOf() }.merge(e.gesture.wire, 1, Int::plus)
        if (detections >= trials) advance("complete")
        return true
    }

    private fun advance(why: String) {
        summary += mapOf("gesture" to prompts[p].first.wire, "trials" to trials, "detected" to detections, "hits" to hits, "end" to why)
        val r = result ?: return
        r.metrics["per_gesture"] = summary.toList(); r.metrics["confusion"] = confusion
        save()
        p++; hits = 0; detections = 0; lastEvent = SystemClock.uptimeMillis(); lastGesture = null
        if (p >= prompts.size) complete()
    }

    private fun complete() {
        val r = result ?: return
        runCatching { raw?.close() }; raw = null
        r.metrics["keycodes_seen"] = keycodes.toList()
        r.metrics["input_devices_seen"] = devices.toList()
        r.metrics["slide_forward_raw_dx"] = slideDx.toList()
        r.metrics["slide_forward_direction"] = when {
            slideDx.isEmpty() -> null; slideDx.count { it < 0 } > slideDx.size / 2 -> "x_decreasing"; else -> "x_increasing"
        }
        r.metrics["raw_log"] = "t6_raw.jsonl"
        val pass = summary.isNotEmpty() && summary.all { (it["hits"] as Int) >= trials - 1 }
        p = prompts.lastIndex
        finish(if (pass) Status.PASS else Status.FAIL)
    }

    override fun stop() { runCatching { raw?.close() } }

    /** Best effort: any system/secure/global setting whose name mentions natural/slide/touch/temple. */
    private fun naturalModeSettings(): Map<String, String> {
        val out = linkedMapOf<String, String>()
        for ((ns, uri) in listOf("system" to Settings.System.CONTENT_URI, "secure" to Settings.Secure.CONTENT_URI, "global" to Settings.Global.CONTENT_URI)) {
            runCatching {
                ctx.contentResolver.query(uri, arrayOf("name", "value"), null, null, null)?.use { c ->
                    while (c.moveToNext()) {
                        val n = c.getString(0) ?: continue
                        if (Regex("natural|slide|touch|temple|tp_|gesture", RegexOption.IGNORE_CASE).containsMatchIn(n)) out["$ns.$n"] = c.getString(1) ?: ""
                    }
                }
            }.onFailure { out["$ns.<error>"] = it.javaClass.simpleName }
        }
        return out
    }
}
