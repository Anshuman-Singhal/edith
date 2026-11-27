package edith.platform

/** Small, dependency-free statistics used by the selftest results. */
object Stats {
    /** Nearest-rank percentile (p in 0..100); null for an empty list. */
    fun percentile(values: Collection<Double>, p: Double): Double? {
        if (values.isEmpty()) return null
        val s = values.sorted()
        val rank = kotlin.math.ceil(p / 100.0 * s.size).toInt().coerceIn(1, s.size)
        return s[rank - 1]
    }

    fun mean(values: Collection<Double>): Double? = if (values.isEmpty()) null else values.sum() / values.size

    /** RMS level of 16-bit PCM in dBFS (full-scale sine ≈ -3 dBFS); -120 for silence. */
    fun rmsDbfs(samples: ShortArray, len: Int = samples.size): Double {
        if (len <= 0) return -120.0
        var acc = 0.0
        for (i in 0 until len) { val v = samples[i] / 32768.0; acc += v * v }
        val rms = kotlin.math.sqrt(acc / len)
        return if (rms <= 1e-6) -120.0 else 20 * kotlin.math.log10(rms)
    }
}
