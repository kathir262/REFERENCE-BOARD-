package com.refpad.app

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.os.Handler
import android.os.Looper
import android.os.Process
import android.util.Log
import java.io.File
import java.util.Locale
import java.util.concurrent.Executors
import kotlin.math.max
import kotlin.math.roundToInt

/**
 * Value steps (the picture in 2–5 greys) and squint (blurred) versions of board pictures.
 * They are made once in the background and kept in a small memory-limited cache; until one is ready
 * the board shows the picture in black & white.
 */
object Looks {
    private const val TAG = "RefPad"
    /** Long side of a made look; value studies need no fine detail. */
    private const val SIDE = 1200
    private const val MAX_BYTES = 96L shl 20

    private val main = Handler(Looper.getMainLooper())
    private val worker = Executors.newSingleThreadExecutor { r ->
        Thread({
            Process.setThreadPriority(Process.THREAD_PRIORITY_BACKGROUND)
            r.run()
        }, "refpad-looks")
    }
    private val cache = LinkedHashMap<String, Bitmap>(16, 0.75f, true)
    private val pending = HashSet<String>()
    /** Looks that could not be made (not tried again until the app restarts). */
    private val failed = HashSet<String>()
    private var bytes = 0L
    private val listeners = ArrayList<() -> Unit>()

    fun addListener(l: () -> Unit) {
        if (!listeners.contains(l)) listeners.add(l)
    }

    fun removeListener(l: () -> Unit) {
        listeners.remove(l)
    }

    /** The look for [image], or null while it is being made (main thread). */
    fun get(image: RefImage, values: Int, blur: Boolean): Bitmap? {
        val key = "${image.fileName}|$values|$blur"
        cache[key]?.let { return it }
        if (key in failed) return null
        if (pending.add(key)) {
            worker.execute {
                val made = try {
                    source(image)?.let { make(it, values, blur) }?.let { ImageLoader.toDisplay(it) }
                } catch (t: Throwable) {
                    Log.w(TAG, "Look failed", t)
                    null
                }
                main.post {
                    pending.remove(key)
                    if (made == null) failed.add(key)
                    if (made != null) {
                        cache[key] = made
                        bytes += made.byteCountEstimate()
                        trim()
                        for (l in listeners.toTypedArray()) l()
                    }
                }
            }
        }
        return null
    }

    private fun trim() {
        val it = cache.entries.iterator()
        while (bytes > MAX_BYTES && it.hasNext()) {
            val e = it.next()
            bytes -= e.value.byteCountEstimate()
            it.remove()
        }
    }

    private fun Bitmap.byteCountEstimate(): Long = width.toLong() * height * 4

    /** A normal (CPU) copy of the picture, read from its saved file. */
    fun source(image: RefImage, maxSide: Int = SIDE): Bitmap? {
        val file = File(Storage.imgDir, image.fileName)
        if (file.exists()) {
            val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeFile(file.path, bounds)
            var sample = 1
            while (max(bounds.outWidth, bounds.outHeight) / (sample * 2) >= maxSide) sample *= 2
            BitmapFactory.decodeFile(file.path, BitmapFactory.Options().apply {
                inSampleSize = sample
                inPreferredConfig = Bitmap.Config.ARGB_8888
            })?.let { return it }
        }
        // No file (should not happen): read the pixels back from the picture in memory.
        return try {
            image.bitmap.copy(Bitmap.Config.ARGB_8888, false)
        } catch (t: Throwable) {
            null
        }
    }

    /** Value steps, then squint (the same order as RefPad for Windows). Works on a CPU bitmap. */
    fun make(src: Bitmap, values: Int, blur: Boolean): Bitmap {
        var img = src
        if (values > 1) img = posterize(img, values)
        if (blur) img = squint(img)
        return img
    }

    fun posterize(src: Bitmap, steps: Int): Bitmap {
        val w = src.width
        val h = src.height
        val px = IntArray(w * h)
        src.getPixels(px, 0, w, 0, 0, w, h)
        val lut = IntArray(256) { i ->
            val v = ((i / 255f * (steps - 1)).roundToInt() * 255f / (steps - 1)).roundToInt()
            Color.rgb(v, v, v)
        }
        for (i in px.indices) {
            val c = px[i]
            px[i] = lut[luma(c)] and 0x00FFFFFF or (c and 0xFF000000.toInt())
        }
        return Bitmap.createBitmap(px, w, h, Bitmap.Config.ARGB_8888)
    }

    /** Blurred, like squinting at the subject: only the big shapes and values remain. */
    fun squint(src: Bitmap): Bitmap {
        val w = src.width
        val h = src.height
        val k = max(w, h) / 28f
        val small = Bitmap.createScaledBitmap(src, max(2, (w / k).roundToInt()), max(2, (h / k).roundToInt()), true)
        val mid = Bitmap.createScaledBitmap(small, max(2, w / 4), max(2, h / 4), true)
        return Bitmap.createScaledBitmap(mid, w, h, true)
    }

    /** Brightness 0..255 the way people see it (green counts most). */
    fun luma(c: Int): Int =
        ((Color.red(c) * 0.2126f + Color.green(c) * 0.7152f + Color.blue(c) * 0.0722f).roundToInt()).coerceIn(0, 255)

    /** "#7A5C3E · hue 30° · saturation 49% · brightness 48% · value 38%" */
    fun describe(c: Int): String {
        val hsv = FloatArray(3)
        Color.colorToHSV(c, hsv)
        val value = (luma(c) / 255f * 100).roundToInt()
        return String.format(
            Locale.US, "%s  ·  hue %d°  ·  saturation %d%%  ·  brightness %d%%  ·  value %d%%",
            hex(c), hsv[0].roundToInt(), (hsv[1] * 100).roundToInt(), (hsv[2] * 100).roundToInt(), value
        )
    }

    fun hex(c: Int) = String.format(Locale.US, "#%06X", c and 0xFFFFFF)
}
