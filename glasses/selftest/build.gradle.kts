// :selftest — standalone bring-up APK (D13a, C74, C104). Flavors: `rayneo` (only when the local
// Mercury repo exists, C44) and `generic` (any Android phone; for dev and CI without the SDK).
plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
}

val hasRayneoSdk = rootProject.extra["hasRayneoSdk"] as Boolean
val repoRoot = rootDir.parentFile

android {
    namespace = "edith.selftest"
    compileSdk = 36
    defaultConfig {
        applicationId = "edith.selftest"
        minSdk = 29
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0-d13a"
        buildConfigField("String", "GIT_REV", "\"${gitRev()}\"")
    }
    buildFeatures { buildConfig = true }
    flavorDimensions += "platform"
    productFlavors {
        if (hasRayneoSdk) create("rayneo") { dimension = "platform" }
        create("generic") { dimension = "platform"; applicationIdSuffix = ".generic" }
    }
    // The test registry generated from docs/bringup/TESTS.md ships as an asset (no copy in git).
    sourceSets["main"].assets.srcDir(repoRoot.resolve("docs/bringup/registry"))
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    packaging { resources.excludes += setOf("META-INF/*.kotlin_module", "META-INF/versions/**") }
    lint { abortOnError = false; checkReleaseBuilds = false }
    testOptions { unitTests { isIncludeAndroidResources = true; all { it.maxHeapSize = "1g" } } }
}

kotlin { compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17) } }

fun gitRev(): String = try {
    providers.exec { commandLine("git", "-C", repoRoot.path, "rev-parse", "--short", "HEAD"); isIgnoreExitValue = true }
        .standardOutput.asText.get().trim().ifEmpty { "unknown" }
} catch (_: Exception) { "unknown" }

dependencies {
    implementation(project(":platform-api"))
    implementation(project(":platform-generic"))
    implementation(project(":selftest-proto"))
    implementation(libs.okhttp)
    implementation(libs.appcompat)
    implementation(libs.lifecycle.runtime.ktx)
    if (hasRayneoSdk) "rayneoImplementation"(project(":platform-rayneo"))
    testImplementation(libs.junit)
    testImplementation(libs.robolectric)
    testImplementation(libs.androidx.test.core)
}
