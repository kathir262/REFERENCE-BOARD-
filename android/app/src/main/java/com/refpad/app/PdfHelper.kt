package com.refpad.app

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.pdf.PdfRenderer
import android.net.Uri
import android.os.ParcelFileDescriptor
import java.io.File
import java.io.FileOutputStream

object PdfHelper {

    fun renderPdfPages(context: Context, uri: Uri, maxPages: Int = 30): List<Bitmap> {
        val bitmaps = mutableListOf<Bitmap>()
        val tempFile = File(context.cacheDir, "temp_render_${System.currentTimeMillis()}.pdf")

        try {
            // 1. Copy the PDF input stream to a local cache file so the ParcelFileDescriptor is 100% seekable
            var copied = false
            try {
                context.contentResolver.openInputStream(uri)?.use { input ->
                    FileOutputStream(tempFile).use { output ->
                        input.copyTo(output)
                    }
                }
                copied = true
            } catch (e: Exception) {
                e.printStackTrace()
            }

            // Fallback via ParcelFileDescriptor if stream copy failed
            if (!copied || !tempFile.exists() || tempFile.length() == 0L) {
                try {
                    context.contentResolver.openFileDescriptor(uri, "r")?.use { pfd ->
                        java.io.FileInputStream(pfd.fileDescriptor).use { input ->
                            FileOutputStream(tempFile).use { output ->
                                input.copyTo(output)
                            }
                        }
                    }
                    copied = true
                } catch (e2: Exception) {
                    e2.printStackTrace()
                }
            }

            if (!copied || !tempFile.exists() || tempFile.length() == 0L) {
                return emptyList()
            }

            // 2. Open seekable ParcelFileDescriptor from the local cached file
            ParcelFileDescriptor.open(tempFile, ParcelFileDescriptor.MODE_READ_ONLY).use { pfd ->
                PdfRenderer(pfd).use { renderer ->
                    val pageCount = Math.min(renderer.pageCount, maxPages)
                    for (i in 0 until pageCount) {
                        try {
                            val page = renderer.openPage(i)

                            // Keep dimensions sharp for anatomy/reference but memory-safe
                            val maxDim = 1024
                            var w = page.width
                            var h = page.height
                            if (w > maxDim || h > maxDim) {
                                val scale = maxDim.toFloat() / Math.max(w, h)
                                w = Math.max(1, (w * scale).toInt())
                                h = Math.max(1, (h * scale).toInt())
                            }

                            // Use RGB_565 (2 bytes per pixel) for maximum memory efficiency on mobile
                            val bitmap = Bitmap.createBitmap(w, h, Bitmap.Config.RGB_565)
                            bitmap.eraseColor(Color.WHITE)
                            page.render(bitmap, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                            page.close()

                            bitmaps.add(bitmap)
                        } catch (oom: OutOfMemoryError) {
                            oom.printStackTrace()
                            break
                        } catch (e: Exception) {
                            e.printStackTrace()
                        }
                    }
                }
            }
        } catch (e: Exception) {
            e.printStackTrace()
        } finally {
            try {
                if (tempFile.exists()) {
                    tempFile.delete()
                }
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }

        return bitmaps
    }
}
