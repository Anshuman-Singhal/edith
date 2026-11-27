package edith.selftest.proto

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/** D13a: the registry generated from docs/bringup/TESTS.md holds 19 tests with g0 tags. */
class RegistryGenerationTest {
    private val root = File(System.getProperty("edith.repoRoot") ?: "../..")

    @Test fun nineteenTestsWithPassCriteriaOwnersAndG0Tags() {
        val tests = Registry.parse(File(root, "docs/bringup/registry/registry.json").readText())
        assertEquals(19, tests.size)
        assertEquals((0..18).map { "T$it" }, tests.map { it.id })
        assertEquals(setOf("T0", "T5", "T6", "T7", "T9", "T13", "T14"), tests.filter { "g0" in it.tags }.map { it.id }.toSet())
        for (t in tests) {
            assertTrue("${t.id} pass", t.pass.isNotBlank())
            assertTrue("${t.id} owner", t.owners.isNotEmpty())
            assertEquals(t.id, if (t.id.drop(1).toInt() <= 4) "host" else "apk", t.runner)
        }
        assertEquals(setOf("T0", "T1", "T2", "T3", "T4"), tests.filter { it.runner == "host" }.map { it.id }.toSet())
        assertTrue(tests.filter { "g0" in it.tags }.all { it.implemented })
    }
}
