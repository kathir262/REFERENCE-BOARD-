package com.refpad.app

import android.app.Activity
import android.content.Intent
import android.os.Build
import android.provider.MediaStore
import android.util.Log
import android.widget.Toast

/** The system pickers used to choose images and PDFs (no storage permission needed). */
object Pickers {
    fun images(): Intent =
        if (Build.VERSION.SDK_INT >= 33) {
            Intent(MediaStore.ACTION_PICK_IMAGES)
                .setType("image/*") // photos only, no videos
                .putExtra(MediaStore.EXTRA_PICK_IMAGES_MAX, maxImages())
        } else {
            Intent(Intent.ACTION_GET_CONTENT)
                .setType("image/*")
                .addCategory(Intent.CATEGORY_OPENABLE)
                .putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
        }

    fun imagesFallback(): Intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
        .setType("image/*")
        .addCategory(Intent.CATEGORY_OPENABLE)
        .putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)

    fun pdf(): Intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
        .setType("application/pdf")
        .addCategory(Intent.CATEGORY_OPENABLE)

    fun pdfFallback(): Intent = Intent(Intent.ACTION_GET_CONTENT)
        .setType("application/pdf")
        .addCategory(Intent.CATEGORY_OPENABLE)

    fun folder(): Intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE)

    private fun maxImages(): Int = try {
        minOf(50, MediaStore.getPickImagesMaxLimit())
    } catch (t: Throwable) {
        20
    }

    /** Starts [primary], or [fallback] if no app handles it. Returns false if neither could start. */
    fun launch(activity: Activity, primary: Intent, fallback: Intent?, requestCode: Int): Boolean {
        for (intent in listOfNotNull(primary, fallback)) {
            try {
                activity.startActivityForResult(intent, requestCode)
                return true
            } catch (e: Exception) {
                Log.w("RefPad", "Picker not available: ${intent.action}", e)
            }
        }
        Toast.makeText(activity, "No file picker is available on this device", Toast.LENGTH_SHORT).show()
        return false
    }
}
