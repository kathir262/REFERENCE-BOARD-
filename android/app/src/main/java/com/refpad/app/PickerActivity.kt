package com.refpad.app

import android.app.Activity
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Bundle
import java.io.InputStream

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
                val pickIntent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    type = "image/*"
                    putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
                }
                startActivityForResult(pickIntent, REQ_PICK_IMAGE)
            }
            "pick_pdf_ref" -> {
                val pickIntent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    type = "application/pdf"
                }
                startActivityForResult(pickIntent, REQ_PICK_PDF_REF)
            }
            "pick_pdf_practice" -> {
                val pickIntent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    type = "application/pdf"
                }
                startActivityForResult(pickIntent, REQ_PICK_PDF_PRACTICE)
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

                        for (uri in uris) {
                            loadBitmapFromUri(uri)?.let { bmp ->
                                runOnUiThread {
                                    DataManager.addReference(bmp)
                                }
                            }
                        }
                    }

                    REQ_PICK_PDF_REF -> {
                        data.data?.let { uri ->
                            val pages = PdfHelper.renderPdfPages(this@PickerActivity, uri)
                            runOnUiThread {
                                for (page in pages) {
                                    DataManager.addReference(page)
                                }
                            }
                        }
                    }

                    REQ_PICK_PDF_PRACTICE -> {
                        data.data?.let { uri ->
                            val pages = PdfHelper.renderPdfPages(this@PickerActivity, uri)
                            runOnUiThread {
                                DataManager.addPracticeImages(pages)
                            }
                        }
                    }
                }
            } catch (e: Exception) {
                e.printStackTrace()
            } finally {
                runOnUiThread {
                    // Instantly finish so user stays right in their drawing app!
                    finish()
                }
            }
        }.start()
    }

    private fun loadBitmapFromUri(uri: Uri): Bitmap? {
        return try {
            val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            var input: InputStream? = contentResolver.openInputStream(uri)
            BitmapFactory.decodeStream(input, null, options)
            input?.close()

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
            input = contentResolver.openInputStream(uri)
            val bmp = BitmapFactory.decodeStream(input, null, loadOptions)
            input?.close()
            bmp
        } catch (e: Exception) {
            e.printStackTrace()
            null
        }
    }
}
