package expo.modules.cardtext

import android.net.Uri
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import expo.modules.kotlin.Promise
import expo.modules.kotlin.exception.CodedException
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition

/** On-device text recognition (Google ML Kit) for photos of trading cards. */
class CardTextModule : Module() {
  private val recognizer by lazy { TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS) }

  override fun definition() = ModuleDefinition {
    Name("CardText")

    // Returns the text lines in the photo, top to bottom: [{ text, top, left }].
    AsyncFunction("recognize") { uri: String, promise: Promise ->
      val context = appContext.reactContext
        ?: return@AsyncFunction promise.reject(CodedException("No Android context"))
      val image = try {
        InputImage.fromFilePath(context, Uri.parse(uri))
      } catch (e: Exception) {
        return@AsyncFunction promise.reject(CodedException("Couldn't open image: ${e.message}", e))
      }
      recognizer.process(image)
        .addOnSuccessListener { text ->
          val lines = text.textBlocks
            .flatMap { it.lines }
            .sortedBy { it.boundingBox?.top ?: 0 }
            .map {
              mapOf(
                "text" to it.text,
                "top" to (it.boundingBox?.top ?: 0),
                "left" to (it.boundingBox?.left ?: 0),
              )
            }
          promise.resolve(lines)
        }
        .addOnFailureListener { e -> promise.reject(CodedException("Text recognition failed: ${e.message}", e)) }
    }

    OnDestroy { recognizer.close() }
  }
}
