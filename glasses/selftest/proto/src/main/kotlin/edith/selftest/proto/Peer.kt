package edith.selftest.proto

import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit

/**
 * Where `./edith glasses selftest --serve` listens, from the provisioning extras
 * (`--es peer ws://<ip>:7400/v1/selftest --es token <t>`). Wire protocol: docs/bringup/PROTOCOL.md.
 */
data class PeerConfig(val wsUrl: String, val token: String?) {
    private val http: HttpUrl = requireNotNull(
        wsUrl.replaceFirst(Regex("^ws", RegexOption.IGNORE_CASE), "http").toHttpUrlOrNull()
    ) { "bad peer url: $wsUrl" }

    /** WebSocket URL for one test (`?test=t13&token=...`). */
    fun wsFor(test: String): String {
        val b = http.newBuilder().addQueryParameter("test", test)
        token?.let { b.addQueryParameter("token", it) }
        return b.build().toString().replaceFirst("http", "ws")
    }

    /** HTTP URL under the peer path, e.g. `httpFor("t11/down", "bytes" to "1000")`. */
    fun httpFor(sub: String, vararg q: Pair<String, String>): HttpUrl {
        val b = http.newBuilder()
        sub.split('/').filter { it.isNotEmpty() }.forEach { b.addPathSegment(it) }
        q.forEach { (k, v) -> b.addQueryParameter(k, v) }
        token?.let { b.addQueryParameter("token", it) }
        return b.build()
    }

    companion object {
        fun parse(peer: String?, token: String?): PeerConfig? =
            peer?.trim()?.takeIf { it.isNotEmpty() }?.let { PeerConfig(it, token?.takeIf { t -> t.isNotEmpty() }) }

        fun client(): OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(5, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .pingInterval(0, TimeUnit.SECONDS)
            .build()
    }
}

/** Monotonic milliseconds as a double (System.nanoTime based; same clock on JVM and Android). */
internal fun nowMs(): Double = System.nanoTime() / 1e6
