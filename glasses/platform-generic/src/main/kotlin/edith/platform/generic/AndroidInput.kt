package edith.platform.generic

import android.os.SystemClock
import android.view.GestureDetector
import android.view.InputDevice
import android.view.KeyEvent
import android.view.MotionEvent
import edith.platform.Gesture
import edith.platform.GestureEvent
import edith.platform.InputListener
import edith.platform.InputPort
import edith.platform.RawKey
import edith.platform.RawTouch
import android.content.Context

/** Converts Android input events to the SDK-free platform-api types. */
object AndroidEvents {
    fun touch(ev: MotionEvent): RawTouch = RawTouch(
        tMonoMs = SystemClock.uptimeMillis(),
        eventTimeMs = ev.eventTime,
        action = MotionEvent.actionToString(ev.actionMasked),
        pointerCount = ev.pointerCount,
        x = ev.x, y = ev.y,
        deviceId = ev.deviceId,
        source = ev.source,
        deviceName = deviceName(ev.deviceId),
    )

    fun key(ev: KeyEvent): RawKey = RawKey(
        tMonoMs = SystemClock.uptimeMillis(),
        action = if (ev.action == KeyEvent.ACTION_DOWN) "DOWN" else if (ev.action == KeyEvent.ACTION_UP) "UP" else ev.action.toString(),
        keyCode = ev.keyCode, keyName = KeyEvent.keyCodeToString(ev.keyCode), deviceName = deviceName(ev.deviceId),
    )

    fun deviceName(id: Int): String = try { InputDevice.getDevice(id)?.name ?: "?" } catch (_: Throwable) { "?" }

    /**
     * Keyboard / `adb shell input keyevent` fallback so the selftest is drivable even if the
     * temple gestures do not work (UNVERIFIED until T6). Key-sourced gestures never count as T6 hits.
     */
    fun keyGesture(ev: KeyEvent): GestureEvent? {
        if (ev.action != KeyEvent.ACTION_UP) return null
        val g = when (ev.keyCode) {
            KeyEvent.KEYCODE_ENTER, KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_SPACE -> Gesture.TAP
            KeyEvent.KEYCODE_DEL, KeyEvent.KEYCODE_ESCAPE, KeyEvent.KEYCODE_BACK -> Gesture.DOUBLE_TAP
            KeyEvent.KEYCODE_DPAD_RIGHT, KeyEvent.KEYCODE_TAB -> Gesture.SLIDE_FORWARD
            KeyEvent.KEYCODE_DPAD_LEFT -> Gesture.SLIDE_BACKWARD
            KeyEvent.KEYCODE_DPAD_UP -> Gesture.SLIDE_UP
            KeyEvent.KEYCODE_DPAD_DOWN -> Gesture.SLIDE_DOWN
            else -> return null
        }
        return GestureEvent(g, SystemClock.uptimeMillis(), "key", KeyEvent.keyCodeToString(ev.keyCode))
    }
}

/** An InputPort the host activity pushes events into. */
class DispatchingInput : InputPort, InputListener {
    @Volatile private var listener: InputListener? = null
    override fun setListener(listener: InputListener?) { this.listener = listener }
    override fun onGesture(event: GestureEvent) { listener?.onGesture(event) }
    override fun onRawTouch(event: RawTouch) { listener?.onRawTouch(event) }
    override fun onKey(event: RawKey) { listener?.onKey(event) }
}

/**
 * Phone/touchscreen gesture classifier for the generic platform (not for RayNeo, where the
 * Mercury SDK classifies). Tap counting uses a 300 ms window (C106).
 */
class GenericGestureClassifier(context: Context, private val emit: (GestureEvent) -> Unit) {
    private var taps = 0
    private var maxPointers = 1
    private val handler = android.os.Handler(android.os.Looper.getMainLooper())
    private val flushTaps = Runnable {
        val g = when (taps) { 1 -> Gesture.TAP; 2 -> Gesture.DOUBLE_TAP; 0 -> null; else -> Gesture.TRIPLE_TAP }
        taps = 0
        g?.let { emit(GestureEvent(it, SystemClock.uptimeMillis(), "generic", "taps")) }
    }
    private val detector = GestureDetector(context, object : GestureDetector.SimpleOnGestureListener() {
        override fun onDown(e: MotionEvent) = true
        override fun onSingleTapUp(e: MotionEvent): Boolean {
            if (maxPointers >= 2) return true
            taps++; handler.removeCallbacks(flushTaps); handler.postDelayed(flushTaps, 300); return true
        }
        override fun onLongPress(e: MotionEvent) {
            emit(GestureEvent(if (maxPointers >= 2) Gesture.TWO_FINGER_LONG_PRESS else Gesture.LONG_PRESS, SystemClock.uptimeMillis(), "generic", "long"))
        }
        override fun onFling(e1: MotionEvent?, e2: MotionEvent, vx: Float, vy: Float): Boolean {
            val g = if (kotlin.math.abs(vx) >= kotlin.math.abs(vy)) {
                if (vx < 0) Gesture.SLIDE_FORWARD else Gesture.SLIDE_BACKWARD
            } else if (vy < 0) Gesture.SLIDE_UP else Gesture.SLIDE_DOWN
            emit(GestureEvent(g, SystemClock.uptimeMillis(), "generic", "fling vx=$vx vy=$vy")); return true
        }
    }).apply { setIsLongpressEnabled(true) }

    fun onTouch(ev: MotionEvent) {
        if (ev.actionMasked == MotionEvent.ACTION_DOWN) {
            maxPointers = 1
            emit(GestureEvent(Gesture.ACTION_DOWN, SystemClock.uptimeMillis(), "generic", "down"))
        }
        maxPointers = maxOf(maxPointers, ev.pointerCount)
        detector.onTouchEvent(ev)
        if (ev.actionMasked == MotionEvent.ACTION_UP) {
            emit(GestureEvent(Gesture.ACTION_UP, SystemClock.uptimeMillis(), "generic", "up"))
            if (maxPointers >= 2 && ev.eventTime - ev.downTime < 400) {
                emit(GestureEvent(Gesture.TWO_FINGER_TAP, SystemClock.uptimeMillis(), "generic", "two"))
            }
        }
    }
}
