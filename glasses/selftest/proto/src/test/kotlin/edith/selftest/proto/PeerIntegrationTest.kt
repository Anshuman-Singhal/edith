package edith.selftest.proto

import edith.platform.PcmStream
import kotlinx.serialization.json.JsonObject
import org.junit.AfterClass
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.BeforeClass
import org.junit.Test
import java.io.File
import java.nio.file.Files
import java.util.concurrent.TimeUnit
import javax.imageio.ImageIO

/**
 * D13a acceptance (C104, R4 nits 1–2): the SDK-free T13 and T9 (and T11) clients run against
 * `./edith glasses selftest --serve` on localhost on a free port, and the result JSON they produce
 * validates against docs/bringup/results.schema.json.
 */
class PeerIntegrationTest {
    companion object {
        private val root = File(System.getProperty("edith.repoRoot") ?: "../..").canonicalFile
        private lateinit var tmp: File
        private lateinit var proc: Process
        private lateinit var peer: PeerConfig
        private lateinit var runDir: File

        private fun python(): List<String> {
            System.getenv("EDITH_PEER_PYTHON")?.let { return it.split(' ') }
            val venv = File(root, ".venv/bin/python")
            if (venv.canExecute()) return listOf(venv.path)
            return listOf("uv", "run", "--project", root.path, "python")
        }

        private fun py(vararg args: String): ProcessBuilder = ProcessBuilder(python() + listOf("-m", "edith_tools.commands.g") + args)
            .directory(root).also {
                it.environment()["PYTHONPATH"] = File(root, "tools").path
                it.environment()["EDITH_ROOT"] = root.path
            }

        @BeforeClass @JvmStatic fun startPeer() {
            tmp = Files.createTempDirectory("edith-peer").toFile()
            val ready = File(tmp, "ready.json")
            proc = py("glasses", "selftest", "--serve", "--host", "127.0.0.1", "--port", "0", "--token", "t0ken",
                "--out", File(tmp, "runs").path, "--ready-file", ready.path, "--quiet")
                .redirectErrorStream(true).redirectOutput(File(tmp, "peer.out")).start()
            val deadline = System.currentTimeMillis() + 120_000
            while (!ready.isFile || ready.length() == 0L) {
                check(proc.isAlive) { "peer exited: " + File(tmp, "peer.out").readText() }
                check(System.currentTimeMillis() < deadline) { "peer did not start" }
                Thread.sleep(100)
            }
            val info = J.parse(ready.readText())
            val port = J.num(info, "port")!!.toInt()
            runDir = File(J.str(info, "run_dir")!!)
            peer = PeerConfig("ws://127.0.0.1:$port/v1/selftest", "t0ken")
        }

        @AfterClass @JvmStatic fun stopPeer() {
            if (::proc.isInitialized) { proc.destroy(); proc.waitFor(5, TimeUnit.SECONDS); proc.destroyForcibly() }
        }

        val results by lazy {
            Results(File(tmp, "glasses"), app = mapOf("package" to "edith.selftest", "flavor" to "jvm-test",
                "version_name" to "test", "version_code" to 1, "platform" to "jvm"),
                device = mapOf("model" to "jvm", "sdk" to "0"))
        }
    }

    /** 440 Hz sine at the requested rate; mimics AudioRecord's blocking read. */
    private class SinePcm(override val source: String, override val requestedRate: Int, override val requestedChannels: Int, val amp: Double) : PcmStream {
        override val actualRate = requestedRate
        override val actualChannels = requestedChannels
        private var n = 0L
        override fun start(): Long = System.nanoTime() / 1_000_000
        override fun read(buf: ShortArray, off: Int, len: Int): Int {
            for (i in 0 until len) { buf[off + i] = (amp * 32767 * kotlin.math.sin(2 * Math.PI * 440 * n / actualRate)).toInt().toShort(); n++ }
            return len
        }
        override fun close() {}
    }

    @Test fun t13ClientAgainstPeer() {
        val decoder = JpegDecoder { b, off, len ->
            val img = ImageIO.read(b.inputStream(off, len)) ?: error("ImageIO could not decode")
            img.width to img.height
        }
        val r = T13Client(peer, decoder).run(seconds = 4.0, fps = 15)
        val res = r["peer_result"] as JsonObject?
        assertNotNull("t13.result from peer", res)
        assertEquals(60, J.num(res!!, "sent")!!.toInt())
        assertTrue("drops ${J.num(res, "drop_pct")}", J.num(res, "drop_pct")!! < 2.0)
        assertNotNull(J.num(res, "latency_ms_p95"))
        assertEquals("320x240", r["decoded_size"])
        assertTrue(File(runDir, "t13.jsonl").isFile)
        val tr = TestResult("T13", "Inset").apply { metrics.putAll(r); passCriterion = "p95<=150" }
        tr.finish(Status.MEASURED)
        results.put(tr)
        validate()
    }

    @Test fun t9ClientAgainstPeer() {
        val segs = listOf(T9Segment("src_MIC", "MIC", 1.0, "x"), T9Segment("wearer", "VOICE_RECOGNITION", 0.5, "x"),
            T9Segment("bystander", "VOICE_RECOGNITION", 0.5, "x"), T9Segment("broken", "NOPE", 0.5, "x"))
        val local = File(tmp, "local")
        val r = T9Client(peer, localDir = local).run(segs) { src, rate, ch ->
            if (src == "NOPE") throw IllegalStateException("no such source")
            SinePcm(src, rate, ch, if (src == "MIC") 0.5 else 0.05)
        }
        @Suppress("UNCHECKED_CAST") val out = r["segments"] as List<Map<String, Any?>>
        assertEquals(4, out.size)
        assertEquals(16000L, out[0]["samples"])
        assertEquals(16000L, out[0]["peer_samples"])
        assertTrue(out[3]["error"].toString().contains("no such source"))
        val wav = File(runDir, "t9_src_MIC.wav")
        assertTrue(wav.isFile)
        assertEquals(44L + 32000L, wav.length())
        assertEquals(44L + 32000L, File(local, "t9_src_MIC.wav").length())
        assertTrue(File(runDir, "t9_wearer.wav").isFile)
        val tr = TestResult("T9", "Mic").apply { metrics.putAll(r) }
        tr.finish(Status.MEASURED)
        results.put(tr)
        validate()
    }

    @Test fun t11ClientAgainstPeer() {
        val r = T11Client(peer).run(bytes = 1L shl 20, pings = 5)
        assertEquals(emptyList<String>(), r["errors"])
        assertEquals(1L shl 20, r["down_bytes"])
        assertEquals(5, r["pongs"])
        results.put(TestResult("T11", "Wi-Fi").apply { metrics.putAll(r); finish(Status.MEASURED) })
        validate()
    }

    @Test fun badTokenIsRejected() {
        val bad = PeerConfig(peer.wsUrl, "wrong")
        val e = runCatching { WsSession(PeerConfig.client(), bad.wsFor("t13")).awaitOpen() }.exceptionOrNull()
        assertNotNull(e)
    }

    private fun validate() {
        val p = py("glasses", "validate", "--schema", File(root, "docs/bringup/results.schema.json").path, results.file.path)
            .redirectErrorStream(true).start()
        val out = p.inputStream.bufferedReader().readText()
        assertEquals("schema validation: $out", 0, p.waitFor())
    }
}
