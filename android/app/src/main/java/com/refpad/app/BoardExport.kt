package com.refpad.app

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.RectF
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.util.Log
import java.io.BufferedOutputStream
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt
import kotlin.math.sqrt

/** Saves the whole board as one PNG picture (to share, print, or use in another app). */
object BoardExport {
    private const val TAG = "RefPad"
    /** Long side and pixel count limits, so even a huge board fits in memory on a phone. */
    private const val MAX_SIDE = 4096
    private const val MAX_PIXELS = 16_000_000L
    private const val MARGIN = 40f

    private val main = Handler(Looper.getMainLooper())

    /** The file name the save screen suggests. */
    fun suggestedName(boardTitle: String) = boardTitle.replace(Regex("""[\\/:*?"<>|]"""), " ").trim().ifEmpty { "Board" } + ".png"

    /** Draws the board and writes it into [uri] (chosen by the user) in the background. */
    fun export(context: Context, uri: Uri) {
        val app = context.applicationContext
        val items = DataManager.items.map { it.snapshot() } // taken on the main thread
        if (items.isEmpty()) return
        val bg = when (DataManager.background) {
            DataManager.BG_GREY -> Color.parseColor("#76767A")
            DataManager.BG_LIGHT -> Color.parseColor("#E8E8EB")
            else -> Color.parseColor("#0E0E10")
        }
        DataManager.setStatus("Exporting the board…")
        Storage.io.execute {
            val error = try {
                val bmp = render(items, bg)
                app.contentResolver.openOutputStream(uri, "w")?.use { out ->
                    BufferedOutputStream(out, 256 * 1024).use { bmp.compress(Bitmap.CompressFormat.PNG, 100, it) }
                } ?: throw java.io.IOException("Can't write $uri")
                val size = "${bmp.width} × ${bmp.height}"
                bmp.recycle()
                main.post { DataManager.toast("Board saved as a picture · $size") }
                null
            } catch (oom: OutOfMemoryError) {
                Log.w(TAG, "Export ran out of memory", oom)
                "The board is too big to export on this device"
            } catch (e: Exception) {
                Log.w(TAG, "Export failed", e)
                "Couldn't save the picture"
            }
            main.post {
                DataManager.setStatus(null)
                if (error != null) DataManager.toast(error)
            }
        }
    }

    /** The board drawn into one picture (background thread). */
    private fun render(items: List<RefBoardItem>, bg: Int): Bitmap {
        val r = RectF()
        var l = Float.MAX_VALUE
        var t = Float.MAX_VALUE
        var rr = -Float.MAX_VALUE
        var b = -Float.MAX_VALUE
        for (it in items) {
            it.boundsInto(r)
            l = min(l, r.left)
            t = min(t, r.top)
            rr = max(rr, r.right)
            b = max(b, r.bottom)
        }
        l -= MARGIN
        t -= MARGIN
        val w = (rr + MARGIN - l).coerceAtLeast(1f)
        val h = (b + MARGIN - t).coerceAtLeast(1f)
        // Sharp enough to show every picture at its own resolution, within the size limits.
        var k = items.filter { !it.isNote }.maxOfOrNull { 1f / it.scale } ?: 1f
        k = min(k, MAX_SIDE / max(w, h))
        if (w * k * h * k > MAX_PIXELS) k = sqrt(MAX_PIXELS / (w * h.toDouble())).toFloat()
        val outW = (w * k).roundToInt().coerceAtLeast(1)
        val outH = (h * k).roundToInt().coerceAtLeast(1)
        val out = Bitmap.createBitmap(outW, outH, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(out)
        canvas.drawColor(bg)
        canvas.scale(k, k)
        canvas.translate(-l, -t)
        val paints = ItemPaints()
        val scratch = RectF()
        for (it in items) {
            val img = it.image
            if (img == null) {
                it.draw(canvas, scratch, k, paints)
                continue
            }
            // Only as many pixels as the picture takes up in the export.
            val cropShare = max(it.srcW / img.width, it.srcH / img.height).coerceIn(0.01f, 1f)
            val need = (max(it.width, it.height) * k / cropShare * 1.2f).roundToInt().coerceIn(64, ImageLoader.MAX_IMAGE_SIDE)
            var pic = Looks.source(img, need) ?: continue
            if (it.values > 0 || it.blur) pic = Looks.make(pic, it.values, it.blur)
            it.draw(canvas, scratch, k, paints, pic)
            pic.recycle()
        }
        return out
    }
}
