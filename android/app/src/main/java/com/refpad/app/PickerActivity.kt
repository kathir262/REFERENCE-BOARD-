package com.refpad.app

import android.app.Activity
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.ImageDecoder
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.MediaStore
import android.widget.Toast

class PickerActivity : Activity() {

    private val REQ_PICK_IMAGE = 1001
    private val REQ_PICK_PDF_REF = 1002
    private val REQ_PICK_PDF_PRACTICE = 1003

    private var currentAction: String? = null
    private var pickerLaunched = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        overridePendingTransition(0, 0)

        if (savedInstanceState != null && savedInstanceState.getBoolean("picker_launched", false)) {
            pickerLaunched = true
            return
        }

        currentAction = intent.getStringExtra("action")
        pickerLaunched = true

        when (currentAction) {
            "pick_image" -> {
                val intent = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    Intent(MediaStore.ACTION_PICK_IMAGES).apply {
                        type = "image/*"
                        putExtra(MediaStore.EXTRA_PICK_IMAGES_MAX, 20)
                    }
                } else {
                    Intent(Intent.ACTION_GET_CONTENT).apply {
                        type = "image/*"
                        putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
                        addCategory(Intent.CATEGORY_OPENABLE)
                    }
                }
                try {
                    startActivityForResult(intent, REQ_PICK_IMAGE)
                } catch (e: Exception) {
                    val fallback = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                        type = "image/*"
                        putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
                        addCategory(Intent.CATEGORY_OPENABLE)
                    }
                    startActivityForResult(fallback, REQ_PICK_IMAGE)
                }
            }
            "pick_pdf_ref" -> {
                val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    type = "application/pdf"
                }
                try {
                    startActivityForResult(intent, REQ_PICK_PDF_REF)
                } catch (e: Exception) {
                    val fallback = Intent(Intent.ACTION_GET_CONTENT).apply {
                        type = "application/pdf"
                        addCategory(Intent.CATEGORY_OPENABLE)
                    }
                    startActivityForResult(fallback, REQ_PICK_PDF_REF)
                }
            }
            "pick_pdf_practice" -> {
                val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    type = "application/pdf"
                }
                try {
                    startActivityForResult(intent, REQ_PICK_PDF_PRACTICE)
                } catch (e: Exception) {
                    val fallback = Intent(Intent.ACTION_GET_CONTENT).apply {
                        type = "application/pdf"
                        addCategory(Intent.CATEGORY_OPENABLE)
                    }
                    startActivityForResult(fallback, REQ_PICK_PDF_PRACTICE)
                }
            }
            else -> finish()
        }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        outState.putBoolean("picker_launched", pickerLaunched)
    }

    override fun finish() {
        super.finish()
        overridePendingTransition(0, 0)
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)

        if (resultCode != RESULT_OK || data == null) {
            finish()
            return
        }

        // Extract all URIs from both data.data and data.clipData
        val uris = mutableListOf<Uri>()
        data.data?.let { uris.add(it) }
        data.clipData?.let { clipData ->
            for (i in 0 until clipData.itemCount) {
                val u = clipData.getItemAt(i).uri
                if (!uris.contains(u)) uris.add(u)
            }
        }

        // Take persistable URI permissions if offered
        for (u in uris) {
            try {
                contentResolver.takePersistableUriPermission(u, Intent.FLAG_GRANT_READ_URI_PERMISSION)
            } catch (e: Exception) {}
        }

        Thread {
            try {
                when (requestCode) {
                    REQ_PICK_IMAGE -> {
                        val loadedBitmaps = mutableListOf<Bitmap>()
                        for (uri in uris) {
                            loadBitmapFromUri(uri)?.let { bmp ->
                                loadedBitmaps.add(bmp)
                            }
                        }

                        runOnUiThread {
                            for (bmp in loadedBitmaps) {
                                DataManager.addReference(bmp)
                            }
                            if (loadedBitmaps.isNotEmpty()) {
                                Toast.makeText(applicationContext, "Added ${loadedBitmaps.size} image(s)", Toast.LENGTH_SHORT).show()
                            } else {
                                Toast.makeText(applicationContext, "Could not load selected image", Toast.LENGTH_SHORT).show()
                            }
                            finish()
                        }
                    }

                    REQ_PICK_PDF_REF -> {
                        val loadedPages = mutableListOf<Bitmap>()
                        for (uri in uris) {
                            loadedPages.addAll(PdfHelper.renderPdfPages(this@PickerActivity, uri))
                        }

                        runOnUiThread {
                            for (page in loadedPages) {
                                DataManager.addReference(page)
                            }
                            if (loadedPages.isNotEmpty()) {
                                Toast.makeText(applicationContext, "Loaded ${loadedPages.size} PDF page(s)", Toast.LENGTH_SHORT).show()
                            } else {
                                Toast.makeText(applicationContext, "Could not load PDF pages", Toast.LENGTH_SHORT).show()
                            }
                            finish()
                        }
                    }

                    REQ_PICK_PDF_PRACTICE -> {
                        val loadedPages = mutableListOf<Bitmap>()
                        for (uri in uris) {
                            loadedPages.addAll(PdfHelper.renderPdfPages(this@PickerActivity, uri))
                        }

                        runOnUiThread {
                            DataManager.addPracticeImages(loadedPages)
                            if (loadedPages.isNotEmpty()) {
                                Toast.makeText(applicationContext, "Loaded ${loadedPages.size} pages to Practice Mode", Toast.LENGTH_SHORT).show()
                            } else {
                                Toast.makeText(applicationContext, "Could not load PDF pages", Toast.LENGTH_SHORT).show()
                            }
                            finish()
                        }
                    }
                    else -> runOnUiThread { finish() }
                }
            } catch (e: Exception) {
                e.printStackTrace()
                runOnUiThread {
                    Toast.makeText(applicationContext, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                    finish()
                }
            }
        }.start()
    }

    private fun loadBitmapFromUri(uri: Uri): Bitmap? {
        // Try ImageDecoder on Android 28+ for hardware-assisted, zero-fail decode
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            try {
                val source = ImageDecoder.createSource(contentResolver, uri)
                return ImageDecoder.decodeBitmap(source) { decoder, info, _ ->
                    decoder.allocator = ImageDecoder.ALLOCATOR_SOFTWARE
                    val maxDim = 1600
                    val size = info.size
                    if (size.width > maxDim || size.height > maxDim) {
                        val ratio = maxDim.toFloat() / Math.max(size.width, size.height)
                        decoder.setTargetSize(Math.max(1, (size.width * ratio).toInt()), Math.max(1, (size.height * ratio).toInt()))
                    }
                }
            } catch (e: Throwable) {
                e.printStackTrace()
            }
        }

        // Stream byte buffer fallback
        val bytes = try {
            contentResolver.openInputStream(uri)?.use { it.readBytes() }
        } catch (e: Exception) {
            try {
                contentResolver.openFileDescriptor(uri, "r")?.use { pfd ->
                    java.io.FileInputStream(pfd.fileDescriptor).use { it.readBytes() }
                }
            } catch (e2: Exception) {
                e2.printStackTrace()
                null
            }
        } ?: return null

        if (bytes.isEmpty()) return null

        try {
            val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options)

            val maxDimension = 1600
            var inSampleSize = 1
            if (options.outHeight > maxDimension || options.outWidth > maxDimension) {
                val halfHeight = options.outHeight / 2
                val halfWidth = options.outWidth / 2
                while (halfHeight / inSampleSize >= maxDimension || halfWidth / inSampleSize >= maxDimension) {
                    inSampleSize *= 2
                }
            }

            val loadOptions = BitmapFactory.Options().apply {
                this.inSampleSize = inSampleSize
                inPreferredConfig = Bitmap.Config.ARGB_8888
            }
            return BitmapFactory.decodeByteArray(bytes, 0, bytes.size, loadOptions)
        } catch (oom: OutOfMemoryError) {
            oom.printStackTrace()
            return null
        } catch (e: Exception) {
            e.printStackTrace()
            return null
        }
    }
}
