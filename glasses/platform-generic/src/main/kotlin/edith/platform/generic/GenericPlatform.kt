package edith.platform.generic

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.hardware.Sensor
import android.hardware.SensorManager
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.hardware.display.DisplayManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.BatteryManager
import android.os.Build
import android.os.PowerManager
import android.os.SystemClock
import edith.platform.CameraPort
import edith.platform.DisplayInfo
import edith.platform.DisplayPort
import edith.platform.GlassesPlatform
import edith.platform.InfoPort
import edith.platform.MicPort
import edith.platform.PcmStream
import edith.platform.PosePort
import edith.platform.PowerPort
import edith.platform.PowerSample
import edith.platform.StereoLayout

/** AOSP implementation of [GlassesPlatform]; platform-rayneo reuses all of it except input. */
open class GenericPlatform(protected val activity: Activity, override val input: DispatchingInput = DispatchingInput()) : GlassesPlatform {
    override val display: DisplayPort = AndroidDisplay(activity)
    override val mic: MicPort = AndroidMic()
    override val pose: PosePort = AndroidPose(activity)
    override val camera: CameraPort = AndroidCamera(activity)
    override val power: PowerPort = AndroidPower(activity)
    override val info: InfoPort = AndroidInfo("generic")
}

class AndroidDisplay(private val activity: Activity) : DisplayPort {
    override fun info(): DisplayInfo {
        val root = activity.window?.decorView
        val dm = activity.resources.displayMetrics
        val w = root?.width?.takeIf { it > 0 } ?: dm.widthPixels
        val h = root?.height?.takeIf { it > 0 } ?: dm.heightPixels
        val extra = linkedMapOf<String, String>()
        @Suppress("DEPRECATION") val d = activity.windowManager.defaultDisplay
        runCatching {
            val m = d.mode
            extra["mode"] = "${m.physicalWidth}x${m.physicalHeight}@${m.refreshRate}"
            extra["supported_modes"] = d.supportedModes.joinToString { "${it.physicalWidth}x${it.physicalHeight}@${it.refreshRate}" }
        }
        runCatching {
            val dmgr = activity.getSystemService(Context.DISPLAY_SERVICE) as DisplayManager
            extra["displays"] = dmgr.displays.joinToString { "${it.displayId}:${it.name}" }
        }
        extra["metrics"] = "${dm.widthPixels}x${dm.heightPixels} density=${dm.density} xdpi=${dm.xdpi} ydpi=${dm.ydpi}"
        if (Build.VERSION.SDK_INT >= 30) runCatching {
            val b = activity.windowManager.currentWindowMetrics.bounds
            extra["window_metrics"] = "${b.width()}x${b.height()}"
        }
        return DisplayInfo(w, h, dm.densityDpi, d.refreshRate, StereoLayout.detect(w, h), extra)
    }

    override fun setBrightness(level: Float) {
        val lp = activity.window.attributes
        lp.screenBrightness = if (level < 0) -1f else level.coerceIn(0.01f, 1f)
        activity.window.attributes = lp
    }
}

class AndroidMic : MicPort {
    override fun sources(): List<String> = SOURCES.keys.toList()

    @SuppressLint("MissingPermission")
    override fun open(source: String, sampleRate: Int, channels: Int): PcmStream {
        val src = SOURCES[source] ?: throw IllegalArgumentException("unknown AudioSource $source")
        val chMask = if (channels == 2) AudioFormat.CHANNEL_IN_STEREO else AudioFormat.CHANNEL_IN_MONO
        val min = AudioRecord.getMinBufferSize(sampleRate, chMask, AudioFormat.ENCODING_PCM_16BIT)
        if (min <= 0) throw IllegalStateException("getMinBufferSize=$min for $sampleRate Hz ch=$channels")
        val rec = AudioRecord(src, sampleRate, chMask, AudioFormat.ENCODING_PCM_16BIT, maxOf(min * 4, sampleRate / 5 * 2 * channels))
        if (rec.state != AudioRecord.STATE_INITIALIZED) { rec.release(); throw IllegalStateException("AudioRecord($source) not initialized") }
        return AudioRecordStream(rec, source, sampleRate, channels)
    }

    companion object {
        val SOURCES = linkedMapOf(
            "DEFAULT" to MediaRecorder.AudioSource.DEFAULT, "MIC" to MediaRecorder.AudioSource.MIC,
            "VOICE_RECOGNITION" to MediaRecorder.AudioSource.VOICE_RECOGNITION,
            "VOICE_COMMUNICATION" to MediaRecorder.AudioSource.VOICE_COMMUNICATION,
            "CAMCORDER" to MediaRecorder.AudioSource.CAMCORDER, "UNPROCESSED" to MediaRecorder.AudioSource.UNPROCESSED,
            "VOICE_PERFORMANCE" to MediaRecorder.AudioSource.VOICE_PERFORMANCE,
        )
    }
}

class AudioRecordStream(val record: AudioRecord, override val source: String, override val requestedRate: Int, override val requestedChannels: Int) : PcmStream {
    override val actualRate: Int get() = record.sampleRate
    override val actualChannels: Int get() = record.channelCount
    override fun start(): Long { record.startRecording(); return SystemClock.uptimeMillis() }
    override fun read(buf: ShortArray, off: Int, len: Int): Int = record.read(buf, off, len)
    override fun close() { runCatching { record.stop() }; record.release() }
}

