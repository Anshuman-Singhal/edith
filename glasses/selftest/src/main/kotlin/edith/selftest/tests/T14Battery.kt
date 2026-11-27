package edith.selftest.tests

import edith.platform.PowerSample
import edith.selftest.Screen
import edith.selftest.SelfTestActivity
import edith.selftest.proto.J
import edith.selftest.proto.Status
import java.io.File

/** Logs battery + thermal every 10 s for the whole session to battery.jsonl (T14/T15). */
class BatteryLogger(private val ctx: SelfTestActivity) {
    @Volatile var last: PowerSample? = null; private set
    @Volatile var mode = "idle"
    @Volatile private var running = false
    val samples = java.util.concurrent.ConcurrentLinkedQueue<PowerSample>()

    fun start() {
        running = true
        Thread({
            while (running) {
                runCatching {
                    val s = ctx.platform.power.sample()
                    last = s; samples += s
                    File(ctx.runDir, "battery.jsonl").appendText(J.of(mapOf("mode" to mode, "t" to s.tWallMs, "level_pct" to s.levelPct,
                        "status" to s.status, "plugged" to s.plugged, "temp_c" to s.temperatureC, "voltage_mv" to s.voltageMv,
                        "current_now_ua" to s.currentNowUa, "current_avg_ua" to s.currentAvgUa, "charge_counter_uah" to s.chargeCounterUah,
                        "energy_nwh" to s.energyNwh, "thermal" to s.thermalStatus, "headroom" to s.thermalHeadroom)).toString() + "\n")
                }
                try { Thread.sleep(10_000) } catch (_: InterruptedException) { break }
            }
        }, "battery-logger").apply { isDaemon = true; start() }
    }

    fun stop() { running = false }
}

/**
 * T14 battery: TAP 1 = mark HUD-only; TAP 2 = full load (mic capture + inset stream if a peer is
 * provisioned + this animated display; camera at 10 fps comes with D13b); TAP 3 = stop.
 * The 10 s logger runs all session; this screen summarises it into results.json.
 */
class T14Battery(ctx: SelfTestActivity) : Screen(ctx, "T14", "Battery") {
    @Volatile private var loadOn = false
    private var startLevel: Int? = null
    private var t0 = 0L

    override fun intro() = listOf("Logs battery every 10 s (level, CURRENT_NOW, temperature, thermal).",
        "TAP 1: HUD-only.  TAP 2: full load (mic + inset).  TAP 3: stop.",
        "Targets: full load ≥30 min and HUD-only ≥60 min from 100→20%. Also try while charging.")

    override fun status(): List<String> {
        val s = ctx.battery.last
        return listOf("Mode: ${ctx.battery.mode}   ${(System.currentTimeMillis() - t0) / 60000} min",
            "Level ${s?.levelPct}%  ${s?.status}/${s?.plugged}  ${s?.temperatureC} °C",
            "CURRENT_NOW ${s?.currentNowUa} µA (sign/units UNVERIFIED)  thermal ${s?.thermalStatus}",
            if (phase == Phase.DONE) "Result: ${result?.status?.wire?.uppercase()} · TAP = next" else "TAP = next mode")
    }

    override fun start() {
        newResult(); t0 = System.currentTimeMillis(); startLevel = ctx.battery.last?.levelPct
        ctx.battery.mode = "hud_only"; summarise()
    }

    override fun onGesture(e: edith.platform.GestureEvent): Boolean {
        if (phase != Phase.RUNNING || e.gesture != edith.platform.Gesture.TAP) return false
        if (ctx.battery.mode == "hud_only") { ctx.battery.mode = "full_load"; startLoad() } else { stop(); summarise(); finish(Status.MEASURED) }
        return true
    }

    private fun startLoad() {
        loadOn = true
        background("mic_load") {
            try {
                val s = ctx.platform.mic.open("VOICE_RECOGNITION", 16000, 1)
                val buf = ShortArray(320); s.start()
                try { while (loadOn) s.read(buf, 0, buf.size) } finally { s.close() }
            } catch (t: Throwable) { result?.error("mic_load", t) }
        }
        (ctx.screens.firstOrNull { it is T13Inset } as? T13Inset)?.let { t13 -> background("inset_load") { t13.loadStream { !loadOn } } }
        ctx.view.postDelayed(object : Runnable { override fun run() { if (phase == Phase.RUNNING) { summarise(); ctx.view.postDelayed(this, 10_000) } } }, 10_000)
    }

    private fun summarise() {
        val r = result ?: return
        val all = ctx.battery.samples.toList()
        r.metrics["samples"] = all.size
        r.metrics["start_level_pct"] = startLevel
        r.metrics["last"] = ctx.battery.last?.let { mapOf("level_pct" to it.levelPct, "current_now_ua" to it.currentNowUa, "temp_c" to it.temperatureC, "thermal" to it.thermalStatus) }
        r.metrics["current_now_readable"] = all.any { it.currentNowUa != null && it.currentNowUa != 0L }
        r.metrics["current_now_min_max_ua"] = all.mapNotNull { it.currentNowUa }.let { if (it.isEmpty()) null else listOf(it.min(), it.max()) }
        r.metrics["thermal_seen"] = all.mapNotNull { it.thermalStatus }.toSortedSet().toList()
        r.metrics["log"] = "battery.jsonl"
        r.metrics["camera_load"] = "not in D13a (T10/D13b)"
        save()
    }

    override fun stop() { loadOn = false; ctx.battery.mode = "idle" }
}
