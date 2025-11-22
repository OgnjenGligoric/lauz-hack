plugins {
    id("org.jetbrains.intellij") version "1.17.0"
    kotlin("jvm") version "1.9.0"
}

group = "com.example"
version = "1.0-SNAPSHOT"

repositories {
    mavenCentral()
}

intellij {
    version.set("2023.2")
    type.set("IC")
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

tasks {
    patchPluginXml {
        sinceBuild.set("232")
        untilBuild.set("232.*")
    }
}
