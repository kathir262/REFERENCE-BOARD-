package com.refpad.app

import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.RectF
import android.graphics.pdf.PdfRenderer
import android.os.Handler
import android.os.HandlerThread
import android.os.Looper
import android.os.ParcelFileDescriptor
import android.os.Process
import android.util.Log
import android.util.LruCache
import java.io.File
import kotlin.math.max
import kotlin.math.roundToInt

/** Shared PDF helpers. */
object PdfHelper {
    /** Renders one page onto white, long side [longSide] px. Returns a normal (CPU) bitmap. */
    fun renderPage(page: PdfRenderer.Page, longSide: Int): Bitmap {
        val s = longSide.toFloat() / max(page.width, page.height).coerceAtLeast(1)
        val w = max(1, (page.width * s).roundToInt())
        val h = max(1, (page.height * s).roundToInt())
        // PdfRenderer can only draw into ARGB_8888 bitmaps.
        val bmp = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        bmp.eraseColor(Color.WHITE)
        page.render(bmp, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
        bmp.setHasAlpha(false)
        return bmp
    }

    /** Number of pages, or -1 if the file is not a readable PDF (damaged or password protected). */
    fun pageCount(file: File): Int = try {
        PdfRenderer(ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY)).use { it.pageCount }
    } catch (e: Exception) {
        Log.w("RefPad", "Cannot open PDF ${file.name}", e)
        -1
    }

    /** Height/width of every page (needed to lay out the reader), or null if the PDF cannot be read. */
    fun pageAspects(file: File, progress: (done: Int, total: Int) -> Unit): FloatArray? = try {
        PdfRenderer(ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY)).use { r ->
            val n = r.pageCount
            if (n <= 0) return null
            FloatArray(n) { i ->
                if (i % 40 == 0) progress(i, n)
                r.openPage(i).use { p -> p.height.toFloat() / p.width.coerceAtLeast(1) }
            }
        }
    } catch (e: Exception) {
        Log.w("RefPad", "Cannot read PDF ${file.name}", e)
        null
    }
}

/**
 * Renders practice-mode PDF pages only when they are needed (current page plus its neighbours),
 * keeping a small cache. A 300-page art book therefore uses about as much memory as 5 pages.
 */
object PdfPages {
    private const val TAG = "RefPad"
    const val RENDER_LONG_SIDE = 1800
    /** Room for the pages on screen plus their neighbours at full quality. */
    private const val CACHE_BYTES = 40 * 1024 * 1024

    /** Width in pixels of the cached rendering of a page with this height/width ratio. */
    fun baseWidth(aspect: Float): Float = if (aspect >= 1f) RENDER_LONG_SIDE / aspect else RENDER_LONG_SIDE.toFloat()

    private val main = Handler(Looper.getMainLooper())
    private val worker: Handler = HandlerThread("refpad-pdf", Process.THREAD_PRIORITY_BACKGROUND).let {
        it.start()
        Handler(it.looper)
    }

    private val cache = object : LruCache<String, Bitmap>(CACHE_BYTES) {
        override fun sizeOf(key: String, value: Bitmap) = value.width * value.height * 4
    }

    // Main-thread state
    private val inFlight = HashSet<String>()
    private val failed = HashSet<String>()
    private val listeners = ArrayList<() -> Unit>()

    /** Pages each screen currently wants; renders for anything else are skipped. */
    @Volatile
    private var wanted: Set<String> = emptySet()
    private val wantedByOwner = HashMap<Any, Set<String>>()

    // Worker-thread state: keep the current PDF open while flipping through it.
    private var openDocId: String? = null
    private var openRenderer: PdfRenderer? = null
    private val closeIdle = Runnable { closeDoc() }

    private fun key(docId: String, page: Int) = "$docId#$page"

    fun get(docId: String, page: Int): Bitmap? = cache.get(key(docId, page))

    fun hasFailed(docId: String, page: Int) = failed.contains(key(docId, page))

    fun addListener(l: () -> Unit) {
        if (!listeners.contains(l)) listeners.add(l)
    }

    fun removeListener(l: () -> Unit) {
        listeners.remove(l)
    }

    /**
     * Declares which pages a screen ([owner]) needs right now (most important first) and renders any that are missing.
     * The full screen and the floating window can both ask at the same time.
     */
    fun focus(owner: Any, pages: List<Pose.PdfPage>) {
        wantedByOwner[owner] = pages.mapTo(HashSet()) { key(it.docId, it.page) }
        wanted = wantedByOwner.values.flatMapTo(HashSet()) { it }
        for (p in pages) request(p.docId, p.page)
    }

