# kotlinx.serialization
-keepattributes *Annotation*, InnerClasses
-keepclassmembers class com.pokecollector.app.data.api.** { *** Companion; }
-keepclasseswithmembers class com.pokecollector.app.data.api.** { kotlinx.serialization.KSerializer serializer(...); }
