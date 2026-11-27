package edith.selftest

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Canvas
import android.graphics.Color
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.FrameMetrics
import android.view.View
import android.view.Window
import android.view.WindowManager
import edith.platform.Gesture
import edith.platform.GestureEvent
import edith.platform.RawKey
import edith.platform.RawTouch
import edith.platform.StereoLayout
import edith.selftest.proto.PeerConfig
import edith.selftest.proto.Registry
import edith.selftest.proto.RegistryTest
import edith.selftest.proto.Results
import edith.selftest.tests.BatteryLogger
import edith.selftest.tests.T11Wifi
import edith.selftest.tests.T13Inset
import edith.selftest.tests.T14Battery
import edith.selftest.tests.T5Binocular
import edith.selftest.tests.T6Touch
import edith.selftest.tests.T7Ptt
import edith.selftest.tests.T9Mic
import java.io.File
import java.util.concurrent.ConcurrentLinkedDeque

/**
 * Standalone bring-up APK (D13a). Provisioning via intent extras, persisted in SharedPreferences:
 *
 *   adb shell am start -n edith.selftest/.SelfTestActivity \
 *       --es peer ws://<laptop-ip>:7400/v1/selftest --es token <t> [--es goto T13] [--ez start true]
 *
 * Optional: --ei t6_trials 20, --ei t7_wear_s 300, --ei t9_source_s 10, --ei t9_cmd_s 60,
 * --ei t13_s 60, --es stereo sbs|mono (force the layout; default: detect).
 * Results: getExternalFilesDir("results")/<run_id>/results.json (pulled by tools/bringup.sh).
 */
class SelfTestActivity : SelfTestHost() {
    lateinit var results: Results; private set
    var registry: List<RegistryTest> = emptyList(); private set
    var peer: PeerConfig? = null; private set
    val ui = Ui()
    lateinit var view: SelfTestView; private set
    lateinit var screens: List<Screen>; private set
    @Volatile var index = 0
    var forcedStereo: StereoLayout.Mode? = null
    val frameMs = ConcurrentLinkedDeque<Double>()
    lateinit var battery: BatteryLogger; private set
    private val main = Handler(Looper.getMainLooper())
    private val prefs by lazy { getSharedPreferences("provisioning", Context.MODE_PRIVATE) }

    val runDir: File get() = results.dir
    val current: Screen get() = screens[index]

