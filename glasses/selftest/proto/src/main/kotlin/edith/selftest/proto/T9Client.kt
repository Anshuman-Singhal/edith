package edith.selftest.proto

import edith.platform.PcmStream
import okhttp3.OkHttpClient
import java.io.File

/** One T9 capture segment. */
data class T9Segment(val name: String, val source: String, val seconds: Double, val instruction: String)

object T9Plan {
    const val RATE = 16000
    const val CHANNELS = 1

    /**
     * TESTS.md T9: 10 s in each stock source (and each RayNeo mode once known; UNVERIFIED),
     * then wearer vs bystander-at-1-m on VOICE_RECOGNITION, then the 20-command read.
     */
    fun default(sources: List<String>, perSourceS: Double = 10.0, commandsS: Double = 60.0): List<T9Segment> =
        sources.map { T9Segment("src_$it", it, perSourceS, "Speak normally: count from one to ten") } +
            listOf(
                T9Segment("wearer", "VOICE_RECOGNITION", 10.0, "WEARER: read the sentence on the card. Bystander silent."),
                T9Segment("bystander", "VOICE_RECOGNITION", 10.0, "WEARER SILENT. Bystander at 1 m reads the same sentence."),
                T9Segment("commands", "VOICE_RECOGNITION", commandsS, "WEARER: read the 20 commands on the card."),
            )
}

/**
 * T9 mic client (SDK-free, R4 nit 2). For each segment it opens the source through [open],
 * streams 16 kHz PCM to `selftest --serve` (which writes WAVs into runs/bringup/<ts>/), and
 * optionally also writes a local WAV into [localDir]. Works without a peer (local only).
 * Every failure is recorded per segment; the run continues.
 */
class T9Client(
    private val peer: PeerConfig?,
    private val http: OkHttpClient = PeerConfig.client(),
    private val localDir: File? = null,
    private val onSegment: (T9Segment, Int, Int) -> Unit = { _, _, _ -> },
) {
    fun run(segments: List<T9Segment>, open: (source: String, rate: Int, channels: Int) -> PcmStream): Map<String, Any?> {
        val out = mutableListOf<Map<String, Any?>>()
        val errors = mutableListOf<String>()
        var ws: WsSession? = null
        if (peer != null) {
            try { ws = WsSession(http, peer.wsFor("t9")).awaitOpen(); ws.await("hello", 5000) }
            catch (t: Throwable) { errors += "peer: ${t.message}"; ws = null }
        }
        try {
            segments.forEachIndexed { i, seg ->
                onSegment(seg, i, segments.size)
                out += runSegment(seg, ws, open)
            }
            ws?.send(J.obj("type" to "bye"))
        } finally { ws?.close() }

        val byName = out.associateBy { it["segment"] as String }
        val wearer = byName["wearer"]?.get("rms_dbfs") as? Double
        val bystander = byName["bystander"]?.get("rms_dbfs") as? Double
        return linkedMapOf(
            "peer" to (peer?.wsUrl), "peer_connected" to (ws != null),
            "segments" to out,
            "wearer_minus_bystander_db" to if (wearer != null && bystander != null) wearer - bystander else null,
            "errors" to errors,
        )
    }

    private fun runSegment(seg: T9Segment, ws: WsSession?, open: (String, Int, Int) -> PcmStream): Map<String, Any?> {
        val r = linkedMapOf<String, Any?>("segment" to seg.name, "source" to seg.source, "seconds" to seg.seconds,
            "requested_rate" to T9Plan.RATE, "requested_channels" to T9Plan.CHANNELS)
        var stream: PcmStream? = null
        var wav: WavWriter? = null
        try {
            stream = open(seg.source, T9Plan.RATE, T9Plan.CHANNELS)
            r["actual_rate"] = stream.actualRate; r["actual_channels"] = stream.actualChannels
            r["rate_ok"] = stream.actualRate == T9Plan.RATE && stream.actualChannels == T9Plan.CHANNELS
            ws?.send(J.obj("type" to "t9.start", "segment" to seg.name, "source" to seg.source,
                "rate" to stream.actualRate, "channels" to stream.actualChannels))
            localDir?.let { it.mkdirs(); wav = WavWriter(File(it, "t9_${seg.name}.wav"), stream.actualRate, stream.actualChannels) }
            val total = (seg.seconds * stream.actualRate * stream.actualChannels).toLong()
            val chunk = ShortArray((stream.actualRate / 50) * stream.actualChannels) // 20 ms
            val tStart = stream.start()
            var got = 0L; var firstFrameMs: Double? = null
            var acc = 0.0; var peak = 0
            while (got < total) {
                val n = stream.read(chunk, 0, minOf(chunk.size.toLong(), total - got).toInt())
                if (n < 0) throw java.io.IOException("read returned $n")
                if (n == 0) continue
                if (firstFrameMs == null) firstFrameMs = nowMs() - tStart
                for (k in 0 until n) { val v = chunk[k].toInt(); acc += v.toDouble() * v; if (kotlin.math.abs(v) > peak) peak = kotlin.math.abs(v) }
                wav?.write(chunk, 0, n)
                ws?.send(pcmBytes(chunk, 0, n))
                got += n
            }
            r["samples"] = got
            r["start_to_first_frame_ms"] = firstFrameMs
            val rms = if (got > 0) kotlin.math.sqrt(acc / got) / 32768.0 else 0.0
            r["rms_dbfs"] = if (rms <= 1e-6) -120.0 else 20 * kotlin.math.log10(rms)
            r["peak"] = peak
            if (ws != null) {
                ws.send(J.obj("type" to "t9.end", "segment" to seg.name, "samples" to got))
                val saved = ws.await("t9.saved", 10_000)
                r["peer_saved"] = saved?.let { J.str(it, "path") }
                r["peer_samples"] = saved?.let { J.num(it, "samples")?.toLong() }
            }
        } catch (t: Throwable) {
            r["error"] = "${t.javaClass.simpleName}: ${t.message}"
        } finally {
            try { wav?.close() } catch (_: Throwable) {}
            try { stream?.close() } catch (_: Throwable) {}
        }
        return r
    }

    companion object {
        /** Stock Android AudioSource names (MediaRecorder.AudioSource) tried by the generic platform. */
        val STOCK_SOURCES = listOf("DEFAULT", "MIC", "VOICE_RECOGNITION", "VOICE_COMMUNICATION", "CAMCORDER", "UNPROCESSED", "VOICE_PERFORMANCE")
    }
}