    fun release(owner: Any) {
        if (wantedByOwner.remove(owner) != null) wanted = wantedByOwner.values.flatMapTo(HashSet()) { it }
    }

    /**
     * Renders part of a page at screen sharpness (used when zoomed into a page).
     * [displayWidth] is the page's width on screen; ([x], [y], [w], [h]) is the wanted area in those pixels.
     * [isStale] is checked just before the slow work starts, so outdated requests are skipped.
     */
    fun renderDetail(
        docId: String, page: Int, displayWidth: Float,
        x: Float, y: Float, w: Int, h: Int,
        isStale: () -> Boolean, done: (Bitmap?) -> Unit
    ) {
        worker.post {
            var result: Bitmap? = null
            if (!isStale()) {
                worker.removeCallbacks(closeIdle)
                try {
                    val renderer = rendererFor(docId)
                    if (renderer != null && page in 0 until renderer.pageCount) {
                        renderer.openPage(page).use { p ->
                            val s = displayWidth / p.width.coerceAtLeast(1)
                            val bmp = Bitmap.createBitmap(w.coerceAtLeast(1), h.coerceAtLeast(1), Bitmap.Config.ARGB_8888)
                            bmp.eraseColor(Color.WHITE)
                            val m = android.graphics.Matrix()
                            m.setScale(s, s)
                            m.postTranslate(-x, -y)
                            p.render(bmp, null, m, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                            bmp.setHasAlpha(false)
                            result = ImageLoader.toDisplay(bmp)
                        }
                    }
                } catch (oom: OutOfMemoryError) {
                    Log.w(TAG, "Out of memory rendering detail", oom)
                } catch (e: Exception) {
                    Log.w(TAG, "Detail render failed", e)
                    closeDoc()
                } finally {
                    worker.postDelayed(closeIdle, 30_000)
                }
            }
            val out = result
            main.post { done(out) }
        }
    }

    private fun request(docId: String, page: Int) {
        val k = key(docId, page)
        if (cache.get(k) != null || inFlight.contains(k) || failed.contains(k)) return
        inFlight.add(k)
        worker.post {
            val stillWanted = wanted.contains(k)
            val bmp = if (stillWanted) render(docId, page) else null
            main.post {
                inFlight.remove(k)
                if (bmp != null) {
                    cache.put(k, bmp)
                    for (l in listeners.toTypedArray()) l()
                } else if (stillWanted) {
                    failed.add(k)
                    for (l in listeners.toTypedArray()) l()
                }
            }
        }
    }

    private fun render(docId: String, page: Int): Bitmap? {
        worker.removeCallbacks(closeIdle)
        try {
            val renderer = rendererFor(docId) ?: return null
            if (page < 0 || page >= renderer.pageCount) return null
            val bmp = renderer.openPage(page).use { PdfHelper.renderPage(it, RENDER_LONG_SIDE) }
            return ImageLoader.toDisplay(bmp)
        } catch (oom: OutOfMemoryError) {
            Log.w(TAG, "Out of memory rendering page $page", oom)
            main.post { cache.evictAll() }
        } catch (e: Exception) {
            Log.w(TAG, "Could not render page $page", e)
            closeDoc()
        } finally {
            // Release the PDF if nobody flips a page for a while.
            worker.postDelayed(closeIdle, 30_000)
        }
        return null
    }

    private fun rendererFor(docId: String): PdfRenderer? {
        if (openDocId == docId) openRenderer?.let { return it }
        closeDoc()
        val file = Storage.pdfFile(docId)
        if (!file.exists()) return null
        val pfd = ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY)
        return try {
            PdfRenderer(pfd).also {
                openRenderer = it
                openDocId = docId
            }
        } catch (e: Exception) {
            pfd.close()
            throw e
        }
    }

    private fun closeDoc() {
        try {
            openRenderer?.close()
        } catch (_: Exception) {
        }
        openRenderer = null
        openDocId = null
    }

    /** Frees cached pages when Android is short on memory. */
    fun trim(all: Boolean) {
        main.post {
            if (all) cache.evictAll() else cache.trimToSize(CACHE_BYTES / 4)
            if (all) thumbs.evictAll()
            failed.clear()
        }
    }

    // ---------------------------------------------------------------- Page thumbnails (the page strip)

    private const val THUMB_SIDE = 220
    private val thumbs = object : LruCache<String, Bitmap>(10 * 1024 * 1024) {
        override fun sizeOf(key: String, value: Bitmap) = value.width * value.height * 4
    }
    private val thumbsInFlight = HashSet<String>()
    @Volatile
    private var thumbsWanted: Set<String> = emptySet()

