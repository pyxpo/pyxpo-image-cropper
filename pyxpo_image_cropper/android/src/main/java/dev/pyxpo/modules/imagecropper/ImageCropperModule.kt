package dev.pyxpo.modules.imagecropper

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Build
import android.os.Bundle
import com.canhub.cropper.CropImage
import com.canhub.cropper.CropImageActivity
import com.canhub.cropper.CropImageOptions
import com.canhub.cropper.CropImageView
import dev.pyxpo.moduleapi.PxModule
import dev.pyxpo.moduleapi.PxModuleContext
import dev.pyxpo.moduleapi.PxNativeView
import dev.pyxpo.moduleapi.PxReply
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.UUID

/**
 * Full-screen cropper on the CanHub Android-Image-Cropper, and the inline `PxCropView` editor ([CropView]): free or
 * fixed aspect ratio, oval guide, rotate, flip and pinch zoom. The cropped photo is written to the app cache as a new
 * file, so `uri` is a local path.
 */
class ImageCropperModule : PxModule() {
    override val name = "ImageCropper"
    override val viewTypes = setOf("PxCropView")
    @Volatile private var busy = false

    override fun makeView(ctx: PxModuleContext, type: String, emit: (name: String, value: Any?) -> Unit): PxNativeView =
        CropView(ctx.activity, emit)

    override fun call(ctx: PxModuleContext, method: String, args: JSONArray, reply: PxReply) {
        fun view(): CropView? = (ctx.view(args.optInt(0, -1)) as? CropView).also { if (it == null) reply(null, "the CropView is not mounted") }
        when (method) {
            "crop" -> crop(ctx, args, reply)
            "rotate" -> view()?.let { it.rotate(args.optBoolean(1, true)); reply(null, null) }
            "flip" -> view()?.let { it.flip(args.optBoolean(1, true)); reply(null, null) }
            "reset" -> view()?.let { it.reset(); reply(null, null) }
            "cropView" -> view()?.cropTo(args.optJSONObject(1) ?: JSONObject(), reply)
            else -> reply(null, "unknown native call ImageCropper.$method")
        }
    }

    private fun crop(ctx: PxModuleContext, args: JSONArray, reply: PxReply) {
        if (busy) { reply(null, "a cropper is already open"); return }
        val raw = args.optString(0, "")
        if (raw.isEmpty()) { reply(null, "no photo to crop"); return }
        val source = if (raw.startsWith("file://") || raw.startsWith("content://")) Uri.parse(raw) else Uri.fromFile(File(raw))
        val o = args.optJSONObject(1) ?: JSONObject()
        val png = o.optString("format", "jpeg") == "png"
        val a = ctx.activity
        val out = File(File(a.cacheDir, "pyxpo-cropped").apply { mkdirs() }, UUID.randomUUID().toString() + if (png) ".png" else ".jpg")
        val opts = CropImageOptions().apply {
            val rx = o.optInt("ratioX", 0)
            val ry = o.optInt("ratioY", 0)
            if (rx > 0 && ry > 0) { aspectRatioX = rx; aspectRatioY = ry }
            fixAspectRatio = o.optBoolean("lock", false)
            if (o.optBoolean("circle", false)) cropShape = CropImageView.CropShape.OVAL
            guidelines = CropImageView.Guidelines.ON_TOUCH
            allowRotation = o.optBoolean("rotate", true)
            allowCounterRotation = allowRotation
            allowFlipping = o.optBoolean("flip", true)
            activityTitle = o.optString("title", "")
            outputCompressFormat = if (png) Bitmap.CompressFormat.PNG else Bitmap.CompressFormat.JPEG
            outputCompressQuality = (o.optDouble("quality", 0.9) * 100).toInt().coerceIn(0, 100)
            imageSourceIncludeGallery = false
            imageSourceIncludeCamera = false
        }
        val intent = Intent(a, CropImageActivity::class.java).putExtra(CropImage.CROP_IMAGE_EXTRA_BUNDLE, Bundle(2).apply {
            putParcelable(CropImage.CROP_IMAGE_EXTRA_SOURCE, source)
            putParcelable(CropImage.CROP_IMAGE_EXTRA_OPTIONS, opts)
        })
        busy = true
        try {
            ctx.startForResult(intent) { code, data ->
                busy = false
                val result = data?.let { cropResult(it) }
                when {
                    code == CropImage.CROP_IMAGE_ACTIVITY_RESULT_ERROR_CODE ->
                        reply(null, result?.error?.message ?: "the cropper failed")
                    code != Activity.RESULT_OK || result == null || !result.isSuccessful -> reply(mapOf("canceled" to true), null)
                    else -> save(a, result.uriContent, out)?.let { reply(null, it) } ?: reply(describe(out, png), null)
                }
            }
        } catch (e: Throwable) {
            busy = false
            reply(null, e.message ?: e.toString())
        }
    }

    @Suppress("DEPRECATION")
    private fun cropResult(data: Intent): CropImage.ActivityResult? =
        if (Build.VERSION.SDK_INT >= 33) data.getParcelableExtra(CropImage.CROP_IMAGE_EXTRA_RESULT, CropImage.ActivityResult::class.java)
        else data.getParcelableExtra(CropImage.CROP_IMAGE_EXTRA_RESULT)

    companion object {
        /** CanHub writes only to its own content:// file, so copy that into [out]. Returns an error message or null. */
        fun save(ctx: Context, from: Uri?, out: File): String? = try {
            val input = from?.let { ctx.contentResolver.openInputStream(it) } ?: return "the cropper returned no file"
            input.use { i -> out.outputStream().use { i.copyTo(it) } }
            null
        } catch (e: Exception) {
            e.message ?: e.toString()
        }

        fun describe(file: File, png: Boolean): Map<String, Any?> {
            val b = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeFile(file.path, b)
            return mapOf("canceled" to false, "uri" to file.path, "width" to b.outWidth, "height" to b.outHeight,
                         "fileSize" to file.length(), "mimeType" to if (png) "image/png" else "image/jpeg")
        }
    }
}
