package edith.selftest

import android.content.Intent
import android.os.SystemClock
import androidx.test.core.app.ApplicationProvider
import edith.platform.Gesture
import edith.platform.GestureEvent
import edith.selftest.proto.J
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * Robolectric smoke test (sdk 31, the likely device level): the activity starts with its flavor
 * Application (rayneo: MercurySDK.init before BaseEventActivity), persists provisioning, writes
 * results.json, and T5 can be driven to completion by gestures alone.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [31], qualifiers = "w1280dp-h480dp-land-mdpi")
class SelfTestActivityTest {
    private fun tap(a: SelfTestActivity, g: Gesture = Gesture.TAP) =
        a.onGesture(GestureEvent(g, SystemClock.uptimeMillis(), "temple_sdk", "test"))

    @Test fun startsProvisionedAndRunsT5() {
        val i = Intent(ApplicationProvider.getApplicationContext(), SelfTestActivity::class.java)
            .putExtra("peer", "ws://192.0.2.1:7400/v1/selftest").putExtra("token", "tok")
        val a = Robolectric.buildActivity(SelfTestActivity::class.java, i).setup().get()
        assertEquals("ws://192.0.2.1:7400/v1/selftest", a.peer?.wsUrl)
        assertEquals(19, a.registry.size)
        assertTrue(a.results.file.isFile)

        tap(a)                                  // intro -> T5
        assertEquals("T5", a.current.id)
        tap(a)                                  // start T5
        tap(a, Gesture.SLIDE_FORWARD)           // right-eye offset +1
        tap(a)                                  // pattern done -> questions
        repeat(4) { tap(a) }                    // 4 × yes
        val doc = J.parse(a.results.file.readText())
        val t5 = (doc["tests"] as JsonObject)["T5"] as JsonObject
        assertEquals("pass", J.str(t5, "status"))
        assertEquals(1.0, J.num(t5["metrics"] as JsonObject, "right_eye_offset_px"))
        tap(a)                                  // DONE -> next
        assertEquals("T6", a.current.id)
        tap(a, Gesture.DOUBLE_TAP)              // back
        assertEquals("T5", a.current.id)
    }
}
