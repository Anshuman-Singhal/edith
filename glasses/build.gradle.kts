// Root build: plugin versions come from gradle/libs.versions.toml (PLAN §4.2).
plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.android.library) apply false
    alias(libs.plugins.kotlin.android) apply false
    alias(libs.plugins.kotlin.jvm) apply false
    alias(libs.plugins.kotlin.multiplatform) apply false
    alias(libs.plugins.kotlin.compose) apply false
    alias(libs.plugins.kotlin.serialization) apply false
}

/** True when tools/fetch_rayneo_sdk.sh has built the local Mercury repo (see settings.gradle.kts). */
extra["hasRayneoSdk"] = findProject(":platform-rayneo") != null
