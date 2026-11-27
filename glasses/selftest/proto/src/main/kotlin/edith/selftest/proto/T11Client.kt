package edith.selftest.proto

import edith.platform.Stats
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okio.BufferedSink

/** T11 Wi-Fi client (SDK-free): HTTP down/up throughput and WS ping RTT against the peer. */
class T11Client(private val peer: PeerConfig, private val http: OkHttpClient = PeerConfig.client()) {
    fun run(bytes: Long = 8L shl 20, pings: Int = 50): Map<String, Any?> {
        val r = linkedMapOf<String, Any?>("peer" to peer.wsUrl, "bytes" to bytes)
        val errors = mutableListOf<String>()
        try {
            val t0 = nowMs()
            http.newCall(Request.Builder().url(peer.httpFor("t11/down", "bytes" to bytes.toString())).build()).execute().use { resp ->
                check(resp.isSuccessful) { "down HTTP ${resp.code}" }
                val src = resp.body!!.source(); var n = 0L; val buf = okio.Buffer()
                while (true) { val k = src.read(buf, 1 shl 16); if (k < 0) break; n += k; buf.clear() }
                val s = (nowMs() - t0) / 1000.0
                r["down_bytes"] = n; r["down_mbit_s"] = n * 8 / 1e6 / s
            }
        } catch (t: Throwable) { errors += "down: ${t.message}" }
        try {
            val body = object : RequestBody() {
                override fun contentType() = "application/octet-stream".toMediaType()
                override fun contentLength() = bytes
                override fun writeTo(sink: BufferedSink) {
                    val chunk = ByteArray(1 shl 16); var left = bytes
                    while (left > 0) { val k = minOf(left, chunk.size.toLong()).toInt(); sink.write(chunk, 0, k); left -= k }
                }
            }
            val t0 = nowMs()
            http.newCall(Request.Builder().url(peer.httpFor("t11/up")).post(body).build()).execute().use { resp ->
                check(resp.isSuccessful) { "up HTTP ${resp.code}" }
                val s = (nowMs() - t0) / 1000.0
                r["up_bytes"] = bytes; r["up_mbit_s"] = bytes * 8 / 1e6 / s
                r["up_peer"] = resp.body?.string()?.let { J.parse(it) }
            }
        } catch (t: Throwable) { errors += "up: ${t.message}" }
        try {
            WsSession(http, peer.wsFor("t11")).use { ws ->
                ws.awaitOpen(); ws.await("hello", 5000)
                val rtts = mutableListOf<Double>()
                for (i in 0 until pings) {
                    val t0 = nowMs()
                    ws.send(J.obj("type" to "t11.ping", "seq" to i))
                    if (ws.await("t11.pong", 2000) != null) rtts += nowMs() - t0
                }
                r["pings"] = pings; r["pongs"] = rtts.size
                r["rtt_ms_p50"] = Stats.percentile(rtts, 50.0); r["rtt_ms_p95"] = Stats.percentile(rtts, 95.0)
            }
        } catch (t: Throwable) { errors += "rtt: ${t.message}" }
        r["errors"] = errors
        return r
    }
}
