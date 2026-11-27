package edith.platform

/**
 * The glasses platform seam (PLAN §3.8). Implementations: `platform-generic` (AOSP phone or any
 * Android device) and `platform-rayneo` (RayNeo X3 Pro via the Mercury SDK, the only module
 * that imports `com.ffalcon.*`). Everything device-specific is UNVERIFIED until bring-up (T0–T18).
 * This module is pure Kotlin/JVM: no Android types, so it is unit-testable on any JVM.
 */
interface GlassesPlatform {
    val display: DisplayPort
    val input: InputPort
    val mic: MicPort
    val pose: PosePort
    val camera: CameraPort
    val power: PowerPort
    val info: InfoPort
}

/** Display geometry discovered at runtime (T5). */
interface DisplayPort {
    fun info(): DisplayInfo
    /** 0..1, or a negative value to follow the system setting. */
    fun setBrightness(level: Float)
}

data class DisplayInfo(
    val widthPx: Int,
    val heightPx: Int,
    val densityDpi: Int,
    val refreshHz: Float,
    val layout: StereoLayout,
    /** Free-form facts (display ids, modes, HDR caps...), recorded verbatim into results. */
    val extra: Map<String, String> = emptyMap(),
)

/** Temple touchpad and other inputs (T6/T7). */
interface InputPort {
    fun setListener(listener: InputListener?)
}

interface InputListener {
    /** A classified gesture (from the vendor SDK on RayNeo, or our detector on generic). */
    fun onGesture(event: GestureEvent) {}
    /** Every raw touch event, before any classification. */
    fun onRawTouch(event: RawTouch) {}
    /** Raw key events (the temple or a BT HID key may arrive as keycodes; UNVERIFIED). */
    fun onKey(event: RawKey) {}
}

enum class Gesture(val wire: String) {
    TAP("tap"), DOUBLE_TAP("double_tap"), TRIPLE_TAP("triple_tap"), LONG_PRESS("long_press"),
    SLIDE_FORWARD("slide_forward"), SLIDE_BACKWARD("slide_backward"),
    SLIDE_UP("slide_up"), SLIDE_DOWN("slide_down"),
    TWO_FINGER_TAP("two_finger_tap"), TWO_FINGER_LONG_PRESS("two_finger_long_press"),
    ACTION_DOWN("action_down"), ACTION_UP("action_up"), OTHER("other");

    /** Gestures that a classifier reports as a completed trial (not DOWN/UP markers). */
    val isClassified: Boolean get() = this != ACTION_DOWN && this != ACTION_UP && this != OTHER

    companion object {
        fun fromWire(s: String): Gesture? = entries.firstOrNull { it.wire == s || it.name == s.uppercase() }
    }
}

/** [tMonoMs] is a monotonic clock in ms (Android: SystemClock.uptimeMillis). */
data class GestureEvent(val gesture: Gesture, val tMonoMs: Long, val source: String, val raw: String)

data class RawTouch(
    val tMonoMs: Long,
    /** Event time from the input system (uptime ms); dispatch delay = tMonoMs - eventTimeMs. */
    val eventTimeMs: Long,
    val action: String,
    val pointerCount: Int,
    val x: Float,
    val y: Float,
    val deviceId: Int,
    val source: Int,
    val deviceName: String,
)

data class RawKey(val tMonoMs: Long, val action: String, val keyCode: Int, val keyName: String, val deviceName: String)

/** Microphone (T7/T9). */
interface MicPort {
    /** Stock AudioSource names this platform will try, in order (plus vendor modes if known). */
    fun sources(): List<String>
    fun open(source: String, sampleRate: Int, channels: Int): PcmStream
}

/** A blocking 16-bit PCM stream. Implementations: AudioRecord (Android), synthetic (tests). */
interface PcmStream : AutoCloseable {
    val source: String
    val requestedRate: Int
    val requestedChannels: Int
    val actualRate: Int
    val actualChannels: Int
    /** Starts capture; returns a monotonic ms timestamp. */
    fun start(): Long
    /** Blocking read of interleaved samples; returns the count read (<0 on error). */
    fun read(buf: ShortArray, off: Int, len: Int): Int
    override fun close()
}

/** Orientation sensors (T8, D13b). */
interface PosePort {
    fun sensors(): List<Map<String, String>>
}

/** Camera enumeration (T10, D13b). */
interface CameraPort {
    fun enumerate(): List<Map<String, String>>
}

/** Battery and thermal (T14/T15). */
interface PowerPort {
    fun sample(): PowerSample
}

data class PowerSample(
    val tWallMs: Long,
    val levelPct: Int?,
    val status: String?,
    val plugged: String?,
    val temperatureC: Double?,
    val voltageMv: Int?,
    /** BatteryManager.BATTERY_PROPERTY_CURRENT_NOW; sign and units UNVERIFIED (T18). */
    val currentNowUa: Long?,
    val currentAvgUa: Long?,
    val chargeCounterUah: Long?,
    val energyNwh: Long?,
    val thermalStatus: String?,
    val thermalHeadroom: Float?,
)

/** Device identity (T0). */
interface InfoPort {
    val platformName: String
    fun identity(): Map<String, String>
}
