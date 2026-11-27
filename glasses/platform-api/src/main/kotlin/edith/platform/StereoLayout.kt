package edith.platform

/** A pixel rectangle; [right]/[bottom] are exclusive. */
data class Rect(val left: Int, val top: Int, val right: Int, val bottom: Int) {
    val width: Int get() = right - left
    val height: Int get() = bottom - top
}

/**
 * How the logical window maps to the eyes. The RayNeo X3 Pro is assumed to present a
 * side-by-side 1280×480 logical display (640×480 per eye) — UNVERIFIED until T5, so the selftest
 * detects the mode at runtime from the window size and shows what it found.
 */
data class StereoLayout(val mode: Mode, val left: Rect, val right: Rect?) {
    enum class Mode(val wire: String) { SBS("sbs"), MONO("mono") }

    val eyeWidth: Int get() = left.width
    val eyeHeight: Int get() = left.height

    companion object {
        /** Aspect ratio at or above which the window is treated as two side-by-side eyes (1280×480 = 2.67; 21:9 phones = 2.33). */
        const val SBS_MIN_ASPECT = 2.5

        fun detect(widthPx: Int, heightPx: Int, forceMode: Mode? = null): StereoLayout {
            require(widthPx > 0 && heightPx > 0) { "bad window $widthPx x $heightPx" }
            val sbs = when (forceMode) {
                Mode.SBS -> true
                Mode.MONO -> false
                null -> widthPx.toDouble() / heightPx >= SBS_MIN_ASPECT
            }
            return if (sbs) {
                val half = widthPx / 2
                StereoLayout(Mode.SBS, Rect(0, 0, half, heightPx), Rect(half, 0, half * 2, heightPx))
            } else {
                StereoLayout(Mode.MONO, Rect(0, 0, widthPx, heightPx), null)
            }
        }
    }
}
