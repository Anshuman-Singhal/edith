package edith.selftest.proto

import edith.platform.Stats
import okhttp3.OkHttpClient
import java.nio.ByteBuffer
import java.util.concurrent.ConcurrentLinkedQueue

/** Decodes one JPEG and returns (width, height); Android uses BitmapFactory, JVM tests ImageIO. */
fun interface JpegDecoder { fun decode(jpeg: ByteArray, off: Int, len: Int): Pair<Int, Int> }

/**
 * T13 inset client (SDK-free). The peer sends 320×240 JPEG at 15 fps, each binary message
 * `[0x0D][frame_id u32 BE][JPEG]`; for each frame we decode and echo
 * `{type:"t13.echo", frame_id, recv_to_decoded_ms}`. The peer computes RTT on its own clock
 * (no clocks compared) and returns `t13.result`; latency is defined in TESTS.md §T13.
 */
class T13Client(
    private val peer: PeerConfig,
    private val decoder: JpegDecoder,
    private val http: OkHttpClient = PeerConfig.client(),
    /** Called on the reader thread with each decoded frame (e.g. to show the inset). */
    private val onFrame: (frameId: Long, jpeg: ByteArray) -> Unit = { _, _ -> },
) {
    fun run(seconds: Double = 60.0, fps: Int = 15, width: Int = 320, height: Int = 240): Map<String, Any?> {
        val decodeMs = ConcurrentLinkedQueue<Double>()
        val ids = ConcurrentLinkedQueue<Long>()
        val decodeErrors = java.util.concurrent.atomic.AtomicInteger()
        val sizes = java.util.concurrent.atomic.AtomicReference<Pair<Int, Int>?>(null)
        val r = linkedMapOf<String, Any?>("peer" to peer.wsUrl, "seconds" to seconds, "fps" to fps, "width" to width, "height" to height)
        val ws = WsSession(http, peer.wsFor("t13")) { s, bytes ->
            val tRecv = nowMs()
            val b = bytes.toByteArray()
            if (b.size < 5 || b[0] != 0x0D.toByte()) return@WsSession
            val id = ByteBuffer.wrap(b, 1, 4).int.toLong() and 0xffffffffL
            var ok = true
            try { sizes.set(decoder.decode(b, 5, b.size - 5)) } catch (_: Throwable) { ok = false; decodeErrors.incrementAndGet() }
            val d = nowMs() - tRecv
            decodeMs += d; ids += id
            s.send(J.obj("type" to "t13.echo", "frame_id" to id, "recv_to_decoded_ms" to d, "ok" to ok))
            if (ok) try { onFrame(id, b.copyOfRange(5, b.size)) } catch (_: Throwable) {}
        }
        ws.use {
            it.awaitOpen(); it.await("hello", 5000)
            it.send(J.obj("type" to "t13.start", "fps" to fps, "width" to width, "height" to height, "seconds" to seconds))
            val res = it.await("t13.result", ((seconds + 20) * 1000).toLong())
            r["peer_result"] = res
            val d = decodeMs.toList()
            r["client_frames"] = d.size
            r["client_decode_ms_p50"] = Stats.percentile(d, 50.0)
            r["client_decode_ms_p95"] = Stats.percentile(d, 95.0)
            r["client_decode_errors"] = decodeErrors.get()
            r["decoded_size"] = sizes.get()?.let { (w, h) -> "${w}x$h" }
            val seen = ids.toSortedSet()
            r["client_gap_frames"] = if (seen.isEmpty()) null else (seen.last() - seen.first() + 1 - seen.size)
            if (res != null) {
                for (k in listOf("sent", "echoed", "dropped", "drop_pct", "rtt_ms_p50", "rtt_ms_p95", "rtt_ms_max",
                    "decode_ms_p50", "decode_ms_p95", "latency_ms_p50", "latency_ms_p95", "achieved_fps", "pass")) {
                    r[k] = res[k]
                }
            }
        }
        return r
    }

    companion object {
        const val LATENCY_P95_MAX_MS = 150.0
        const val DROP_PCT_MAX = 2.0
        const val DECODE_P95_MAX_MS = 10.0
    }
}
