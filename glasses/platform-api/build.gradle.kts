// Pure Kotlin/JVM: the GlassesPlatform interfaces and SDK-free helpers. No Android, no com.ffalcon.
plugins { alias(libs.plugins.kotlin.jvm) }

// JVM 17 bytecode (PLAN §4.2) built by whatever JDK runs Gradle (21 here); no toolchain download.
java { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
kotlin { compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17) } }

dependencies {
    testImplementation(libs.junit)
}
