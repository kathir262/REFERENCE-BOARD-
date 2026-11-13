package com.refpad.app

import android.content.Context
import android.content.Intent
import android.graphics.pdf.PdfRenderer
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.os.ParcelFileDescriptor
import android.provider.DocumentsContract
import android.provider.OpenableColumns
import android.util.Log
import android.widget.Toast
import java.io.File
import java.io.FileOutputStream
import java.util.concurrent.Executors

/**
 * Brings pictures and PDFs into the app without ever blocking the screen.
 *
 * Step 1 (quick, own thread): open every picked file while the picker's permission is still valid.
 *         The caller's onOpened() runs after this, so a picker screen can close right away.
 * Step 2 (slow, shared background worker): decode, shrink, save a copy, then hand the result to the board.
 */
object Importer {
    enum class Target { BOARD, PRACTICE, VIEWER }

    private const val TAG = "RefPad"
    private const val BOARD_PDF_LONG_SIDE = 1200
    private const val FOLDER_MAX_IMAGES = 60

    private val main = Handler(Looper.getMainLooper())
    private val opener = Executors.newSingleThreadExecutor { r -> Thread(r, "refpad-open") }

    /** All URIs in a picker result (single pick, multi pick, or share). */
    fun urisFrom(data: Intent?): List<Uri> {
        if (data == null) return emptyList()
        val out = LinkedHashSet<Uri>()
        data.data?.let { out.add(it) }
        data.clipData?.let { clip -> for (i in 0 until clip.itemCount) clip.getItemAt(i).uri?.let { out.add(it) } }
        return out.toList()
    }

    fun importImages(context: Context, uris: List<Uri>, target: Target, onOpened: () -> Unit = {}) {
        val app = context.applicationContext
        if (uris.isEmpty()) { onOpened(); return }
        DataManager.setStatus("Opening ${plural(uris.size, "image")}…")
        opener.execute {
            val files = uris.mapNotNull { open(app, it) }
            main.post(onOpened)
            if (files.isEmpty()) {
                status(null)
                toast(app, "Could not open the selected image(s)")
                return@execute
            }
            Storage.io.execute { decodeImages(app, files, target, uris.size) }
        }
    }

    fun importPdfs(context: Context, uris: List<Uri>, target: Target, onOpened: () -> Unit = {}) {
        val app = context.applicationContext
        if (uris.isEmpty()) { onOpened(); return }
        DataManager.setStatus("Opening PDF…")
        opener.execute {
            val files = uris.mapNotNull { uri -> open(app, uri)?.let { it to displayName(app, uri) } }
            main.post(onOpened)
            if (files.isEmpty()) {
                status(null)
                toast(app, "Could not open the selected PDF")
                return@execute
            }
            Storage.io.execute {
                for ((pfd, name) in files) {
                    when (target) {
                        Target.BOARD -> pdfToViewer(app, pfd, name, choosePages = true)
                        Target.PRACTICE -> pdfToPractice(app, pfd)
                        Target.VIEWER -> pdfToViewer(app, pfd, name)
                    }
                }
                status(null)
            }
        }
    }

    /** Copies one page of a viewer PDF onto the board as an image. */
    fun pageToBoard(context: Context, doc: ViewerDoc, page: Int) {
        val app = context.applicationContext
        DataManager.setStatus("Adding page ${page + 1} to the board…")
        Storage.io.execute {
            try {
                val bmp = PdfRenderer(ParcelFileDescriptor.open(Storage.pdfFile(doc.docId), ParcelFileDescriptor.MODE_READ_ONLY)).use { r ->
                    r.openPage(page).use { PdfHelper.renderPage(it, BOARD_PDF_LONG_SIDE) }
                }
                val image = ImageLoader.store(bmp)
                main.post { DataManager.addToBoard(image) }
                toast(app, "Page ${page + 1} added to the board")
            } catch (t: Throwable) {
                Log.w(TAG, "Page to board failed", t)
                toast(app, "Could not add that page")
            }
            status(null)
        }
    }

