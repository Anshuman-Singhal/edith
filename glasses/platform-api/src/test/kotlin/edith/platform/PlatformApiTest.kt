package edith.platform

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PlatformApiTest {
    @Test fun sbsDetectedFor1280x480() {
        val l = StereoLayout.detect(1280, 480)
        assertEquals(StereoLayout.Mode.SBS, l.mode)
        assertEquals(Rect(0, 0, 640, 480), l.left)
        assertEquals(Rect(640, 0, 1280, 480), l.right)
    }

    @Test fun monoFor640x480AndPhone() {
        assertEquals(StereoLayout.Mode.MONO, StereoLayout.detect(640, 480).mode)
        assertEquals(StereoLayout.Mode.MONO, StereoLayout.detect(2400, 1080).mode)
        assertNull(StereoLayout.detect(640, 480).right)
        assertEquals(StereoLayout.Mode.SBS, StereoLayout.detect(640, 480, StereoLayout.Mode.SBS).mode)
    }

    @Test fun percentileNearestRank() {
        val v = (1..100).map { it.toDouble() }
        assertEquals(95.0, Stats.percentile(v, 95.0)!!, 0.0)
        assertEquals(50.0, Stats.percentile(v, 50.0)!!, 0.0)
        assertNull(Stats.percentile(emptyList(), 50.0))
    }

    @Test fun rmsOfFullScaleSquareIsZeroDb() {
        val s = ShortArray(1000) { if (it % 2 == 0) Short.MAX_VALUE else Short.MIN_VALUE }
        assertTrue(kotlin.math.abs(Stats.rmsDbfs(s)) < 0.01)
        assertEquals(-120.0, Stats.rmsDbfs(ShortArray(10)), 0.0)
    }

    @Test fun gestureWireRoundTrip() {
        for (g in Gesture.entries) assertEquals(g, Gesture.fromWire(g.wire))
    }
}