    fun intExtra(key: String, def: Int): Int = prefs.getInt(key, def)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON or WindowManager.LayoutParams.FLAG_FULLSCREEN)
        provision(intent)
        registry = runCatching { Registry.parse(assets.open("registry.json").bufferedReader().readText()) }.getOrDefault(emptyList())
        val base = getExternalFilesDir("results") ?: File(filesDir, "results")
        val runId = Results.runIdNow()
        results = Results(File(base, runId), runId, app = mapOf(
            "package" to packageName, "flavor" to BuildConfig.FLAVOR, "version_name" to BuildConfig.VERSION_NAME,
            "version_code" to BuildConfig.VERSION_CODE, "platform" to platform.info.platformName, "git" to BuildConfig.GIT_REV,
        ), device = runCatching { platform.info.identity() }.getOrDefault(emptyMap()))
        results.provisioning = mapOf("peer" to peer?.wsUrl, "token_set" to (peer?.token != null))
        results.write()

        screens = listOf(
            InfoScreen(this, "intro", "EDITH selftest") { introLines() },
            T5Binocular(this), T6Touch(this), T7Ptt(this), T9Mic(this), T11Wifi(this), T13Inset(this), T14Battery(this),
            InfoScreen(this, "done", "Summary") { summaryLines() },
        )
        view = SelfTestView(this)
        view.keepScreenOn = true
        view.setBackgroundColor(Color.BLACK)
        setContentView(view)
        runCatching {
            window.addOnFrameMetricsAvailableListener({ _: Window, m: FrameMetrics, _: Int ->
                frameMs.addLast(m.getMetric(FrameMetrics.TOTAL_DURATION) / 1e6)
                while (frameMs.size > 2000) frameMs.pollFirst()
            }, main)
        }
        battery = BatteryLogger(this).also { it.start() }
        val need = listOf(Manifest.permission.RECORD_AUDIO, Manifest.permission.CAMERA)
            .filter { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }
        if (need.isNotEmpty()) requestPermissions(need.toTypedArray(), 1)
        view.post { recordDisplay(); handleGoto(intent) }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        provision(intent)
        results.provisioning = mapOf("peer" to peer?.wsUrl, "token_set" to (peer?.token != null))
        results.write()
        handleGoto(intent)
    }

    override fun onDestroy() {
        runCatching { battery.stop() }
        screens.forEach { runCatching { it.stop() } }
        super.onDestroy()
    }

    private fun provision(i: Intent?) {
        val e = prefs.edit()
        i?.getStringExtra("peer")?.let { e.putString("peer", it) }
        i?.getStringExtra("token")?.let { e.putString("token", it) }
        i?.getStringExtra("ws")?.let { e.putString("ws", it) }
        i?.getStringExtra("stereo")?.let { e.putString("stereo", it) }
        for (k in listOf("t6_trials", "t7_wear_s", "t9_source_s", "t9_cmd_s", "t13_s")) {
            if (i?.hasExtra(k) == true) e.putInt(k, i.getIntExtra(k, i.getStringExtra(k)?.toIntOrNull() ?: 0))
        }
        e.apply()
        peer = runCatching { PeerConfig.parse(prefs.getString("peer", null), prefs.getString("token", null)) }.getOrNull()
        forcedStereo = when (prefs.getString("stereo", null)) { "sbs" -> StereoLayout.Mode.SBS; "mono" -> StereoLayout.Mode.MONO; else -> null }
    }

    private fun handleGoto(i: Intent?) {
        val target = i?.getStringExtra("goto") ?: return
        val k = screens.indexOfFirst { it.id.equals(target, ignoreCase = true) }
        if (k >= 0) { go(k); if (i.getBooleanExtra("start", false)) primary() }
    }

    fun recordDisplay() {
        runCatching {
            val d = platform.display.info()
            val l = StereoLayout.detect(view.width.coerceAtLeast(1), view.height.coerceAtLeast(1), forcedStereo)
            results.display = mapOf(
                "window_w" to view.width, "window_h" to view.height, "display_w" to d.widthPx, "display_h" to d.heightPx,
                "density_dpi" to d.densityDpi, "refresh_hz" to d.refreshHz,
                "layout_detected" to l.mode.wire, "layout_forced" to (forcedStereo?.wire),
                "eye_w" to l.eyeWidth, "eye_h" to l.eyeHeight, "extra" to d.extra,
                "note" to "UNVERIFIED until T5: SBS assumed when window aspect >= ${StereoLayout.SBS_MIN_ASPECT}",
            )
            results.write()
        }
    }

    fun layout(): StereoLayout = StereoLayout.detect(view.width.coerceAtLeast(1), view.height.coerceAtLeast(1), forcedStereo)

    // ---- navigation ------------------------------------------------------------------------

    fun go(k: Int) {
        val n = k.coerceIn(0, screens.lastIndex)
        if (n == index) return
        index = n
    }

    fun next() = go(index + 1)
    fun back() = go(index - 1)

    fun primary() {
        val s = current
        when (s.phase) {
            Screen.Phase.IDLE -> if (s is InfoScreen) next() else { s.phase = Screen.Phase.RUNNING; runCatching { s.start() }.onFailure { s.result?.error("start", it) } }
            Screen.Phase.RUNNING -> {}
            Screen.Phase.DONE -> next()
        }
    }

    override fun onGesture(event: GestureEvent) {
        val s = current
        val consumed = runCatching { s.onGesture(event) }.getOrDefault(false)
        if (consumed) return
        when (event.gesture) {
            Gesture.TAP -> primary()
            Gesture.DOUBLE_TAP, Gesture.SLIDE_BACKWARD -> { if (s.phase == Screen.Phase.RUNNING) return; back() }
            Gesture.SLIDE_FORWARD -> { if (s.phase == Screen.Phase.RUNNING) return; next() }
            else -> {}
        }
    }

    override fun onRawTouch(event: RawTouch) { runCatching { current.onRawTouch(event) } }
    override fun onKey(event: RawKey) { runCatching { current.onKey(event) } }

    // ---- text ------------------------------------------------------------------------------

    private fun introLines(): List<String> {
        val l = layout()
        return listOf(
            "Flavor ${BuildConfig.FLAVOR} · ${platform.info.platformName} · ${BuildConfig.VERSION_NAME} (${BuildConfig.GIT_REV})",
            "Window ${view.width}x${view.height} → ${l.mode.wire.uppercase()} ${l.eyeWidth}x${l.eyeHeight} per eye" +
                (forcedStereo?.let { " (forced)" } ?: " (detected, UNVERIFIED)"),
            "Peer: " + (peer?.wsUrl ?: "NONE — T9 saves locally only; T11/T13 need --es peer"),
            "Run ${results.runId}",
            "",
            "TAP = start / next   2×TAP = back",
            "SLIDE fwd = skip   SLIDE back = previous",
            "TAP to begin with T5.",
        )
    }

    private fun summaryLines(): List<String> =
        screens.mapNotNull { s -> s.result?.let { "${s.id}  ${it.status.wire.uppercase()}  ${it.errors.size} errors" } ?: if (s.id.startsWith("T")) "${s.id}  not run" else null } +
            listOf("", "Results: ${results.file.path}", "Pull with: tools/bringup.sh --pull-only")
}

