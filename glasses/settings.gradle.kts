// E.D.I.T.H. glasses build (WS-G). PLAN §3.8, §4.2; C44, C74.
pluginManagement {
    repositories { google(); mavenCentral(); gradlePluginPortal() }
}

// The RayNeo Mercury SDK is never committed. tools/fetch_rayneo_sdk.sh builds this local
// Maven repo (AAR + generated POM) from the vendor sample zip.
val mercuryDir = file("platform-rayneo/libs/m2/com/ffalcon/mercury-sdk/0.2.6")
val hasRayneoSdk = file("$mercuryDir/mercury-sdk-0.2.6.aar").isFile &&
    file("$mercuryDir/mercury-sdk-0.2.6.pom").isFile

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
        if (hasRayneoSdk) {
            maven(uri("platform-rayneo/libs/m2")) { content { includeGroup("com.ffalcon") } }
        }
    }
}

rootProject.name = "edith-glasses"

include(":platform-api", ":platform-generic", ":selftest-proto", ":selftest")
project(":selftest-proto").projectDir = file("selftest/proto")

if (hasRayneoSdk) {
    include(":platform-rayneo")
} else {
    logger.warn(
        "WARNING: RayNeo Mercury SDK not found at glasses/${mercuryDir.relativeTo(rootDir)}. " +
            ":platform-rayneo and the 'rayneo' flavors are skipped. " +
            "Run: tools/fetch_rayneo_sdk.sh --from <RayNeo sample zip>"
    )
}

// Later workstreams slot in when their directories exist (WS-H: hud-core, emulator-desktop; D12: app-android).
for (name in listOf("hud-core", "emulator-desktop", "app-android")) {
    if (file("$name/build.gradle.kts").isFile) include(":$name")
}
