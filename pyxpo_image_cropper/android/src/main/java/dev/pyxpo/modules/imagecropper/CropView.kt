package dev.pyxpo.modules.imagecropper

import android.app.Activity
import android.graphics.Bitmap
import android.graphics.Color
import android.net.Uri
import com.canhub.cropper.CropImageView
import dev.pyxpo.moduleapi.PxNativeView
import dev.pyxpo.moduleapi.PxReply
import org.json.JSONObject
import java.io.File
import java.util.UUID

/** The inline editor: a CanHub CropImageView the app drives with its own buttons. */
class CropView(private val activity: Activity, private val emit: (String, Any?) -> Unit) : PxNativeView {
    private val crop = CropImageView(activity).apply {
        setBackgroundColor(Color.BLACK)
        isAutoZoomEnabled = true
        isShowProgressBar = true
        guidelines = CropImageView.Guidelines.ON
    }
    override val view = crop

    private var source = ""
    private var ratioX = 0
    private var ratioY = 0
    private var circle = false
    private var resettable = false
    private var pending: Pair<File, PxReply>? = null

    init {
        crop.setOnSetImageUriCompleteListener { _, _, error ->
            if (error != null) emit("error", mapOf("message" to (error.message ?: "cannot open the photo at $source")))
            applyShape()
            report()
        }
        crop.setOnSetCropOverlayReleasedListener { report() }
        crop.setOnCropImageCompleteListener { _, result ->
            val (out, reply) = pending ?: return@setOnCropImageCompleteListener
            pending = null
            val err = if (result.isSuccessful) ImageCropperModule.save(activity, result.uriContent, out) else result.error?.message ?: "the crop failed"
            if (err == null) reply(ImageCropperModule.describe(out, out.name.endsWith(".png")), null)
            else reply(null, err)
        }
    }

    override fun update(props: JSONObject, removed: Set<String>) {
        var shape = false
        if (props.has("circle")) { val c = props.optBoolean("circle"); shape = shape || c != circle; circle = c }
        if (props.has("ratio_x") || props.has("ratio_y")) {
            val x = props.optInt("ratio_x", ratioX)
            val y = props.optInt("ratio_y", ratioY)
            shape = shape || x != ratioX || y != ratioY
            ratioX = x
            ratioY = y
        }
        if (props.has("grid")) crop.guidelines = if (props.optBoolean("grid", true)) CropImageView.Guidelines.ON else CropImageView.Guidelines.OFF
        val s = props.optString("source", source)
        if (s.isNotEmpty() && s != source) {
            source = s
            val uri = if (s.startsWith("file://") || s.startsWith("content://")) Uri.parse(s) else Uri.fromFile(File(s))
            crop.setImageUriAsync(uri)  // the shape is applied when it has loaded
        } else if (shape) {
            applyShape()
        }
    }

    override fun dispose() {
        pending?.second?.invoke(null, "the CropView was removed")
        pending = null
    }

    fun rotate(clockwise: Boolean) {
        crop.rotateImage(if (clockwise) 90 else -90)
        report()
    }

    fun flip(horizontal: Boolean) {
        if (horizontal) crop.flipImageHorizontally() else crop.flipImageVertically()
        report()
    }

    fun reset() {
        crop.rotatedDegrees = 0
        crop.isFlippedHorizontally = false
        crop.isFlippedVertically = false
        crop.resetCropRect()
        applyShape()
        report()
    }

    fun cropTo(o: JSONObject, reply: PxReply) {
        if (pending != null) { reply(null, "a crop is already running"); return }
        val png = o.optString("format", "jpeg") == "png"
        val out = File(File(activity.cacheDir, "pyxpo-cropped").apply { mkdirs() }, UUID.randomUUID().toString() + if (png) ".png" else ".jpg")
        pending = out to reply
        crop.croppedImageAsync(if (png) Bitmap.CompressFormat.PNG else Bitmap.CompressFormat.JPEG,
                               (o.optDouble("quality", 0.9) * 100).toInt().coerceIn(0, 100), 0, 0,
                               CropImageView.RequestSizeOptions.NONE, null)
    }

    private fun applyShape() {
        crop.cropShape = if (circle) CropImageView.CropShape.OVAL else CropImageView.CropShape.RECTANGLE
        when {
            circle -> crop.setAspectRatio(1, 1)
            ratioX > 0 && ratioY > 0 -> crop.setAspectRatio(ratioX, ratioY)
            else -> crop.clearAspectRatio()
        }
    }

    private fun report() {
        val whole = crop.wholeImageRect
        val now = crop.rotatedDegrees % 360 != 0 || crop.isFlippedHorizontally || crop.isFlippedVertically ||
            (whole != null && crop.cropRect != null && crop.cropRect != whole)
        if (now == resettable) return
        resettable = now
        emit("change", mapOf("resettable" to now))
    }
}
