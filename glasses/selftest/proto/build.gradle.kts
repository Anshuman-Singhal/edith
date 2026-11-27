// SDK-free selftest client logic (R4 nit 2): T9/T11/T13 protocol clients, results model,
// registry. Plain Kotlin/JVM + OkHttp so the D13a JVM test runs it against `selftest --serve`.
plugins { alias(libs.plugins.kotlin.jvm) }

// JVM 17 bytecode (PLAN §4.2) built by whatever JDK runs Gradle (21 here); no toolchain download.
java { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
kotlin { compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17) } }

dependencies {
    api(project(":platform-api"))
    api(libs.okhttp)
    api(libs.serialization.json)
    testImplementation(libs.junit)
}

val repoRoot = rootDir.parentFile

tasks.test {
    maxHeapSize = "1g"
    systemProperty("edith.repoRoot", repoRoot.absolutePath)
    // Optional override of the peer launcher, e.g. "python3" when aiohttp is installed system-wide.
    System.getenv("EDITH_PEER_PYTHON")?.let { environment("EDITH_PEER_PYTHON", it) }
    inputs.file(repoRoot.resolve("docs/bringup/registry/registry.json"))
    inputs.file(repoRoot.resolve("docs/bringup/results.schema.json"))
    inputs.file(repoRoot.resolve("tools/edith_tools/commands/g.py"))
    testLogging { events("passed", "failed", "skipped"); showStandardStreams = true; exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL }
}
