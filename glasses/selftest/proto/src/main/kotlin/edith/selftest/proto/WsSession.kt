package edith.selftest.proto

import kotlinx.serialization.json.JsonObject
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import okio.ByteString.Companion.toByteString
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit

/**
 * A blocking wrapper over an OkHttp WebSocket: text messages are parsed to JSON and queued;
 * binary messages go to [onBinary] on OkHttp's reader thread.
 */
class WsSession(
    client: OkHttpClient,
    url: String,
    private val onBinary: (WsSession, ByteString) -> Unit = { _, _ -> },
) : AutoCloseable {
    private val inbox = LinkedBlockingQueue<JsonObject>()
    @Volatile var failure: Throwable? = null; private set
    @Volatile var closed = false; private set
    private val opened = java.util.concurrent.CountDownLatch(1)

    private val ws: WebSocket = client.newWebSocket(Request.Builder().url(url).build(), object : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) { opened.countDown() }
        override fun onMessage(webSocket: WebSocket, text: String) {
            try { inbox.put(J.parse(text)) } catch (t: Throwable) { failure = t }
        }
        override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
            try { onBinary(this@WsSession, bytes) } catch (t: Throwable) { failure = t }
        }
        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) { closed = true; webSocket.close(1000, null) }
        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) { closed = true }
        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            failure = t; closed = true; opened.countDown()
            inbox.put(J.obj("type" to "_failure", "error" to "${t.javaClass.simpleName}: ${t.message}", "http" to response?.code))
        }
    })

    /** Waits for the handshake; throws if it failed. */
    fun awaitOpen(timeoutMs: Long = 5000): WsSession {
        if (!opened.await(timeoutMs, TimeUnit.MILLISECONDS)) throw java.io.IOException("WS connect timeout")
        failure?.let { throw java.io.IOException("WS connect failed: ${it.message}", it) }
        return this
    }

    fun send(o: JsonObject): Boolean = ws.send(o.toString())
    fun send(bytes: ByteArray): Boolean = ws.send(bytes.toByteString())
    fun queueSize(): Long = ws.queueSize()

    /** Next text message of [type] (others are dropped), or null on timeout/failure. */
    fun await(type: String, timeoutMs: Long): JsonObject? {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (true) {
            val left = deadline - System.currentTimeMillis()
            if (left <= 0) return null
            val m = inbox.poll(left, TimeUnit.MILLISECONDS) ?: return null
            val t = J.type(m)
            if (t == type) return m
            if (t == "_failure" || t == "error") throw java.io.IOException("peer: ${m}")
        }
    }

    override fun close() { ws.close(1000, "bye") }
}
