package edith.selftest.tests

import edith.selftest.Screen
import edith.selftest.SelfTestActivity
import edith.selftest.proto.Status
import edith.selftest.proto.T9Client
import edith.selftest.proto.T9Plan
import edith.selftest.proto.T9Segment
import java.io.File

/**
 * T9 mic: 10 s per stock AudioSource (RayNeo vendor voice modes: UNVERIFIED, none known yet),
 * then wearer / bystander-at-1-m / 20-command segments, streamed as 16 kHz PCM to
 * `selftest --serve` (WAVs in runs/bringup/<ts>/) and saved locally as WAVs too.
 */
class T9Mic(ctx: SelfTestActivity) : Screen(ctx, "T9", "Mic") {
    @Volatile private var line = ""
    @Volatile private var countdown = ""

    override fun intro() = listOf(
        "Records each mic source for 10 s, then WEARER vs BYSTANDER (1 m away),",
        "then the 20-command read (${ctx.intExtra("t9_cmd_s", 60)} s). Have the command card ready.",
        "Peer: " + (ctx.peer?.wsUrl ?: "none — WAVs saved on the glasses only"),
    )

    override fun status() = if (phase == Phase.DONE) listOf("Result: ${result?.status?.wire?.uppercase()}",
        "wearer − bystander: ${result?.metrics?.get("wearer_minus_bystander_db")} dB",
        "WAVs: runs/bringup/<ts>/ on the laptop, and ${ctx.runDir.name}/t9/ here", "TAP = next")
    else listOf(line, "", countdown)

    override fun start() {
        val r = newResult()
        val perSource = ctx.intExtra("t9_source_s", 10).toDouble()
        val plan = T9Plan.default(ctx.platform.mic.sources(), perSource, ctx.intExtra("t9_cmd_s", 60).toDouble())
        r.metrics["plan"] = plan.map { mapOf("segment" to it.name, "source" to it.source, "seconds" to it.seconds) }
        r.metrics["vendor_voice_modes"] = "UNVERIFIED: none known for RayNeo X3 Pro; stock sources only"
        save()
        background("run") {
            val out = T9Client(ctx.peer, localDir = File(ctx.runDir, "t9")) { seg: T9Segment, i: Int, n: Int ->
                line = "Segment ${i + 1}/$n: ${seg.name}"
                for (k in 3 downTo 1) { countdown = "${seg.instruction}  — starts in $k s"; Thread.sleep(1000) }
                countdown = "${seg.instruction}  — RECORDING ${seg.seconds.toInt()} s"
            }.run(plan) { src, rate, ch -> ctx.platform.mic.open(src, rate, ch) }
            r.metrics.putAll(out)
            @Suppress("UNCHECKED_CAST") val segs = out["segments"] as List<Map<String, Any?>>
            val okSegs = segs.count { it["error"] == null }
            r.metrics["segments_ok"] = okSegs
            r.metrics["rate_channels_as_requested"] = segs.filter { it["error"] == null }.all { it["rate_ok"] == true }
            finish(if (okSegs == 0) Status.FAIL else Status.MEASURED)
        }
    }
}
