package com.refpad.app

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.ColorMatrix
import android.os.Build
import android.graphics.ColorMatrixColorFilter
import android.graphics.Paint

/**
 * One decoded picture held in memory. Board items, practice poses and the clipboard all
 * point at the same RefImage, so copying or sending an image to practice costs no extra memory.
 * [fileName] is the saved copy inside the app's storage (used to restore the board after a restart).
 */
class RefImage(val fileName: String, val bitmap: Bitmap, private val preview: Bitmap? = null) {
    val width: Int get() = bitmap.width
    val height: Int get() = bitmap.height

    /**
     * The best bitmap for drawing at [screenLongSide] pixels. When an image is small on screen
     * the small preview is used: the GPU then reads far less memory, which keeps panning and
     * zooming a full board smooth at 120 Hz. Zoomed in, the full image is used.
     */
    fun bitmapFor(screenLongSide: Float): Bitmap {
        val p = preview ?: return bitmap
        return if (screenLongSide <= maxOf(p.width, p.height) * 1.15f) p else bitmap
    }
}

/** A single page in a practice session. PDF pages are rendered only when they are about to be shown. */
sealed class Pose {
    class Image(val image: RefImage) : Pose()
    class PdfPage(val docId: String, val page: Int) : Pose() {
        override fun equals(other: Any?) = other is PdfPage && other.docId == docId && other.page == page
        override fun hashCode() = docId.hashCode() * 31 + page
    }
}

/**
 * A PDF opened in the PDF viewer. Only page shapes are kept in memory;
 * pages are drawn on demand. [position] is the page at the top of the screen (page index + fraction).
 */
class ViewerDoc(val docId: String, val title: String, private val aspects: FloatArray, var position: Float = 0f) {
    val pageCount: Int get() = aspects.size

    /** Height divided by width for page [i]. */
    fun aspect(i: Int): Float = aspects.getOrElse(i) { 1.414f }

    fun aspectList(): FloatArray = aspects
}

/**
 * Images live in GPU memory ("hardware" bitmaps) for speed. Android occasionally draws a window in
 * software mode (while a window is closing, or when a screen-capture tool such as the S Pen's grabs it),
 * and drawing a GPU image there throws. Those rare frames simply skip the image instead of crashing.
 */
fun Canvas.canDraw(bitmap: Bitmap): Boolean =
    isHardwareAccelerated || Build.VERSION.SDK_INT < 26 || bitmap.config != Bitmap.Config.HARDWARE

/** Shared paints so every image does not carry its own set. */
object Paints {
    val normal = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)
    val gray = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG).apply {
        colorFilter = ColorMatrixColorFilter(ColorMatrix().apply { setSaturation(0f) })
    }
}
