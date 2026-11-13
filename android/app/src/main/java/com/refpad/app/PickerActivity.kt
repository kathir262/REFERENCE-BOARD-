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
        const val OPEN_BOARD = "open_board"
        const val CREATE_BOARD = "create_board"
        const val EXPORT_PNG = "export_png"
        const val EXTRA_NAME = "name"
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
            OPEN_BOARD -> Pickers.openBoard() to null
            CREATE_BOARD -> Pickers.createBoard(intent.getStringExtra(EXTRA_NAME) ?: "Board") to null
            EXPORT_PNG -> Pickers.createPng(intent.getStringExtra(EXTRA_NAME) ?: "Board") to null
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
        when (intent.getStringExtra(EXTRA_ACTION)) {
            OPEN_BOARD -> {
                if (resultCode == RESULT_OK) data?.data?.let { FloatingOverlayService.openBoard(this, it) }
                finish()
                return
            }
            CREATE_BOARD -> {
                val uri = if (resultCode == RESULT_OK) data?.data else null
                if (uri != null) BoardFiles.created(this, uri) else BoardFiles.afterSaveAs = null
                finish()
                return
            }
            EXPORT_PNG -> {
                if (resultCode == RESULT_OK) data?.data?.let { BoardExport.export(this, it) }
                finish()
                return
            }
        }
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