    /** Puts part of a page (a snip; [frac] is the area as fractions of the page) on the board as a picture. */
    fun regionToBoard(context: Context, doc: ViewerDoc, page: Int, frac: android.graphics.RectF) {
        val app = context.applicationContext
        DataManager.setStatus("Adding the snip to the board…")
        Storage.io.execute {
            try {
                val bmp = PdfRenderer(ParcelFileDescriptor.open(Storage.pdfFile(doc.docId), ParcelFileDescriptor.MODE_READ_ONLY)).use { r ->
                    r.openPage(page).use { p ->
                        val rw = frac.width() * p.width
                        val rh = frac.height() * p.height
                        // Sharp: the snip's long side becomes the board's picture size, whatever the zoom was.
                        val s = (ImageLoader.MAX_IMAGE_SIDE / maxOf(rw, rh, 1f)).coerceAtMost(12000f / maxOf(p.width, p.height, 1))
                        val w = (rw * s).toInt().coerceAtLeast(1)
                        val h = (rh * s).toInt().coerceAtLeast(1)
                        val out = android.graphics.Bitmap.createBitmap(w, h, android.graphics.Bitmap.Config.ARGB_8888)
                        out.eraseColor(android.graphics.Color.WHITE)
                        val m = android.graphics.Matrix()
                        m.setScale(s, s)
                        m.postTranslate(-frac.left * p.width * s, -frac.top * p.height * s)
                        p.render(out, null, m, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                        out.setHasAlpha(false)
                        out
                    }
                }
                val image = ImageLoader.store(bmp)
                main.post {
                    val item = DataManager.addToBoard(image)
                    DataManager.setStatus(null)
                    toast(app, "Snip from page ${page + 1} added to the board")
                    item
                }
            } catch (t: Throwable) {
                Log.w(TAG, "Snip failed", t)
                status(null)
                toast(app, "Could not add that part of the page")
            }
        }
    }

    /**
     * Adds the chosen pages of a reader PDF to the board, one at a time (light on memory).
     * The message at the bottom has a STOP button; opening another board also stops it.
     */
    fun pagesToBoard(context: Context, doc: ViewerDoc, pages: List<Int>) {
        if (pages.isEmpty()) return
        val app = context.applicationContext
        val stop = java.util.concurrent.atomic.AtomicBoolean(false)
        val stopIt: () -> Unit = { stop.set(true) }
        val epoch = DataManager.boardEpoch
        val total = pages.size
        DataManager.setMode(DataManager.MODE_BOARD)
        DataManager.setStatus("Adding page 1 of $total…", stopIt)
        Storage.io.execute {
            var added = 0
            try {
                PdfRenderer(ParcelFileDescriptor.open(Storage.pdfFile(doc.docId), ParcelFileDescriptor.MODE_READ_ONLY)).use { r ->
                    for ((k, page) in pages.withIndex()) {
                        if (stop.get()) break
                        main.post { if (!stop.get()) DataManager.setStatus("Adding page ${k + 1} of $total…", stopIt) }
                        if (page !in 0 until r.pageCount) continue
                        val bmp = try {
                            r.openPage(page).use { PdfHelper.renderPage(it, BOARD_PDF_LONG_SIDE) }
                        } catch (oom: OutOfMemoryError) {
                            Log.w(TAG, "Out of memory on page $page", oom)
                            break
                        } catch (e: Exception) {
                            Log.w(TAG, "Page $page failed", e)
                            continue
                        }
                        val image = ImageLoader.store(bmp)
                        added++
                        main.post {
                            if (DataManager.boardEpoch == epoch) DataManager.addToBoard(image) else stop.set(true)
                        }
                    }
                }
            } catch (e: Exception) {
                Log.w(TAG, "Pages to board failed", e)
                toast(app, "Could not open that PDF")
            }
            main.post {
                DataManager.setStatus(null)
                if (added > 0) DataManager.requestFit()
            }
            toast(app, if (stop.get()) "Stopped · ${plural(added, "page")} added" else "Added ${plural(added, "page")} to the board")
        }
    }

    fun importFolder(context: Context, treeUri: Uri, target: Target, onOpened: () -> Unit = {}) {
        val app = context.applicationContext
        DataManager.setStatus("Reading folder…")
        opener.execute {
            val (uris, total) = try {
                listFolderImages(app, treeUri)
            } catch (e: Exception) {
                Log.w(TAG, "Folder listing failed", e)
                emptyList<Uri>() to 0
            }
            val files = uris.mapNotNull { open(app, it) }
            main.post(onOpened)
            if (files.isEmpty()) {
                status(null)
                toast(app, "No images found in that folder")
                return@execute
            }
            if (total > FOLDER_MAX_IMAGES) toast(app, "Folder has $total images – adding the first $FOLDER_MAX_IMAGES")
            Storage.io.execute { decodeImages(app, files, target, files.size) }
        }
    }

    fun loadSamples() {
        DataManager.setStatus("Creating sample poses…")
        Storage.io.execute {
            val images = SampleGenerator.createSamplePoses().map { ImageLoader.store(it) }
            main.post {
                DataManager.setMode(DataManager.MODE_BOARD)
                images.forEach { DataManager.addToBoard(it) }
                DataManager.setStatus(null)
                DataManager.requestFit()
            }
        }
    }

    // ------------------------------------------------------------------ Workers

    private fun decodeImages(app: Context, files: List<ParcelFileDescriptor>, target: Target, requested: Int) {
        var added = 0
        for ((i, pfd) in files.withIndex()) {
            status("Importing image ${i + 1} of ${files.size}…")
            val tmp = Storage.tempFile()
            val bmp = try {
                if (copy(pfd, tmp)) ImageLoader.decodeFile(tmp) else null
            } finally {
                tmp.delete()
            }
            if (bmp == null) continue
            val image = ImageLoader.store(bmp)
            val first = added == 0
            added++
            main.post {
                if (target == Target.BOARD) {
                    if (first) DataManager.setMode(DataManager.MODE_BOARD)
                    DataManager.addToBoard(image)
                } else {
                    DataManager.addPoses(listOf(Pose.Image(image)), jumpToFirst = first)
                    if (first) DataManager.setMode(DataManager.MODE_PRACTICE)
                }
            }
        }
        main.post {
            DataManager.setStatus(null)
            if (added > 0 && target == Target.BOARD) DataManager.requestFit()
        }
        val skipped = requested - added
        toast(
            app, when {
                added == 0 -> "Could not load the selected image(s)"
                target == Target.BOARD -> "Added ${plural(added, "image")} to the board" + if (skipped > 0) " ($skipped could not be read)" else ""
                else -> "Added ${plural(added, "pose")} to practice" + if (skipped > 0) " ($skipped could not be read)" else ""
            }
        )
    }

    private fun pdfToPractice(app: Context, pfd: ParcelFileDescriptor) {
        status("Copying PDF…")
        val docId = Storage.newId()
        val file = Storage.pdfFile(docId)
        if (!copy(pfd, file)) {
            toast(app, "Could not read that PDF")
            return
        }
        val count = PdfHelper.pageCount(file)
        if (count <= 0) {
            file.delete()
            toast(app, "Could not open this PDF. It may be damaged or password protected.")
            return
        }
        val poses = (0 until count).map { Pose.PdfPage(docId, it) }
        main.post {
            DataManager.addPoses(poses, jumpToFirst = true)
            DataManager.setMode(DataManager.MODE_PRACTICE)
        }
        toast(app, "Loaded ${plural(count, "page")} into practice")
    }

    private fun pdfToViewer(app: Context, pfd: ParcelFileDescriptor, name: String, choosePages: Boolean = false) {
        status("Copying PDF…")
        val docId = Storage.newId()
        val file = Storage.pdfFile(docId)
        if (!copy(pfd, file)) {
            toast(app, "Could not read that PDF")
            return
        }
        val aspects = PdfHelper.pageAspects(file) { done, total -> status("Reading page $done of $total…") }
        if (aspects == null) {
            file.delete()
            toast(app, "Could not open this PDF. It may be damaged or password protected.")
            return
        }
        val doc = ViewerDoc(docId, name, aspects)
        main.post { if (choosePages) DataManager.choosePages(doc) else DataManager.openDoc(doc) }
    }

    // ------------------------------------------------------------------ Helpers

    /** The file's name without ".pdf", for showing in the recent list. */
    private fun displayName(context: Context, uri: Uri): String {
        val name = try {
            context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
                if (c.moveToFirst()) c.getString(0) else null
            }
        } catch (e: Exception) {
            null
        }
        return (name ?: uri.lastPathSegment ?: "PDF").substringAfterLast('/').removeSuffix(".pdf").removeSuffix(".PDF").trim().ifEmpty { "PDF" }
    }

