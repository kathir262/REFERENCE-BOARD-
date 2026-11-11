package com.refpad.app

import android.app.Activity
import android.content.Intent
import android.os.Bundle

/**
 * Invisible screen the floating window uses to open the system picker
 * (a floating window cannot receive picker results itself).
 * It closes as soon as the picked files are opened; decoding continues in the background.
 */
class PickerActivity : Activity() {

    companion object {
        const val EXTRA_ACTION = "action"
        const val EXTRA_TARGET = "target"
        const val PICK_IMAGES = "images"
        const val PICK_PDF = "pdf"
        private const val REQ_PICK = 7
    }

    private var launched = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        @Suppress("DEPRECATION")
        overridePendingTransition(0, 0)
        DataManager.init(this)

        launched = savedInstanceState?.getBoolean("launched", false) ?: false
        if (launched) return // the picker is already open; wait for its result

        val (primary, fallback) = when (intent.getStringExtra(EXTRA_ACTION)) {
            PICK_IMAGES -> Pickers.images() to Pickers.imagesFallback()
            PICK_PDF -> Pickers.pdf() to Pickers.pdfFallback()
            else -> {
                finish()
                return
            }
        }
        launched = true
        if (!Pickers.launch(this, primary, fallback, REQ_PICK)) finish()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        outState.putBoolean("launched", launched)
    }

    @Deprecated("Plain Activity result API; this app uses no AndroidX libraries")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        val uris = if (resultCode == RESULT_OK) Importer.urisFrom(data) else emptyList()
        if (uris.isEmpty()) {
            finish()
            return
        }
        val target = try {
            Importer.Target.valueOf(intent.getStringExtra(EXTRA_TARGET) ?: "BOARD")
        } catch (e: IllegalArgumentException) {
            Importer.Target.BOARD
        }
        val done = { finish() }
        if (intent.getStringExtra(EXTRA_ACTION) == PICK_PDF) Importer.importPdfs(this, uris, target, done)
        else Importer.importImages(this, uris, target, done)
    }

    override fun finish() {
        super.finish()
        @Suppress("DEPRECATION")
        overridePendingTransition(0, 0)
    }

    override fun onDestroy() {
        // Only when really closing, not when Android recreates this screen.
        if (isFinishing) FloatingOverlayService.onPickerClosed()
        super.onDestroy()
    }
}