    fun thumb(docId: String, page: Int): Bitmap? = thumbs.get(key(docId, page))

    /** Renders small pictures of [pages] that are not ready yet (only the ones still wanted when their turn comes). */
    fun requestThumbs(docId: String, pages: List<Int>) {
        thumbsWanted = pages.mapTo(HashSet()) { key(docId, it) }
        for (p in pages) {
            val k = key(docId, p)
            if (thumbs.get(k) != null || thumbsInFlight.contains(k) || failed.contains(k)) continue
            thumbsInFlight.add(k)
            worker.post {
                var bmp: Bitmap? = null
                if (thumbsWanted.contains(k)) {
                    worker.removeCallbacks(closeIdle)
                    try {
                        val r = rendererFor(docId)
                        if (r != null && p in 0 until r.pageCount) {
                            bmp = ImageLoader.toDisplay(r.openPage(p).use { PdfHelper.renderPage(it, THUMB_SIDE) })
                        }
                    } catch (t: Throwable) {
                        Log.w(TAG, "Thumbnail $p failed", t)
                    } finally {
                        worker.postDelayed(closeIdle, 30_000)
                    }
                }
                val out = bmp
                main.post {
                    thumbsInFlight.remove(k)
                    if (out != null) {
                        thumbs.put(k, out)
                        for (l in listeners.toTypedArray()) l()
                    }
                }
            }
        }
    }
}

/**
 * Finds text in a PDF (Android 15 and newer, whose PDF engine can search). Runs on its own thread with its
 * own copy of the PDF open, so reading stays smooth; results arrive a few pages at a time.
 */
object PdfSearch {
    val supported: Boolean get() = android.os.Build.VERSION.SDK_INT >= 35

    private const val MAX_HITS = 2000
    private val main = Handler(Looper.getMainLooper())
    private val worker = java.util.concurrent.Executors.newSingleThreadExecutor { r ->
        Thread({
            Process.setThreadPriority(Process.THREAD_PRIORITY_BACKGROUND)
            r.run()
        }, "refpad-search")
    }
    private val token = java.util.concurrent.atomic.AtomicInteger()

    fun cancel() {
        token.incrementAndGet()
    }

    /**
     * Searches [docId] for [query]. [onHits] gets batches of matches (page, box as page fractions);
     * [onDone] gets the total, or -1 if this PDF can't be searched.
     */
    fun search(
        docId: String, query: String,
        onHits: (List<PdfViewerView.Hit>) -> Unit, onDone: (Int) -> Unit
    ) {
        val my = token.incrementAndGet()
        if (!supported || query.isBlank()) {
            onDone(-1)
            return
        }
        worker.execute {
            var total = 0
            var failed = false
            try {
                ParcelFileDescriptor.open(Storage.pdfFile(docId), ParcelFileDescriptor.MODE_READ_ONLY).use { pfd ->
                    PdfRenderer(pfd).use { r ->
                        val batch = ArrayList<PdfViewerView.Hit>()
                        for (i in 0 until r.pageCount) {
                            if (token.get() != my || total >= MAX_HITS) break
                            r.openPage(i).use { page -> found(page, i, query, batch) }
                            if (batch.isNotEmpty() && (i % 8 == 7 || batch.size > 50)) {
                                val send = ArrayList(batch)
                                total += send.size
                                batch.clear()
                                main.post { if (token.get() == my) onHits(send) }
                            }
                        }
                        if (batch.isNotEmpty() && token.get() == my) {
                            val send = ArrayList(batch)
                            total += send.size
                            main.post { if (token.get() == my) onHits(send) }
                        }
                    }
                }
            } catch (t: Throwable) {
                Log.w("RefPad", "Search failed", t)
                failed = total == 0
            }
            val n = total
            main.post { if (token.get() == my) onDone(if (failed) -1 else n) }
        }
    }

    @android.annotation.TargetApi(35)
    private fun found(page: PdfRenderer.Page, index: Int, query: String, out: MutableList<PdfViewerView.Hit>) {
        val w = page.width.toFloat().coerceAtLeast(1f)
        val h = page.height.toFloat().coerceAtLeast(1f)
        for (m in page.searchText(query)) {
            // One match can cover several lines: one box around each part.
            for (b in m.bounds) {
                out.add(PdfViewerView.Hit(index, RectF(b.left / w, b.top / h, b.right / w, b.bottom / h)))
            }
        }
    }
}