    private fun open(context: Context, uri: Uri): ParcelFileDescriptor? = try {
        context.contentResolver.openFileDescriptor(uri, "r")
    } catch (e: Exception) {
        Log.w(TAG, "Cannot open $uri", e)
        null
    }

    /** Copies (and closes) [pfd] into [dest]. Works for cloud files that cannot seek. */
    private fun copy(pfd: ParcelFileDescriptor, dest: File): Boolean = try {
        ParcelFileDescriptor.AutoCloseInputStream(pfd).use { input ->
            FileOutputStream(dest).use { out -> input.copyTo(out, 256 * 1024) }
        }
        dest.length() > 0
    } catch (e: Exception) {
        Log.w(TAG, "Copy failed", e)
        dest.delete()
        false
    }

    private fun listFolderImages(context: Context, treeUri: Uri): Pair<List<Uri>, Int> {
        val children = DocumentsContract.buildChildDocumentsUriUsingTree(treeUri, DocumentsContract.getTreeDocumentId(treeUri))
        val found = ArrayList<Pair<String, Uri>>()
        context.contentResolver.query(
            children,
            arrayOf(
                DocumentsContract.Document.COLUMN_DOCUMENT_ID,
                DocumentsContract.Document.COLUMN_MIME_TYPE,
                DocumentsContract.Document.COLUMN_DISPLAY_NAME
            ), null, null, null
        )?.use { c ->
            while (c.moveToNext()) {
                val mime = c.getString(1) ?: continue
                if (!mime.startsWith("image/")) continue
                found.add((c.getString(2) ?: "") to DocumentsContract.buildDocumentUriUsingTree(treeUri, c.getString(0)))
            }
        }
        found.sortWith(compareBy(String.CASE_INSENSITIVE_ORDER) { it.first })
        return found.take(FOLDER_MAX_IMAGES).map { it.second } to found.size
    }

    private fun status(text: String?) = main.post { DataManager.setStatus(text) }

    private fun toast(context: Context, text: String) = main.post {
        Toast.makeText(context, text, if (text.length > 60) Toast.LENGTH_LONG else Toast.LENGTH_SHORT).show()
    }

    private fun plural(n: Int, word: String) = if (n == 1) "1 $word" else "$n ${word}s"
}
