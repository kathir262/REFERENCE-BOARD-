package com.refpad.app

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.DocumentsContract
import android.provider.Settings
import android.widget.Button
import android.widget.Toast
import java.io.InputStream

class MainActivity : Activity() {

    private val OVERLAY_PERMISSION_REQ_CODE = 1234
    private val PICK_IMAGES_REQ_CODE = 2345
    private val PICK_PDF_REQ_CODE = 3456
    private val PICK_FOLDER_REQ_CODE = 4567

    private var pendingTargetMode = 0 // 0: Reference Board, 1: Practice Mode

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        findViewById<Button>(R.id.btn_launch_overlay).setOnClickListener {
            checkOverlayPermissionAndLaunch()
        }

        findViewById<Button>(R.id.btn_pick_images).setOnClickListener {
            promptDestinationDialog { targetMode ->
                pendingTargetMode = targetMode
                val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    type = "image/*"
                    putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
                }
                startActivityForResult(intent, PICK_IMAGES_REQ_CODE)
            }
        }

        findViewById<Button>(R.id.btn_pick_pdf).setOnClickListener {
            promptDestinationDialog { targetMode ->
                pendingTargetMode = targetMode
                val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    type = "application/pdf"
                }
                startActivityForResult(intent, PICK_PDF_REQ_CODE)
            }
        }

        findViewById<Button>(R.id.btn_pick_folder).setOnClickListener {
            promptDestinationDialog { targetMode ->
                pendingTargetMode = targetMode
                val intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE)
                startActivityForResult(intent, PICK_FOLDER_REQ_CODE)
            }
        }

        handleIncomingIntent(intent)
    }

    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        intent?.let { handleIncomingIntent(it) }
    }

    private fun handleIncomingIntent(intent: Intent) {
        if (intent.getStringExtra("action") == "pick_image") {
            pendingTargetMode = 0 // Reference board
            val pickIntent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                addCategory(Intent.CATEGORY_OPENABLE)
                type = "image/*"
                putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
            }
            startActivityForResult(pickIntent, PICK_IMAGES_REQ_CODE)
        }
    }

    private fun promptDestinationDialog(onChosen: (Int) -> Unit) {
        val options = arrayOf("Reference Board", "Practice Mode")
        AlertDialog.Builder(this)
            .setTitle("Import Destination")
            .setItems(options) { _, which ->
                onChosen(which)
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun checkOverlayPermissionAndLaunch() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            if (!Settings.canDrawOverlays(this)) {
                val intent = Intent(
                    Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    Uri.parse("package:$packageName")
                )
                startActivityForResult(intent, OVERLAY_PERMISSION_REQ_CODE)
                Toast.makeText(this, "Grant 'Appear on top' permission to float over your drawing canvas", Toast.LENGTH_LONG).show()
                return
            }
        }
        startFloatingService()
    }

    private fun startFloatingService() {
        val intent = Intent(this, FloatingOverlayService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent)
        } else {
            startService(intent)
        }
        // Move app to background so artist immediately sees their drawing app
        moveTaskToBack(true)
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)

        if (requestCode == OVERLAY_PERMISSION_REQ_CODE) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && Settings.canDrawOverlays(this)) {
                startFloatingService()
            } else {
                Toast.makeText(this, "Overlay permission is required to float over drawing apps", Toast.LENGTH_SHORT).show()
            }
            return
        }

        if (resultCode != RESULT_OK || data == null) return

        when (requestCode) {
            PICK_IMAGES_REQ_CODE -> {
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
                    loadBitmapFromUri(uri)?.let { loadedBitmaps.add(it) }
                }

                dispatchBitmaps(loadedBitmaps)
            }

            PICK_PDF_REQ_CODE -> {
                data.data?.let { uri ->
                    val pages = PdfHelper.renderPdfPages(this, uri)
                    if (pages.isNotEmpty()) {
                        dispatchBitmaps(pages)
                        Toast.makeText(this, "Loaded ${pages.size} PDF pages", Toast.LENGTH_SHORT).show()
                    } else {
                        Toast.makeText(this, "Unable to load PDF pages", Toast.LENGTH_SHORT).show()
                    }
                }
            }

            PICK_FOLDER_REQ_CODE -> {
                data.data?.let { treeUri ->
                    loadFolderImages(treeUri)
                }
            }
        }
    }

    private fun loadFolderImages(treeUri: Uri) {
        val loadedBitmaps = mutableListOf<Bitmap>()
        try {
            val childrenUri = DocumentsContract.buildChildDocumentsUriUsingTree(
                treeUri,
                DocumentsContract.getTreeDocumentId(treeUri)
            )

            val projection = arrayOf(
                DocumentsContract.Document.COLUMN_DOCUMENT_ID,
                DocumentsContract.Document.COLUMN_MIME_TYPE
            )

            contentResolver.query(childrenUri, projection, null, null, null)?.use { cursor ->
                val idIndex = cursor.getColumnIndexOrThrow(DocumentsContract.Document.COLUMN_DOCUMENT_ID)
                val mimeIndex = cursor.getColumnIndexOrThrow(DocumentsContract.Document.COLUMN_MIME_TYPE)

                var count = 0
                while (cursor.moveToNext() && count < 50) {
                    val docId = cursor.getString(idIndex)
                    val mime = cursor.getString(mimeIndex)
                    if (mime.startsWith("image/")) {
                        val fileUri = DocumentsContract.buildDocumentUriUsingTree(treeUri, docId)
                        loadBitmapFromUri(fileUri)?.let {
                            loadedBitmaps.add(it)
                            count++
                        }
                    }
                }
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }

        if (loadedBitmaps.isNotEmpty()) {
            dispatchBitmaps(loadedBitmaps)
            Toast.makeText(this, "Loaded ${loadedBitmaps.size} folder images", Toast.LENGTH_SHORT).show()
        }
    }

    private fun dispatchBitmaps(bitmaps: List<Bitmap>) {
        if (pendingTargetMode == 0) {
            for (bmp in bitmaps) {
                DataManager.addReference(bmp)
            }
            Toast.makeText(this, "Added to Reference Board", Toast.LENGTH_SHORT).show()
        } else {
            DataManager.addPracticeImages(bitmaps)
            Toast.makeText(this, "Added to Practice Mode", Toast.LENGTH_SHORT).show()
        }
        checkOverlayPermissionAndLaunch()
    }

    private fun loadBitmapFromUri(uri: Uri): Bitmap? {
        return try {
            // Downsample if huge to stay within mobile tablet heap limits
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
