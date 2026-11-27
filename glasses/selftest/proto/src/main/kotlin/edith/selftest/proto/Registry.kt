package edith.selftest.proto

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

/** One bring-up test from docs/bringup/registry/registry.json (generated from TESTS.md). */
data class RegistryTest(
    val id: String, val name: String, val tier: String, val tags: List<String>, val owners: List<String>,
    val runner: String, val procedure: String, val pass: String, val implemented: Boolean,
)

object Registry {
    fun parse(text: String): List<RegistryTest> {
        val root = J.parse(text)
        val tests = root["tests"] as JsonArray
        return tests.map { el ->
            val o = el as JsonObject
            fun s(k: String) = (o[k] as JsonPrimitive).contentOrNull ?: ""
            fun l(k: String) = (o[k] as JsonArray).map { (it as JsonPrimitive).content }
            RegistryTest(
                id = s("id"), name = s("name"), tier = s("tier"), tags = l("tags"), owners = l("owners"),
                runner = s("runner"), procedure = s("procedure"), pass = s("pass"),
                implemented = (o["implemented"] as JsonPrimitive).content.toBoolean(),
            )
        }
    }
}
