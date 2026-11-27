package edith.selftest.tests

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.RectF
import android.media.MediaCodecList
import edith.selftest.Screen
import edith.selftest.SelfTestActivity
import edith.selftest.proto.JpegDecoder
import edith.selftest.proto.Status
import edith.selftest.proto.T13Client
import java.util.concurrent.atomic.AtomicReference

/** T13 inset: decode the peer's 320×240 JPEG at 15 fps, echo, show it; list H.264 codecs. */
class T13Inset(ctx: SelfTestActivity) : Screen(ctx, "T13", "Inset") {
    private val latest = AtomicReference<Bitmap?>(null)

    override fun intro() = listOf("The laptop streams 320×240 JPEG at 15 fps for ${ctx.intExtra("t13_s", 60)} s; each frame is decoded and echoed.",
        "Pass: latency p95 ≤150 ms, drops <2%, decode p95 <10 ms.",
        "Peer: " + (ctx.peer?.wsUrl ?: "NONE — provision with --es peer"))

    override fun status() = result?.let { r ->
        listOf(if (phase == Phase.DONE) "Result: ${r.status.wire.uppercase()}" else "Streaming…",
            "latency p95 ${r.metrics["latency_ms_p95"] ?: "-"} ms   drop ${r.metrics["drop_pct"] ?: "-"}%",
            "decode p95 ${r.metrics["decode_ms_p95"] ?: r.metrics["client_decode_ms_p95"] ?: "-"} ms") +
            if (phase == Phase.DONE) listOf("TAP = next") else emptyList()
    } ?: emptyList()

    override fun drawEye(c: Canvas, w: Int, h: Int, eye: Int): Boolean {
        if (phase != Phase.RUNNING) return false
        val b = latest.get() ?: return false
        val u = ctx.ui
        val dw = w * 0.5f; val dh = dw * 0.75f
        c.drawBitmap(b, null, RectF(w - dw - 16, 16f, w - 16f, 16 + dh), null)
        u.lines(c, 16f, 16 + dh, w - 32f, status(), u.body)
        return true
    }

    override fun start() {
        val r = newResult()
        r.metrics["h264_decoders"] = runCatching {
            MediaCodecList(MediaCodecList.ALL_CODECS).codecInfos.filter { !it.isEncoder && it.supportedTypes.any { t -> t.equals("video/avc", true) } }
                .map { "${it.name}${if (it.isHardwareAccelerated) " (hw)" else ""}" }
        }.getOrElse { listOf("error: ${it.message}") }
        val peer = ctx.peer ?: run { r.errors += "no peer provisioned (--es peer ws://<ip>:7400/v1/selftest)"; finish(Status.SKIPPED); return }
        save()
        val decoder = JpegDecoder { b, off, len ->
            val bmp = BitmapFactory.decodeByteArray(b, off, len) ?: error("decode failed")
            latest.set(bmp)
            bmp.width to bmp.height
        }
        background("run") {
            r.metrics.putAll(T13Client(peer, decoder).run(seconds = ctx.intExtra("t13_s", 60).toDouble()))
            finish(if (r.metrics["pass"] == true) Status.PASS else Status.FAIL)
        }
    }

    /** Continuous inset stream for T14 full-load mode. */
    fun loadStream(stopFlag: () -> Boolean) {
        val peer = ctx.peer ?: return
        val decoder = JpegDecoder { b, off, len -> val bmp = BitmapFactory.decodeByteArray(b, off, len); bmp.width to bmp.height }
        while (!stopFlag()) runCatching { T13Client(peer, decoder).run(seconds = 30.0) }
    }
}
