plugins {
    id("org.jetbrains.intellij") version "1.17.0"
    kotlin("jvm") version "1.9.0"
}

group = "com.example"
version = "1.0-SNAPSHOT"

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.json:json:20230227")
}


intellij {
    localPath.set("C:\\Program Files\\JetBrains\\IntelliJ IDEA 2025.2.5")
    plugins.set(listOf("java", "com.intellij.platform.images"))
}

kotlin {
    jvmToolchain(17) // compile Kotlin to JVM 17 target
}

tasks.withType<org.jetbrains.kotlin.gradle.tasks.KotlinCompile> {
    kotlinOptions {
        jvmTarget = "17"
    }
}

tasks.withType<JavaExec> {
    // Change the debugger port from 5005 to 5006 to free up 5005 for your HTTP server.
    jvmArgs("-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=5006")
}

tasks {
    buildSearchableOptions {
        enabled = false
    }

    patchPluginXml {
        sinceBuild.set("252")
        untilBuild.set("255.*")
    }
}
