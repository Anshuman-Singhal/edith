package edith.selftest.proto

import kotlinx.serialization.json.JsonObject
import java.io.File
import java.time.Instant
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter

/** Status values allowed by docs/bringup/results.schema.json. */
enum class Status(val wire: String) {
    PASS("pass"), FAIL("fail"),
    /** Measured, but the pass decision needs a human or a longer run (e.g. T14 durations). */
    MEASURED("measured"),
    INCOMPLETE("incomplete"), ERROR("error"), SKIPPED("skipped"), NOT_IMPLEMENTED("not_implemented"),
}

/** One test's entry in results.json. Mutable while the test runs; errors never abort a test run. */
class TestResult(val id: String, val name: String) {
    var status: Status = Status.INCOMPLETE
    val startedAt: String = Results.isoNow()
    var endedAt: String? = null
    val metrics = linkedMapOf<String, Any?>()
    val errors = mutableListOf<String>()
    val operator = linkedMapOf<String, Any?>()
    var passCriterion: String? = null

    fun error(where: String, t: Throwable) { errors += "$where: ${t.javaClass.simpleName}: ${t.message}" }

    /** Runs [block], recording any exception as an error instead of propagating it. */
    inline fun <T> guard(where: String, block: () -> T): T? = try { block() } catch (t: Throwable) { error(where, t); null }

    fun finish(s: Status) { status = s; endedAt = Results.isoNow() }

    fun toJson(): JsonObject = J.obj(
        "id" to id, "name" to name, "status" to status.wire,
        "started_at" to startedAt, "ended_at" to endedAt,
        "pass_criterion" to passCriterion,
        "metrics" to metrics, "errors" to errors, "operator" to operator,
    )
}

/**
 * The results document (schema `edith.bringup.results/v1`, docs/bringup/results.schema.json),
 * rewritten atomically after every test so a crash loses at most the running test.
 */
class Results(
    val dir: File,
    val runId: String = runIdNow(),
    val app: Map<String, Any?>,
    val device: Map<String, String>,
) {
    val createdAt: String = isoNow()
    var display: Map<String, Any?> = emptyMap()
    var provisioning: Map<String, Any?> = emptyMap()
    private val tests = linkedMapOf<String, TestResult>()

    val file: File get() = File(dir, "results.json")

    @Synchronized fun put(r: TestResult) { tests[r.id] = r; write() }

    @Synchronized fun get(id: String): TestResult? = tests[id]

    @Synchronized fun toJson(): JsonObject = J.obj(
        "schema" to SCHEMA, "run_id" to runId,
        "created_at" to createdAt, "updated_at" to isoNow(),
        "app" to app, "device" to device, "display" to display, "provisioning" to provisioning,
        "tests" to tests.mapValues { it.value.toJson() },
    )

    @Synchronized fun write() {
        dir.mkdirs()
        val tmp = File(dir, "results.json.tmp")
        tmp.writeText(J.pretty.encodeToString(JsonObject.serializer(), toJson()))
        if (!tmp.renameTo(file)) { file.delete(); tmp.renameTo(file) }
    }

    companion object {
        const val SCHEMA = "edith.bringup.results/v1"
        private val RUN_ID = DateTimeFormatter.ofPattern("yyyyMMdd'T'HHmmss'Z'").withZone(ZoneOffset.UTC)
        fun runIdNow(): String = RUN_ID.format(Instant.now())
        fun isoNow(): String = DateTimeFormatter.ISO_INSTANT.format(Instant.now())
    }
}
