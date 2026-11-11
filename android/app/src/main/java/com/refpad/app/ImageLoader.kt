package com.refpad.app

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.ImageDecoder
import android.graphics.Matrix
import android.media.ExifInterface
import android.os.Build
import android.util.Log
import java.io.BufferedOutputStream
import java.io.File
import java.io.FileOutputStream
import kotlin.math.max
import kotlin.math.roundToInt

/** Decoding, saving and memory handling for pictures. Everything here runs on a background thread. */
object ImageLoader {
    private const val TAG = "RefPad"

    /** Long side of imported images. Plenty for references on a tablet, without wasting memory. */
    const val MAX_IMAGE_SIDE = 1600

    /** Decodes an image file, shrunk so its long side is at most [maxSide]. Returns a normal (CPU) bitmap. */
    fun decodeFile(file: File, maxSide: Int = MAX_IMAGE_SIDE): Bitmap? {
        if (Build.VERSION.SDK_INT >= 28) {
            try {
                return ImageDecoder.decodeBitmap(ImageDecoder.createSource(file)) { decoder, info, _ ->
                    decoder.allocator = ImageDecoder.ALLOCATOR_SOFTWARE
                    val w = info.size.width
                    val h = info.size.height
                    val longSide = max(w, h)
                    if (longSide > maxSide) {
                        val s = maxSide.toFloat() / longSide
                        decoder.setTargetSize(max(1, (w * s).roundToInt()), max(1, (h * s).roundToInt()))
                    }
                }
            } catch (e: OutOfMemoryError) {
                Log.w(TAG, "Out of memory decoding ${file.name}", e)
                return null
            } catch (e: Exception) {
                Log.w(TAG, "ImageDecoder could not read ${file.name}, trying BitmapFactory", e)
            }
        }
        return decodeLegacy(file, maxSide)
    }

    private fun decodeLegacy(file: File, maxSide: Int): Bitmap? {
        try {
            val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeFile(file.path, bounds)
            if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return null
            var sample = 1
            while (max(bounds.outWidth, bounds.outHeight) / (sample * 2) >= maxSide) sample *= 2
            val bmp = BitmapFactory.decodeFile(file.path, BitmapFactory.Options().apply { inSampleSize = sample })
                ?: return null
            return applyExifOrientation(scaleDown(bmp, maxSide), file)
        } catch (e: OutOfMemoryError) {
            Log.w(TAG, "Out of memory decoding ${file.name}", e)
        } catch (e: Exception) {
            Log.w(TAG, "Could not decode ${file.name}", e)
        }
        return null
    }

    private fun scaleDown(bmp: Bitmap, maxSide: Int): Bitmap {
        val longSide = max(bmp.width, bmp.height)
        if (longSide <= maxSide) return bmp
        val s = maxSide.toFloat() / longSide
        val out = Bitmap.createScaledBitmap(bmp, max(1, (bmp.width * s).roundToInt()), max(1, (bmp.height * s).roundToInt()), true)
        if (out !== bmp) bmp.recycle()
        return out
    }

