package edith.selftest.tests

import edith.selftest.Screen
import edith.selftest.SelfTestActivity
import edith.selftest.proto.Status
import edith.selftest.proto.T11Client

/** T11 Wi-Fi: HTTP down/up throughput and WS RTT against the peer (note 2.4 vs 5 GHz yourself). */
class T11Wifi(ctx: SelfTestActivity) : Screen(ctx, "T11", "Wi-Fi") {
    override fun intro() = listOf("Downloads and uploads 8 MiB to the laptop peer, then 50 pings.",
        "Pass: ≥10 Mbit/s each way, RTT p95 <30 ms (router). Write down the band (2.4/5 GHz).",
        "Peer: " + (ctx.peer?.wsUrl ?: "NONE — provision with --es peer"))

    override fun status() = result?.let { r ->
        listOf(if (phase == Phase.DONE) "Result: ${r.status.wire.uppercase()}" else "Running…",
            "down ${r.metrics["down_mbit_s"]} Mbit/s   up ${r.metrics["up_mbit_s"]} Mbit/s",
            "RTT p50 ${r.metrics["rtt_ms_p50"]} p95 ${r.metrics["rtt_ms_p95"]} ms") + if (phase == Phase.DONE) listOf("TAP = next") else emptyList()
    } ?: emptyList()

    override fun start() {
        val r = newResult()
        val peer = ctx.peer ?: run { r.errors += "no peer provisioned (--es peer ws://<ip>:7400/v1/selftest)"; finish(Status.SKIPPED); return }
        background("run") {
            r.metrics.putAll(T11Client(peer).run())
            val down = r.metrics["down_mbit_s"] as? Double; val up = r.metrics["up_mbit_s"] as? Double; val rtt = r.metrics["rtt_ms_p95"] as? Double
            finish(if (down != null && up != null && rtt != null && down >= 10 && up >= 10 && rtt < 30) Status.PASS else Status.FAIL)
        }
    }
}
