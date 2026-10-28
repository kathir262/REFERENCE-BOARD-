package com.refpad.app

import android.app.Activity
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Bundle
import android.widget.Toast

class PickerActivity : Activity() {

    private val REQ_PICK_IMAGE = 1001
    private val REQ_PICK_PDF_REF = 1002
    private val REQ_PICK_PDF_PRACTICE = 1003

    private var currentAction: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        overridePendingTransition(0, 0)
        currentAction = intent.getStringExtra("action")

        when (currentAction) {
            "pick_image" -> {
                val intent = Intent(Intent.ACTION_GET_CONTENT).apply {
                    type = "image/*"
                    putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
                    addCategory(Intent.CATEGORY_OPENABLE)
                }
                try {
                    startActivityForResult(Intent.createChooser(intent, "Select Images"), REQ_PICK_IMAGE)
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
                val pickIntent = Intent(Intent.ACTION_GET_CONTENT).apply {
                    type = "application/pdf"
                    addCategory(Intent.CATEGORY_OPENABLE)
                }
                try {
                    startActivityForResult(Intent.createChooser(pickIntent, "Select PDF"), REQ_PICK_PDF_REF)
                } catch (e: Exception) {
                    val fallback = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                        type = "application/pdf"
                        addCategory(Intent.CATEGORY_OPENABLE)
                    }
                    startActivityForResult(fallback, REQ_PICK_PDF_REF)
                }
            }
            "pick_pdf_practice" -> {
                val pickIntent = Intent(Intent.ACTION_GET_CONTENT).apply {
                    type = "application/pdf"
                    addCategory(Intent.CATEGORY_OPENABLE)
                }
                try {
                    startActivityForResult(Intent.createChooser(pickIntent, "Select PDF"), REQ_PICK_PDF_PRACTICE)
                } catch (e: Exception) {
                    val fallback = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                        type = "application/pdf"
                        addCategory(Intent.CATEGORY_OPENABLE)
                    }
                    startActivityForResult(fallback, REQ_PICK_PDF_PRACTICE)
                }
            }
            else -> finish()
        }
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

        Thread {
            try {
                when (requestCode) {
                    REQ_PICK_IMAGE -> {
                        val uris = mutableListOf<Uri>()
                        val clipData = data.clipData
                        if (clipData != null) {
                            for (i in 0 until clipData.itemCount) {
                                uris.add(clipData.getItemAt(i).uri)
                            }
                        } else {
                            data.data?.let { uris.add(it) }
                        }

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
                                Toast.makeText(this@PickerActivity, "Added ${loadedBitmaps.size} image(s)", Toast.LENGTH_SHORT).show()
                            } else {
                                Toast.makeText(this@PickerActivity, "Could not load selected image", Toast.LENGTH_SHORT).show()
                            }
                            finish()
                        }
                    }

                    REQ_PICK_PDF_REF -> {
                        data.data?.let { uri ->
                            val pages = PdfHelper.renderPdfPages(this@PickerActivity, uri)
                            runOnUiThread {
                                for (page in pages) {
                                    DataManager.addReference(page)
                                }
                                if (pages.isNotEmpty()) {
                                    Toast.makeText(this@PickerActivity, "Loaded ${pages.size} PDF page(s)", Toast.LENGTH_SHORT).show()
                                } else {
                                    Toast.makeText(this@PickerActivity, "Could not load PDF pages", Toast.LENGTH_SHORT).show()
                                }
                                finish()
                            }
                        } ?: runOnUiThread { finish() }
                    }

                    REQ_PICK_PDF_PRACTICE -> {
                        data.data?.let { uri ->
                            val pages = PdfHelper.renderPdfPages(this@PickerActivity, uri)
                            runOnUiThread {
                                DataManager.addPracticeImages(pages)
                                if (pages.isNotEmpty()) {
                                    Toast.makeText(this@PickerActivity, "Loaded ${pages.size} pages to Practice Mode", Toast.LENGTH_SHORT).show()
                                }
                                finish()
                            }
                        } ?: runOnUiThread { finish() }
                    }
                    else -> runOnUiThread { finish() }
                }
            } catch (e: Exception) {
                e.printStackTrace()
                runOnUiThread {
                    Toast.makeText(this@PickerActivity, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                    finish()
                }
            }
        }.start()
    }

    private fun loadBitmapFromUri(uri: Uri): Bitmap? {
        return try {
            val bytes = contentResolver.openInputStream(uri)?.use { it.readBytes() } ?: return null
            if (bytes.isEmpty()) return null

            val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options)

            val maxDimension = 2048
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
            BitmapFactory.decodeByteArray(bytes, 0, bytes.size, loadOptions)
        } catch (e: Exception) {
            e.printStackTrace()
            null
        }
    }
}