/** Draws the current screen into each eye. Never consumes touches (the SDK must see them). */
class SelfTestView(private val a: SelfTestActivity) : View(a) {
    override fun onDraw(c: Canvas) {
        super.onDraw(c)
        val l = a.layout()
        a.ui.applyScale(minOf(l.eyeHeight / 480f, l.eyeWidth / 640f).coerceAtLeast(0.5f))
        val eyes = listOfNotNull(l.left, l.right)
        val s = a.current
        for ((i, r) in eyes.withIndex()) {
            c.save()
            c.clipRect(r.left, r.top, r.right, r.bottom)
            c.translate(r.left.toFloat(), r.top.toFloat())
            val handled = try { s.drawEye(c, r.width, r.height, i) } catch (t: Throwable) { false }
            if (!handled) drawText(c, s, r.width, r.height)
            c.restore()
        }
        postInvalidateOnAnimation()
    }

    private fun drawText(c: Canvas, s: Screen, w: Int, h: Int) {
        val u = a.ui
        val pad = 24f * u.scale
        val tag = if (a.registry.firstOrNull { it.id == s.id }?.tags?.contains("g0") == true) "  [g0]" else ""
        var y = u.lines(c, pad, pad, w - 2 * pad, listOf("${s.id}  ${s.title}$tag"), u.title, u.accent)
        val body = if (s.phase == Screen.Phase.IDLE) s.intro() + listOf("", "TAP to start · SLIDE fwd to skip") else s.status()
        y = u.lines(c, pad, y + 8 * u.scale, w - 2 * pad, body)
        val bat = a.battery.last?.levelPct?.let { "bat $it%" } ?: ""
        u.lines(c, pad, h - pad - u.mono.textSize * 1.4f, w - 2 * pad, listOf("${a.index}/${a.screens.lastIndex}  ${a.results.runId}  $bat"), u.mono, u.dim)
    }

    override fun onTouchEvent(event: android.view.MotionEvent?): Boolean = false
}