    private fun applyExifOrientation(bmp: Bitmap, file: File): Bitmap {
        val orientation = try {
            ExifInterface(file.path).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)
        } catch (e: Exception) {
            ExifInterface.ORIENTATION_NORMAL
        }
        val m = Matrix()
        when (orientation) {
            ExifInterface.ORIENTATION_ROTATE_90 -> m.postRotate(90f)
            ExifInterface.ORIENTATION_ROTATE_180 -> m.postRotate(180f)
            ExifInterface.ORIENTATION_ROTATE_270 -> m.postRotate(270f)
            ExifInterface.ORIENTATION_FLIP_HORIZONTAL -> m.postScale(-1f, 1f)
            ExifInterface.ORIENTATION_FLIP_VERTICAL -> m.postScale(1f, -1f)
            else -> return bmp
        }
        val out = Bitmap.createBitmap(bmp, 0, 0, bmp.width, bmp.height, m, true)
        if (out !== bmp) bmp.recycle()
        return out
    }

    /**
     * Saves a compact copy (so the board can be restored later), then moves the pixels to GPU memory.
     * The [bmp] passed in must not be used afterwards.
     */
    fun store(bmp: Bitmap): RefImage {
        val id = Storage.newId()
        val (format, ext, quality) = when {
            !bmp.hasAlpha() -> Triple(Bitmap.CompressFormat.JPEG, "jpg", 90)
            Build.VERSION.SDK_INT >= 30 -> Triple(Bitmap.CompressFormat.WEBP_LOSSY, "webp", 90)
            else -> Triple(Bitmap.CompressFormat.PNG, "png", 100)
        }
        val name = "$id.$ext"
        val file = File(Storage.imgDir, name)
        try {
            Storage.imgDir.mkdirs()
            BufferedOutputStream(FileOutputStream(file), 64 * 1024).use { out ->
                if (!bmp.compress(format, quality, out)) Log.w(TAG, "Could not save $name")
            }
        } catch (e: Exception) {
            Log.w(TAG, "Could not save $name", e)
            file.delete()
        }
        val preview = makePreview(bmp)
        return RefImage(name, toDisplay(bmp), preview?.let { toDisplay(it) })
    }

    /** Long side of the small copy drawn when an image is small on screen. */
    private const val PREVIEW_SIDE = 512

    /** A good-looking small copy (halved step by step, which avoids jagged edges), or null if not needed. */
    private fun makePreview(src: Bitmap): Bitmap? {
        if (max(src.width, src.height) <= PREVIEW_SIDE * 1.3f) return null
        return try {
            var cur = src
            while (max(cur.width, cur.height) / 2 >= PREVIEW_SIDE) {
                val next = Bitmap.createScaledBitmap(cur, cur.width / 2, cur.height / 2, true)
                if (cur !== src) cur.recycle()
                cur = next
            }
            val s = PREVIEW_SIDE.toFloat() / max(cur.width, cur.height)
            val out = Bitmap.createScaledBitmap(cur, max(1, (cur.width * s).roundToInt()), max(1, (cur.height * s).roundToInt()), true)
            if (cur !== src && cur !== out) cur.recycle()
            out
        } catch (t: Throwable) {
            null
        }
    }

    /** Small copy of a saved image, decoded straight at preview size. */
    fun loadSavedPreview(file: File): Bitmap? {
        if (Build.VERSION.SDK_INT < 28 || !file.exists()) return null
        return try {
            ImageDecoder.decodeBitmap(ImageDecoder.createSource(file)) { decoder, info, _ ->
                val w = info.size.width
                val h = info.size.height
                val longSide = max(w, h)
                if (longSide > PREVIEW_SIDE * 1.3f) {
                    val s = PREVIEW_SIDE.toFloat() / longSide
                    decoder.setTargetSize(max(1, (w * s).roundToInt()), max(1, (h * s).roundToInt()))
                }
            }.takeIf { max(it.width, it.height) <= PREVIEW_SIDE * 1.3f }
        } catch (t: Throwable) {
            null
        }
    }

    /**
     * Android 8+: copies the pixels into GPU memory and frees the CPU copy.
     * This roughly halves memory use per image and makes drawing faster.
     */
    fun toDisplay(bmp: Bitmap): Bitmap {
        if (Build.VERSION.SDK_INT < 26 || bmp.config == Bitmap.Config.HARDWARE) return bmp
        return try {
            val hw = bmp.copy(Bitmap.Config.HARDWARE, false)
            if (hw != null) {
                bmp.recycle()
                hw
            } else bmp
        } catch (t: Throwable) {
            bmp
        }
    }

    /** Loads one of our own saved copies straight into GPU memory where possible. */
    fun loadSaved(file: File): Bitmap? {
        if (!file.exists()) return null
        return try {
            if (Build.VERSION.SDK_INT >= 28) {
                ImageDecoder.decodeBitmap(ImageDecoder.createSource(file))
            } else {
                val opts = BitmapFactory.Options()
                if (Build.VERSION.SDK_INT >= 26) opts.inPreferredConfig = Bitmap.Config.HARDWARE
                BitmapFactory.decodeFile(file.path, opts)
            }
        } catch (t: Throwable) {
            Log.w(TAG, "Could not restore ${file.name}", t)
            null
        }
    }
}
