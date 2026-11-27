package edith.platform.generic

import android.os.Bundle
import android.view.KeyEvent
import android.view.MotionEvent
import androidx.appcompat.app.AppCompatActivity
import edith.platform.GestureEvent
import edith.platform.GlassesPlatform
import edith.platform.InputListener
import edith.platform.RawKey
import edith.platform.RawTouch

/**
 * Host activity for the generic flavor. Same contract as `RayneoHostActivity`: subclasses
 * override the [InputListener] callbacks and read [platform].
 */
open class GenericHostActivity : AppCompatActivity(), InputListener {
    lateinit var platform: GlassesPlatform; private set
    private val dispatch = DispatchingInput()
    private lateinit var classifier: GenericGestureClassifier

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        platform = GenericPlatform(this, dispatch)
        dispatch.setListener(this)
        classifier = GenericGestureClassifier(this) { dispatch.onGesture(it) }
    }

    override fun dispatchTouchEvent(ev: MotionEvent): Boolean {
        runCatching { dispatch.onRawTouch(AndroidEvents.touch(ev)) }
        runCatching { classifier.onTouch(ev) }
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
}
