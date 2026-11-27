package edith.platform.rayneo

import android.app.Application
import android.os.Bundle
import android.os.SystemClock
import android.view.KeyEvent
import android.view.MotionEvent
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.ffalcon.mercury.android.sdk.MercurySDK
import com.ffalcon.mercury.android.sdk.touch.TempleAction
import com.ffalcon.mercury.android.sdk.ui.activity.BaseEventActivity
import edith.platform.Gesture
import edith.platform.GestureEvent
import edith.platform.GlassesPlatform
import edith.platform.InputListener
import edith.platform.RawKey
import edith.platform.RawTouch
import edith.platform.generic.AndroidEvents
import edith.platform.generic.AndroidInfo
import edith.platform.generic.DispatchingInput
import edith.platform.generic.GenericPlatform
import kotlinx.coroutines.launch

/**
 * Application base for every rayneo flavor. `MercurySDK.init` must run in
 * `Application.onCreate`, otherwise `BaseEventActivity`'s constructor throws
 * `UninitializedPropertyAccessException` [probed by platform r3; C106].
 */
open class RayneoApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        MercurySDK.init(this)
    }
}

/** RayNeo platform: AOSP display/mic/power/sensors plus temple input from the Mercury SDK. */
class RayneoPlatform(activity: android.app.Activity, input: DispatchingInput) : GenericPlatform(activity, input) {
    override val info = AndroidInfo("rayneo")
}

/**
 * Host activity for rayneo flavors: wraps `BaseEventActivity` and maps its `TempleAction` flow
 * to platform-api [GestureEvent]s. Raw MotionEvents and KeyEvents are forwarded first, so T6/T7
 * see everything the SDK saw. Slide forward/backward follow the system "natural mode" setting
 * (SDK doc §5.8), which T6 records. Content views must not consume touches, or the SDK's
 * `onTouchEvent` never sees them.
 */
abstract class RayneoHostActivity : BaseEventActivity(), InputListener {
    lateinit var platform: GlassesPlatform; private set
    private val dispatch = DispatchingInput()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        platform = RayneoPlatform(this, dispatch)
        dispatch.setListener(this)
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.RESUMED) {
                templeActionViewModel.state.collect { a -> runCatching { dispatch.onGesture(map(a)) } }
            }
        }
    }

    override fun dispatchTouchEvent(ev: MotionEvent): Boolean {
        runCatching { dispatch.onRawTouch(AndroidEvents.touch(ev)) }
        return super.dispatchTouchEvent(ev)
    }

    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        runCatching { dispatch.onKey(AndroidEvents.key(event)) }
        val g = AndroidEvents.keyGesture(event)
        if (g != null) { dispatch.onGesture(g); return true }
        return if (event.keyCode == KeyEvent.KEYCODE_BACK) true else super.dispatchKeyEvent(event)
    }

    override fun onGesture(event: GestureEvent) {}
    override fun onRawTouch(event: RawTouch) {}
    override fun onKey(event: RawKey) {}

    companion object {
        fun map(a: TempleAction): GestureEvent {
            val g = when (a) {
                is TempleAction.Click -> Gesture.TAP
                is TempleAction.DoubleClick -> Gesture.DOUBLE_TAP
                is TempleAction.TripleClick -> Gesture.TRIPLE_TAP
                is TempleAction.LongClick -> Gesture.LONG_PRESS
                is TempleAction.SlideForward -> Gesture.SLIDE_FORWARD
                is TempleAction.SlideBackward -> Gesture.SLIDE_BACKWARD
                is TempleAction.SlideUpwards -> Gesture.SLIDE_UP
                is TempleAction.SlideDownwards -> Gesture.SLIDE_DOWN
                is TempleAction.DoubleFingerClick -> Gesture.TWO_FINGER_TAP
                is TempleAction.DoubleFingerLongClick -> Gesture.TWO_FINGER_LONG_PRESS
                is TempleAction.ActionDown -> Gesture.ACTION_DOWN
                is TempleAction.ActionUp -> Gesture.ACTION_UP
                else -> Gesture.OTHER
            }
            return GestureEvent(g, SystemClock.uptimeMillis(), "temple_sdk", a.toString())
        }
    }
}
