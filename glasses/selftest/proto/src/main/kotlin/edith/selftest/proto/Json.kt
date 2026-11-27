package edith.selftest.proto

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonPrimitive

/** Tiny helpers so callers can build JSON from plain Kotlin values (no serialization plugin). */
object J {
    val pretty = Json { prettyPrint = true }

    fun of(v: Any?): JsonElement = when (v) {
        null -> JsonNull
        is JsonElement -> v
        is String -> JsonPrimitive(v)
        is Boolean -> JsonPrimitive(v)
        is Double -> if (v.isNaN() || v.isInfinite()) JsonNull else JsonPrimitive(round(v))
        is Float -> of(v.toDouble())
        is Number -> JsonPrimitive(v)
        is Enum<*> -> JsonPrimitive(v.name.lowercase())
        is Map<*, *> -> JsonObject(v.entries.associate { (k, x) -> k.toString() to of(x) })
        is Iterable<*> -> JsonArray(v.map { of(it) })
        is Array<*> -> JsonArray(v.map { of(it) })
        else -> JsonPrimitive(v.toString())
    }

    fun obj(vararg kv: Pair<String, Any?>): JsonObject = JsonObject(kv.associate { (k, v) -> k to of(v) })

    fun parse(s: String): JsonObject = Json.parseToJsonElement(s) as JsonObject

    fun str(o: JsonObject, k: String): String? = (o[k] as? JsonPrimitive)?.contentOrNull
    fun num(o: JsonObject, k: String): Double? = (o[k] as? JsonPrimitive)?.contentOrNull?.toDoubleOrNull()
    fun type(o: JsonObject): String? = o["type"]?.jsonPrimitive?.contentOrNull

    private fun round(d: Double): Double = Math.round(d * 1000.0) / 1000.0
}
