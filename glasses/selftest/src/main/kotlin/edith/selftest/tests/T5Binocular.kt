package edith.selftest.tests

import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import edith.platform.Gesture
import edith.platform.GestureEvent
import edith.platform.Stats
import edith.selftest.Screen
import edith.selftest.SelfTestActivity
import edith.selftest.proto.Status

/**
 * T5 binocular: L/R test patterns with a 40 px grid, a 5% safe-area box, corner marks, a
 * circle-aspect check, L-only / R-only glyphs, and a right-eye horizontal offset (SLIDE fwd/back,
 * ±10 px). Then four yes/no questions (TAP = yes, 2×TAP = no). Records the window/display found
 * at runtime and frame times (FrameMetrics); `bringup.sh` adds `wm size` and `gfxinfo`.
 */
class T5Binocular(ctx: SelfTestActivity) : Screen(ctx, "T5", "Binocular") {
    private val questions = listOf(
        "fused" to "ONE fused image, no double vision?",
        "circle_round" to "Is the circle ROUND (not squashed)?",
        "corners_visible" to "All 4 red corner marks visible?",
        "eye_glyphs" to "Close each eye: L only in LEFT, R only in RIGHT?",
    )
    @Volatile private var offset = 0
    @Volatile private var q = -1 // -1: looking at the pattern
    private var frameStart = 0
    private val grid = Paint().apply { color = Color.rgb(70, 70, 70); strokeWidth = 1f }

    override fun intro() = listOf(
        "Shows a test pattern in each eye.",
        "SLIDE fwd/back moves the RIGHT eye ±1 px (max ±10) until the images fuse.",
        "Then TAP, and answer 4 questions: TAP = yes, 2×TAP = no.",
    )

    override fun status() = if (phase == Phase.DONE) listOf(
        "Result: ${result?.status?.wire?.uppercase()}",
        "Answers: ${result?.operator}",
        "Right-eye offset: $offset px",
        "Janky frames: ${result?.metrics?.get("janky_pct")}%",
        "TAP = next",
    ) else emptyList()

    override fun start() {
        val r = newResult()
        frameStart = ctx.frameMs.size
        ctx.recordDisplay()
        r.metrics["display"] = ctx.results.display
        q = -1; offset = 0
        save()
    }

    override fun onGesture(e: GestureEvent): Boolean {
        if (phase != Phase.RUNNING) return false
        if (q < 0) {
            when (e.gesture) {
                Gesture.SLIDE_FORWARD -> { offset = (offset + 1).coerceAtMost(10); return true }
                Gesture.SLIDE_BACKWARD -> { offset = (offset - 1).coerceAtLeast(-10); return true }
                Gesture.TAP -> { q = 0; return true }
                Gesture.DOUBLE_TAP -> return true
                else -> return false
            }
        }
        val yes = when (e.gesture) { Gesture.TAP -> true; Gesture.DOUBLE_TAP -> false; else -> return true }
        result?.operator?.set(questions[q].first, yes)
        q++
        if (q >= questions.size) complete()
        return true
    }

    private fun complete() {
        val r = result ?: return
        val frames = ctx.frameMs.toList().drop(frameStart.coerceAtMost(ctx.frameMs.size))
        r.metrics["right_eye_offset_px"] = offset
        r.metrics["frames"] = frames.size
        r.metrics["frame_ms_p50"] = Stats.percentile(frames, 50.0)
        r.metrics["frame_ms_p95"] = Stats.percentile(frames, 95.0)
        // 30 fps budget = 33.3 ms; gfxinfo from bringup.sh is the authoritative janky count.
        val janky = if (frames.isEmpty()) null else 100.0 * frames.count { it > 33.3 } / frames.size
        r.metrics["janky_pct"] = janky
        r.metrics["janky_definition"] = "FrameMetrics TOTAL_DURATION > 33.3 ms (30 fps budget)"
        val allYes = questions.all { r.operator[it.first] == true }
        finish(if (allYes && (janky ?: 0.0) <= 5.0) Status.PASS else Status.FAIL)
    }

    override fun drawEye(c: Canvas, w: Int, h: Int, eye: Int): Boolean {
        if (phase != Phase.RUNNING) return false
        val u = ctx.ui
        c.save()
        if (eye == 1) c.translate(offset.toFloat(), 0f)
        var x = 0f; while (x <= w) { c.drawLine(x, 0f, x, h.toFloat(), grid); x += 40f }
        var y = 0f; while (y <= h) { c.drawLine(0f, y, w.toFloat(), y, grid); y += 40f }
        val sx = w * 0.05f; val sy = h * 0.05f
        u.stroke.color = u.accent; c.drawRect(sx, sy, w - sx, h - sy, u.stroke)
        u.stroke.color = u.bad
        val m = 30f
        for ((cx, cy, dx, dy) in listOf(listOf(1f, 1f, 1f, 1f), listOf(w - 1f, 1f, -1f, 1f), listOf(1f, h - 1f, 1f, -1f), listOf(w - 1f, h - 1f, -1f, -1f))) {
            c.drawLine(cx, cy, cx + dx * m, cy, u.stroke); c.drawLine(cx, cy, cx, cy + dy * m, u.stroke)
        }
        val r = minOf(w, h) * 0.3f
        u.stroke.color = Color.WHITE; c.drawCircle(w / 2f, h / 2f, r, u.stroke)
        c.drawLine(w / 2f - 20, h / 2f, w / 2f + 20, h / 2f, u.stroke); c.drawLine(w / 2f, h / 2f - 20, w / 2f, h / 2f + 20, u.stroke)
        u.title.color = u.warn
        if (eye == 0) c.drawText("L", w * 0.12f, h / 2f + 12, u.title) else c.drawText("R", w * 0.84f, h / 2f + 12, u.title)
        u.title.color = Color.WHITE
        c.restore()
        val l = ctx.layout()
        val lines = mutableListOf("${l.mode.wire.uppercase()} ${l.eyeWidth}x${l.eyeHeight}/eye  window ${ctx.view.width}x${ctx.view.height}  R-offset $offset px")
        lines += if (q < 0) "SLIDE fwd/back = R-eye offset · TAP = done" else "Q${q + 1}/4: ${questions[q].second}  TAP=yes 2×TAP=no"
        u.lines(c, sx + 8, sy, w - 2 * sx - 16, lines, u.mono, u.warn)
        return true
    }
}
