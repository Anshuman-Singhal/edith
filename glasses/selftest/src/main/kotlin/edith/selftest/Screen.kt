package edith.selftest

import android.graphics.Canvas
import edith.platform.Gesture
import edith.platform.GestureEvent
import edith.platform.RawKey
import edith.platform.RawTouch
import edith.selftest.proto.Status
import edith.selftest.proto.TestResult

/**
 * One screen of the selftest. Navigation (in [SelfTestActivity]): TAP = start / next,
 * DOUBLE-TAP = back, SLIDE FORWARD = skip to next, SLIDE BACK = previous — unless the screen
 * consumes the gesture (T5 offset and questions, T6/T7 trials). Keys (adb `input keyevent`):
 * ENTER = tap, DEL = double-tap, DPAD_RIGHT/LEFT = slide forward/back.
 */
abstract class Screen(val ctx: SelfTestActivity, val id: String, val title: String) {
    enum class Phase { IDLE, RUNNING, DONE }
    @Volatile var phase = Phase.IDLE
    var result: TestResult? = null

    /** Lines shown while IDLE (what the test does, what to do). */
    open fun intro(): List<String> = emptyList()
    /** Lines shown while RUNNING / DONE. */
    open fun status(): List<String> = emptyList()
    /** Draw custom content into one eye (0 = left); default: text only. Return true if handled. */
    open fun drawEye(c: Canvas, w: Int, h: Int, eye: Int): Boolean = false
    open fun onGesture(e: GestureEvent): Boolean = false
    open fun onRawTouch(e: RawTouch) {}
    open fun onKey(e: RawKey) {}
    open fun start() {}
    open fun stop() {}

    fun newResult(): TestResult {
        val r = TestResult(id, title)
        r.passCriterion = ctx.registry.firstOrNull { it.id == id }?.pass
        result = r; ctx.results.put(r)
        return r
    }

    fun save() { result?.let { ctx.results.put(it) } }

    fun finish(s: Status) {
        result?.let { it.finish(s); ctx.results.put(it) }
        phase = Phase.DONE
    }

    /** Runs [block] on a worker thread; exceptions become errors on the result. */
    fun background(name: String, block: () -> Unit) {
        Thread({
            try { block() } catch (t: Throwable) {
                result?.error(name, t); if (phase != Phase.DONE) finish(Status.ERROR)
            }
        }, "selftest-$id-$name").apply { isDaemon = true; start() }
    }

    protected fun isTemple(e: GestureEvent) = e.source != "key"
    protected fun isNav(e: GestureEvent, g: Gesture) = e.gesture == g
}

/** A static information screen (intro / summary). */
class InfoScreen(ctx: SelfTestActivity, id: String, title: String, private val body: () -> List<String>) : Screen(ctx, id, title) {
    override fun intro() = body()
    override fun status() = body()
}