class AndroidPose(private val ctx: Context) : PosePort {
    override fun sensors(): List<Map<String, String>> {
        val sm = ctx.getSystemService(Context.SENSOR_SERVICE) as SensorManager
        return sm.getSensorList(Sensor.TYPE_ALL).map {
            mapOf("name" to it.name, "type" to it.stringType, "vendor" to it.vendor, "min_delay_us" to it.minDelay.toString())
        }
    }
}

class AndroidCamera(private val ctx: Context) : CameraPort {
    override fun enumerate(): List<Map<String, String>> {
        val cm = ctx.getSystemService(Context.CAMERA_SERVICE) as CameraManager
        return cm.cameraIdList.map { id ->
            val c = cm.getCameraCharacteristics(id)
            val map = c.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP)
            mapOf("id" to id, "facing" to (c.get(CameraCharacteristics.LENS_FACING)?.toString() ?: "?"),
                "yuv_sizes" to (map?.getOutputSizes(android.graphics.ImageFormat.YUV_420_888)?.joinToString() ?: ""))
        }
    }
}

class AndroidPower(private val ctx: Context) : PowerPort {
    override fun sample(): PowerSample {
        val bi = ctx.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val bm = ctx.getSystemService(Context.BATTERY_SERVICE) as BatteryManager
        val pm = ctx.getSystemService(Context.POWER_SERVICE) as PowerManager
        fun prop(p: Int): Long? = runCatching { bm.getLongProperty(p) }.getOrNull()?.takeIf { it != Long.MIN_VALUE && it != Int.MIN_VALUE.toLong() }
        val level = bi?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
        val scale = bi?.getIntExtra(BatteryManager.EXTRA_SCALE, 100) ?: 100
        val status = when (bi?.getIntExtra(BatteryManager.EXTRA_STATUS, -1)) {
            BatteryManager.BATTERY_STATUS_CHARGING -> "charging"; BatteryManager.BATTERY_STATUS_DISCHARGING -> "discharging"
            BatteryManager.BATTERY_STATUS_FULL -> "full"; BatteryManager.BATTERY_STATUS_NOT_CHARGING -> "not_charging"; else -> "unknown"
        }
        val plugged = when (bi?.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0)) {
            0 -> "none"; BatteryManager.BATTERY_PLUGGED_AC -> "ac"; BatteryManager.BATTERY_PLUGGED_USB -> "usb"
            BatteryManager.BATTERY_PLUGGED_WIRELESS -> "wireless"; else -> "other"
        }
        val thermal = runCatching {
            when (pm.currentThermalStatus) {
                PowerManager.THERMAL_STATUS_NONE -> "NONE"; PowerManager.THERMAL_STATUS_LIGHT -> "LIGHT"
                PowerManager.THERMAL_STATUS_MODERATE -> "MODERATE"; PowerManager.THERMAL_STATUS_SEVERE -> "SEVERE"
                PowerManager.THERMAL_STATUS_CRITICAL -> "CRITICAL"; PowerManager.THERMAL_STATUS_EMERGENCY -> "EMERGENCY"
                PowerManager.THERMAL_STATUS_SHUTDOWN -> "SHUTDOWN"; else -> "?"
            }
        }.getOrNull()
        val headroom = if (Build.VERSION.SDK_INT >= 30) runCatching { pm.getThermalHeadroom(10) }.getOrNull()?.takeIf { !it.isNaN() } else null
        return PowerSample(
            tWallMs = System.currentTimeMillis(),
            levelPct = if (level >= 0 && scale > 0) level * 100 / scale else null,
            status = status, plugged = plugged,
            temperatureC = bi?.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, Int.MIN_VALUE)?.takeIf { it != Int.MIN_VALUE }?.div(10.0),
            voltageMv = bi?.getIntExtra(BatteryManager.EXTRA_VOLTAGE, -1)?.takeIf { it >= 0 },
            currentNowUa = prop(BatteryManager.BATTERY_PROPERTY_CURRENT_NOW),
            currentAvgUa = prop(BatteryManager.BATTERY_PROPERTY_CURRENT_AVERAGE),
            chargeCounterUah = prop(BatteryManager.BATTERY_PROPERTY_CHARGE_COUNTER),
            energyNwh = prop(BatteryManager.BATTERY_PROPERTY_ENERGY_COUNTER),
            thermalStatus = thermal, thermalHeadroom = headroom,
        )
    }
}

open class AndroidInfo(override val platformName: String) : InfoPort {
    override fun identity(): Map<String, String> = linkedMapOf(
        "platform" to platformName,
        "manufacturer" to Build.MANUFACTURER, "brand" to Build.BRAND, "model" to Build.MODEL,
        "device" to Build.DEVICE, "product" to Build.PRODUCT, "board" to Build.BOARD, "hardware" to Build.HARDWARE,
        "release" to Build.VERSION.RELEASE, "sdk" to Build.VERSION.SDK_INT.toString(),
        "security_patch" to (Build.VERSION.SECURITY_PATCH ?: ""), "fingerprint" to Build.FINGERPRINT,
        "soc" to if (Build.VERSION.SDK_INT >= 31) "${Build.SOC_MANUFACTURER} ${Build.SOC_MODEL}" else "",
        "abis" to Build.SUPPORTED_ABIS.joinToString(","),
    )
}
