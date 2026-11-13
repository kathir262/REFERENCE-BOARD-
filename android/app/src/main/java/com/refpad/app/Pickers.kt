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

    /** Any file: Android doesn't know the .refpad type, so RefPad checks the file itself. */
    fun openBoard(): Intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
        .addCategory(Intent.CATEGORY_OPENABLE)
        .setType("*/*")
        .addFlags(
            Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION or
                Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION
        )

    fun createBoard(name: String): Intent = Intent(Intent.ACTION_CREATE_DOCUMENT)
        .addCategory(Intent.CATEGORY_OPENABLE)
        .setType(BoardFiles.MIME)
        .putExtra(Intent.EXTRA_TITLE, name + BoardFiles.EXT)

    /** Where to save the board as a PNG picture. */
    fun createPng(boardTitle: String): Intent = Intent(Intent.ACTION_CREATE_DOCUMENT)
        .addCategory(Intent.CATEGORY_OPENABLE)
        .setType("image/png")
        .putExtra(Intent.EXTRA_TITLE, BoardExport.suggestedName(boardTitle))

    /** A one-line text box, or a few lines with [multiLine] (works from the floating window too). */
    fun askText(
        context: android.content.Context, overlay: Boolean, title: String, hint: String, initial: String,
        multiLine: Boolean = false, onOk: (String) -> Unit
    ) {
        val ctx = android.view.ContextThemeWrapper(context, android.R.style.Theme_DeviceDefault_Dialog_Alert)
        val pad = (20 * context.resources.displayMetrics.density).toInt()
        val input = android.widget.EditText(ctx).apply {
            this.hint = hint
            setText(initial)
            if (multiLine) {
                inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE or
                    android.text.InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
                isSingleLine = false
                minLines = 3
                maxLines = 8
                gravity = android.view.Gravity.TOP or android.view.Gravity.START
                setSelection(text.length)
            } else {
                setSelectAllOnFocus(true)
                isSingleLine = true
                inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
            }
        }
        val box = android.widget.FrameLayout(ctx).apply {
            setPadding(pad, pad / 2, pad, 0)
            addView(input)
        }
        val dialog = android.app.AlertDialog.Builder(ctx)
            .setTitle(title)
            .setView(box)
            .setPositiveButton("OK") { _, _ -> onOk(input.text.toString()) }
            .setNegativeButton("Cancel", null)
            .create()
        if (overlay) {
            dialog.window?.setType(
                if (Build.VERSION.SDK_INT >= 26) android.view.WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
                else @Suppress("DEPRECATION") android.view.WindowManager.LayoutParams.TYPE_PHONE
            )
        }
        dialog.window?.setSoftInputMode(android.view.WindowManager.LayoutParams.SOFT_INPUT_STATE_VISIBLE)
        if (!multiLine) {
            input.setOnEditorActionListener { _, _, _ ->
                onOk(input.text.toString())
                dialog.dismiss()
                true
            }
        }
        dialog.show()
        input.requestFocus()
    }

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
