package com.refpad.app

import android.animation.ValueAnimator
import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.util.AttributeSet
import android.view.GestureDetector
import android.view.HapticFeedbackConstants
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.VelocityTracker
import android.view.View
import android.view.animation.DecelerateInterpolator
import android.widget.OverScroller
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/**
 * A light PDF reader: pages in one continuous column (or two side by side, like an open book),
 * pinch to zoom, fling to scroll, and a scroll thumb on the right for long books.
 *
 * Only the pages on screen (and their neighbours) are rendered. When you zoom in, the visible
 * part is re-rendered at full sharpness as soon as you stop moving.
 *
 * Extras: a strip of page thumbnails on the left, bookmark ribbons, snipping part of a page,
 * and highlighted search results.
 */
class PdfViewerView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr), DataManager.Listener {

    var onPageChanged: ((page: Int, count: Int) -> Unit)? = null
    var onLongPressed: ((x: Float, y: Float, page: Int) -> Unit)? = null
    var onTouchStarted: (() -> Unit)? = null
    /** While choosing pages for the board: how many are chosen. */
    var onChosenChanged: ((count: Int) -> Unit)? = null
    /** A part of a page was snipped: [frac] is the area as fractions (0..1) of the page. */
    var onSnipped: ((page: Int, frac: RectF) -> Unit)? = null
    /** Snip mode, the page strip or the layout changed (for the toolbar's on/off looks). */
    var onToolsChanged: (() -> Unit)? = null

    private val density = resources.displayMetrics.density
    private val gap = 14f * density
    private val sideMargin = 14f * density

    private var doc: ViewerDoc? = null
    // Page boxes in layout units (zoom 1), relative to the column's left edge and the top of the first row.
    private var pLeft = FloatArray(0)
    private var pTop = FloatArray(0)
    private var pW = FloatArray(0)
    private var pH = FloatArray(0)
    private var rowOf = IntArray(0)
    // Rows: one page each, or two side by side in a spread (the cover alone first).
    private var rowTop = FloatArray(0)
    private var rowH = FloatArray(0)
    private var rowStart = IntArray(0)
    private var rowEnd = IntArray(0) // exclusive
    private var columnW = 0f
    private var totalH = 0f
    private var laidOutWidth = 0
    private var needsRestore = true

    private var zoom = 1f
    private var scrollPx = 0f             // horizontal scroll in screen pixels (only when zoomed wider than the view)
    private var scrollPy = 0f             // vertical scroll in screen pixels
    var currentPage = 0
        private set

    private val scroller = OverScroller(context)
    private var interacting = false
    private var zoomAnimator: ValueAnimator? = null

    private val bg = Color.parseColor("#0E0E10")
    private val accent = Color.parseColor("#FACC15")
    private val pagePaint = Paint().apply { color = Color.WHITE }
    private val shadowPaint = Paint().apply { color = Color.parseColor("#55000000") }
    private val numberPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#A1A1AA")
        textSize = 16f * density
        textAlign = Paint.Align.CENTER
    }
    private val thumbPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = accent }
    private val thumbTrackPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#33FFFFFF") }
    private val ribbonPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = accent }
    private val ribbonPath = Path()
    private val rect = RectF()
    private val tmp = RectF()

    val pageCount: Int get() = doc?.pageCount ?: 0

    // ---------------------------------------------------------------- Choosing pages for the board

    /** True while pages are being picked: a tap chooses or un-chooses the page under the finger. */
    var choosing = false
        private set
    private var chosen = BooleanArray(0)
    private val chosenFrame = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 3f * density
        color = accent
    }
    private val dimPaint = Paint().apply { color = Color.parseColor("#8C0E0E10") }
    private val checkFill = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = accent }
    private val checkRing = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 2f * density
        color = Color.parseColor("#E6F4F4F5")
    }
    private val checkMark = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 2.6f * density
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
        color = Color.parseColor("#0A0A0B")
    }
    private val checkPath = Path()

    fun startChoosing(all: Boolean) {
        val n = doc?.pageCount ?: return
        setSnipping(false)
        chosen = BooleanArray(n) { all }
        choosing = true
        invalidate()
        notifyChosen()
    }

    fun stopChoosing() {
        if (!choosing) return
        choosing = false
        invalidate()
    }

    fun chooseAll(all: Boolean) {
        chosen.fill(all)
        invalidate()
        notifyChosen()
    }

    /** Chooses exactly [pages] (0-based) and scrolls to the first one. */
    fun choose(pages: Collection<Int>) {
        chosen.fill(false)
        for (p in pages) if (p in chosen.indices) chosen[p] = true
        invalidate()
        notifyChosen()
        pages.minOrNull()?.let { goToPage(it) }
    }

    fun chosenPages(): List<Int> = chosen.indices.filter { chosen[it] }

    private fun toggleChosenAt(x: Float, y: Float) {
        val p = pageAt(x, y)
        if (p < 0 || p >= chosen.size) return
        chosen[p] = !chosen[p]
        performHapticFeedback(HapticFeedbackConstants.CLOCK_TICK)
        invalidate()
        notifyChosen()
    }

    private fun notifyChosen() = onChosenChanged?.invoke(chosen.count { it })

    private fun drawChoice(canvas: Canvas, i: Int, r: RectF) {
        if (i >= chosen.size) return
        val radius = 13f * density
        val cx = r.right - radius - 10f * density
        val cy = r.top + radius + 10f * density
        if (chosen[i]) {
            canvas.drawRect(r, chosenFrame)
            canvas.drawCircle(cx, cy, radius, checkFill)
            checkPath.reset()
            checkPath.moveTo(cx - radius * 0.45f, cy + radius * 0.02f)
            checkPath.lineTo(cx - radius * 0.1f, cy + radius * 0.36f)
            checkPath.lineTo(cx + radius * 0.48f, cy - radius * 0.32f)
            canvas.drawPath(checkPath, checkMark)
        } else {
            canvas.drawRect(r, dimPaint)
            canvas.drawCircle(cx, cy, radius, checkRing)
        }
    }

    // ---------------------------------------------------------------- Two pages side by side

    val spread: Boolean get() = doc?.spread == true

    fun setSpread(on: Boolean) {
        val d = doc ?: return
        if (d.spread == on) return
        val keep = readingPosition()
        d.spread = on
        DataManager.docPositionChanged()
        zoom = 1f
        scrollPx = 0f
        layoutPages()
        restorePosition(keep)
        tiles.clear()
        afterMove()
        scheduleDetail()
        onToolsChanged?.invoke()
    }

    // ---------------------------------------------------------------- Bookmarks

    fun isBookmarked(page: Int) = doc?.bookmarks?.contains(page) == true

    /** Bookmarks the page (or removes its bookmark). Returns true if it is now bookmarked. */
    fun toggleBookmark(page: Int): Boolean {
        val d = doc ?: return false
        val on = if (d.bookmarks.contains(page)) {
            d.bookmarks.remove(page)
            false
        } else {
            d.bookmarks.add(page)
            true
        }
        DataManager.docPositionChanged()
        invalidate()
        return on
    }

    private fun drawRibbon(canvas: Canvas, r: RectF, w: Float) {
        val h = w * 1.5f
        val x = r.right - w * 1.6f
        ribbonPath.reset()
        ribbonPath.moveTo(x, r.top)
        ribbonPath.lineTo(x + w, r.top)
        ribbonPath.lineTo(x + w, r.top + h)
        ribbonPath.lineTo(x + w / 2f, r.top + h - w * 0.45f)
        ribbonPath.lineTo(x, r.top + h)
        ribbonPath.close()
        canvas.drawPath(ribbonPath, ribbonPaint)
    }

    // ---------------------------------------------------------------- Snipping part of a page

    var snipping = false
        private set
    private var snipPage = -1
    private var snipX0 = 0f
    private var snipY0 = 0f
    private var snipX1 = 0f
    private var snipY1 = 0f
    private val snipFill = Paint().apply { color = Color.parseColor("#33FACC15") }
    private val snipEdge = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 2f * density
        color = accent
    }
    private val snipShade = Paint().apply { color = Color.parseColor("#660E0E10") }

    fun setSnipping(on: Boolean) {
        if (snipping == on) return
        if (on) stopChoosing()
        snipping = on
        snipPage = -1
        invalidate()
        onToolsChanged?.invoke()
    }

    private fun snipRect(out: RectF) {
        out.set(min(snipX0, snipX1), min(snipY0, snipY1), max(snipX0, snipX1), max(snipY0, snipY1))
    }

    private fun snipTouch(e: MotionEvent) {
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                snipPage = pageAt(e.x, e.y)
                snipX0 = e.x; snipY0 = e.y; snipX1 = e.x; snipY1 = e.y
            }
            MotionEvent.ACTION_POINTER_DOWN -> snipPage = -1 // two fingers: zooming instead
            MotionEvent.ACTION_MOVE -> if (snipPage >= 0 && e.pointerCount == 1) {
                pageRect(snipPage, tmp)
                snipX1 = e.x.coerceIn(tmp.left, tmp.right)
                snipY1 = e.y.coerceIn(tmp.top, tmp.bottom)
                snipX0 = snipX0.coerceIn(tmp.left, tmp.right)
                snipY0 = snipY0.coerceIn(tmp.top, tmp.bottom)
                invalidate()
            }
            MotionEvent.ACTION_UP -> {
                val page = snipPage
                snipPage = -1
                invalidate()
                if (page < 0) return
                snipRect(rect)
                if (rect.width() < 16f * density || rect.height() < 16f * density) return
                pageRect(page, tmp)
                val frac = RectF(
                    (rect.left - tmp.left) / tmp.width(), (rect.top - tmp.top) / tmp.height(),
                    (rect.right - tmp.left) / tmp.width(), (rect.bottom - tmp.top) / tmp.height()
                )
                setSnipping(false)
                onSnipped?.invoke(page, frac)
            }
            MotionEvent.ACTION_CANCEL -> {
                snipPage = -1
                invalidate()
            }
        }
    }

    // ---------------------------------------------------------------- Search results

    /** One match: the page and the box around the found text, as fractions of the page. */
    class Hit(val page: Int, val box: RectF)

    private val hits = ArrayList<Hit>()
    private val hitsByPage = HashMap<Int, MutableList<Int>>()
    var hitIndex = -1
        private set
    val hitCount: Int get() = hits.size
    private val hitFill = Paint().apply { color = Color.parseColor("#66FACC15") }
    private val hitCurrent = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 2.5f * density
        color = Color.parseColor("#F97316")
    }

    fun clearHits() {
        hits.clear()
        hitsByPage.clear()
        hitIndex = -1
        invalidate()
    }

    fun addHits(batch: List<Hit>) {
        for (h in batch) {
            hitsByPage.getOrPut(h.page) { ArrayList() }.add(hits.size)
            hits.add(h)
        }
        invalidate()
    }

    /** Scrolls so match [i] is in view and marks it. */
    fun showHit(i: Int) {
        if (hits.isEmpty()) return
        hitIndex = ((i % hits.size) + hits.size) % hits.size
        val h = hits[hitIndex]
        if (h.page !in pTop.indices) return
        val availH = (height - paddingTop - paddingBottom).toFloat()
        val yInPage = pTop[h.page] + h.box.top * pH[h.page]
        val targetY = (yInPage * zoom - availH * 0.3f).coerceIn(0f, maxScrollY())
        var targetX = scrollPx
        if (maxScrollX() > 0f) {
            val xInCol = sideMargin + pLeft[h.page] + h.box.centerX() * pW[h.page]
            targetX = (xInCol * zoom - availW() / 2f).coerceIn(0f, maxScrollX())
        }
        scroller.forceFinished(true)
        scroller.startScroll(scrollPx.toInt(), scrollPy.toInt(), (targetX - scrollPx).toInt(), (targetY - scrollPy).toInt(), 280)
        postInvalidateOnAnimation()
    }

    private fun drawHits(canvas: Canvas, page: Int, r: RectF) {
        val list = hitsByPage[page] ?: return
        for (k in list) {
            val b = hits[k].box
            tmp.set(r.left + b.left * r.width(), r.top + b.top * r.height(), r.left + b.right * r.width(), r.top + b.bottom * r.height())
            canvas.drawRect(tmp, hitFill)
            if (k == hitIndex) {
                tmp.inset(-2f * density, -2f * density)
                canvas.drawRect(tmp, hitCurrent)
            }
        }
    }

    // ---------------------------------------------------------------- Page strip (thumbnails on the left)

    var stripShown = false
        private set
    private val stripW get() = if (stripShown) (if (width < 520 * density) 78f else 104f) * density else 0f
    private var stripTops = FloatArray(0)
    private var stripHs = FloatArray(0)
    private var stripTotal = 0f
    private var stripScroll = 0f
    private val stripScroller = OverScroller(context)
    private var stripTouch = false
    private var stripDownY = 0f
    private var stripLastY = 0f
    private var stripMoved = false
    private var velocity: VelocityTracker? = null
    private val stripBg = Paint().apply { color = Color.parseColor("#F217171A") }
    private val stripEdge = Paint().apply { color = Color.parseColor("#2C2C33") }
    private val stripLabel = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#A1A1AA")
        textSize = 11f * density
        textAlign = Paint.Align.CENTER
    }
    private val stripCurrent = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 2.5f * density
        color = accent
    }
    private val stripCell = Paint().apply { color = Color.parseColor("#2A2A31") }

    fun setStripShown(on: Boolean) {
        if (stripShown == on) return
        val keep = if (pTop.isNotEmpty()) readingPosition() else null
        stripShown = on
        layoutPages()
        if (keep != null) restorePosition(keep)
        if (on) revealInStrip(currentPage, center = true)
        invalidate()
        onToolsChanged?.invoke()
    }

    private fun layoutStrip() {
        val d = doc ?: return
        val pad = 8f * density
        val tw = stripW - 2 * pad
        val label = 16f * density
        stripTops = FloatArray(d.pageCount)
        stripHs = FloatArray(d.pageCount)
        var y = pad
        for (i in 0 until d.pageCount) {
            stripTops[i] = y
            stripHs[i] = (tw * d.aspect(i)).coerceIn(tw * 0.4f, tw * 1.6f)
            y += stripHs[i] + label + 6f * density
        }
        stripTotal = y
        stripScroll = stripScroll.coerceIn(0f, maxStripScroll())
    }

    private fun stripAreaTop() = paddingTop.toFloat()
    private fun stripAreaBottom() = (height - paddingBottom).toFloat()
    private fun maxStripScroll() = max(0f, stripTotal - (stripAreaBottom() - stripAreaTop()))

    private fun firstStripCellBelow(y: Float): Int {
        var lo = 0
        var hi = stripTops.size - 1
        val target = y - stripAreaTop() + stripScroll
        while (lo < hi) {
            val mid = (lo + hi) / 2
            if (stripTops[mid] + stripHs[mid] < target) lo = mid + 1 else hi = mid
        }
        return lo
    }

    /** Scrolls the strip so page [page] is in it (or in its middle). */
    private fun revealInStrip(page: Int, center: Boolean = false) {
        if (!stripShown || page !in stripTops.indices) return
        val viewH = stripAreaBottom() - stripAreaTop()
        val top = stripTops[page]
        val bottom = top + stripHs[page] + 16f * density
        stripScroll = when {
            center -> top - viewH / 2f + stripHs[page] / 2f
            top < stripScroll -> top - 8f * density
            bottom > stripScroll + viewH -> bottom - viewH + 8f * density
            else -> stripScroll
        }.coerceIn(0f, maxStripScroll())
    }

    private fun drawStrip(canvas: Canvas, d: ViewerDoc) {
        val left = paddingLeft.toFloat()
        val right = left + stripW
        val top = stripAreaTop()
        val bottom = stripAreaBottom()
        canvas.drawRect(left, top, right, bottom, stripBg)
        canvas.drawRect(right - 1f * density, top, right, bottom, stripEdge)
        if (stripTops.isEmpty()) return
        canvas.save()
        canvas.clipRect(left, top, right, bottom)
        val pad = 8f * density
        val tw = stripW - 2 * pad
        val wanted = ArrayList<Int>()
        // The page (or both pages, side by side) on screen is framed.
        val curRow = rowOf.getOrElse(currentPage) { 0 }
        val curFirst = rowStart.getOrElse(curRow) { currentPage }
        val curEnd = rowEnd.getOrElse(curRow) { currentPage + 1 }
        var i = firstStripCellBelow(top)
        while (i < stripTops.size) {
            val y = top + stripTops[i] - stripScroll
            if (y > bottom) break
            // Keep the page's shape inside the cell.
            val aspect = d.aspect(i)
            var w = tw
            var h = tw * aspect
            if (h > stripHs[i]) {
                h = stripHs[i]
                w = h / aspect
            }
            val x = left + pad + (tw - w) / 2f
            rect.set(x, y + (stripHs[i] - h) / 2f, x + w, y + (stripHs[i] - h) / 2f + h)
            val bmp = PdfPages.thumb(d.docId, i)
            if (bmp != null && canvas.canDraw(bmp)) {
                canvas.drawBitmap(bmp, null, rect, Paints.normal)
            } else {
                canvas.drawRect(rect, stripCell)
                wanted.add(i)
            }
            if (i in curFirst until curEnd) {
                tmp.set(rect)
                tmp.inset(-2f * density, -2f * density)
                canvas.drawRect(tmp, stripCurrent)
            }
            if (d.bookmarks.contains(i)) drawRibbon(canvas, rect, 7f * density)
            if (hitsByPage.containsKey(i)) canvas.drawCircle(rect.left + 6f * density, rect.top + 6f * density, 4f * density, thumbPaint)
            canvas.drawText("${i + 1}", left + stripW / 2f, y + stripHs[i] + 13f * density, stripLabel)
            i++
        }
        canvas.restore()
        if (wanted.isNotEmpty()) PdfPages.requestThumbs(d.docId, wanted)
    }

    private fun handleStripTouch(e: MotionEvent): Boolean {
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                stripScroller.forceFinished(true)
                stripDownY = e.y
                stripLastY = e.y
                stripMoved = false
                velocity?.recycle()
                velocity = VelocityTracker.obtain().also { it.addMovement(e) }
            }
            MotionEvent.ACTION_MOVE -> {
                velocity?.addMovement(e)
                if (abs(e.y - stripDownY) > 8f * density) stripMoved = true
                stripScroll = (stripScroll - (e.y - stripLastY)).coerceIn(0f, maxStripScroll())
                stripLastY = e.y
                invalidate()
            }
            MotionEvent.ACTION_UP -> {
                velocity?.addMovement(e)
                if (!stripMoved) {
                    val i = firstStripCellBelow(e.y)
                    val y = stripAreaTop() + stripTops.getOrElse(i) { 0f } - stripScroll
                    if (i in stripTops.indices && e.y >= y - 4f * density && e.y <= y + stripHs[i] + 18f * density) goToPage(i)
                } else {
                    velocity?.let {
                        it.computeCurrentVelocity(1000)
                        stripScroller.fling(0, stripScroll.toInt(), 0, (-it.yVelocity).toInt(), 0, 0, 0, maxStripScroll().toInt())
                        postInvalidateOnAnimation()
                    }
                }
                velocity?.recycle()
                velocity = null
            }
            MotionEvent.ACTION_CANCEL -> {
                velocity?.recycle()
                velocity = null
            }
        }
        return true
    }

    // ---------------------------------------------------------------- Sharp zoom tiles

    private class Tile(val docId: String, val page: Int, val zoom: Float, val area: RectF, val bitmap: Bitmap)

    private val tiles = ArrayList<Tile>()
    private var detailToken = 0
    private val detailRunnable = Runnable { requestDetail() }

    // ---------------------------------------------------------------- Scroll thumb

    private var thumbVisibleUntil = 0L
    private var draggingThumb = false
    private val thumbH = 56f * density
    private val thumbW = 6f * density
    private val thumbTouchW = 36f * density
    private val hideThumb = Runnable { invalidate() }

    // ---------------------------------------------------------------- Gestures

    private val scaleDetector = ScaleGestureDetector(context, object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
        override fun onScaleBegin(d: ScaleGestureDetector): Boolean {
            zoomAnimator?.cancel()
            return true
        }

        override fun onScale(d: ScaleGestureDetector): Boolean {
            zoomAround(d.focusX, d.focusY, zoom * d.scaleFactor)
            return true
        }
    }).apply { isQuickScaleEnabled = false }

    private val gestures = GestureDetector(context, object : GestureDetector.SimpleOnGestureListener() {
        override fun onDown(e: MotionEvent) = true

        override fun onScroll(e1: MotionEvent?, e2: MotionEvent, dx: Float, dy: Float): Boolean {
            if (draggingThumb) return true
            moveTo(scrollPx + dx, scrollPy + dy)
            return true
        }

        override fun onFling(e1: MotionEvent?, e2: MotionEvent, vx: Float, vy: Float): Boolean {
            if (draggingThumb || scaleDetector.isInProgress) return false
            scroller.fling(
                scrollPx.toInt(), scrollPy.toInt(), (-vx).toInt(), (-vy).toInt(),
                0, maxScrollX().toInt(), 0, maxScrollY().toInt()
            )
            postInvalidateOnAnimation()
            return true
        }

        override fun onSingleTapUp(e: MotionEvent): Boolean {
            if (choosing && !draggingThumb) toggleChosenAt(e.x, e.y)
            return choosing
        }

        override fun onDoubleTap(e: MotionEvent): Boolean {
            if (choosing) {
                toggleChosenAt(e.x, e.y) // a quick second tap chooses the page under it
                return true
            }
            animateZoom(e.x, e.y, if (zoom < 1.6f) 2.5f else 1f)
            return true
        }

        override fun onLongPress(e: MotionEvent) {
            if (scaleDetector.isInProgress || draggingThumb || choosing) return
            val page = pageAt(e.x, e.y)
            if (page < 0) return
            performHapticFeedback(HapticFeedbackConstants.LONG_PRESS)
            onLongPressed?.invoke(e.x, e.y, page)
        }
    })

    // ---------------------------------------------------------------- Lifecycle

    private val pageReady: () -> Unit = { if (visibility == VISIBLE) invalidate() }

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        DataManager.addListener(this)
        PdfPages.addListener(pageReady)
        bindDoc()
    }

    override fun onDetachedFromWindow() {
        savePosition()
        DataManager.removeListener(this)
        PdfPages.removeListener(pageReady)
        PdfPages.release(this)
        removeCallbacks(detailRunnable)
        tiles.clear()
        super.onDetachedFromWindow()
    }

    override fun onDocsChanged() = bindDoc()

    override fun onModeChanged() {
        if (DataManager.mode == DataManager.MODE_PDF) {
            requestPages(force = true)
            scheduleDetail()
        } else {
            savePosition()
            PdfPages.release(this)
            tiles.clear()
            setSnipping(false)
        }
    }

    override fun onVisibilityChanged(changedView: View, visibility: Int) {
        super.onVisibilityChanged(changedView, visibility)
        if (visibility != VISIBLE) tiles.clear()
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        super.onSizeChanged(w, h, oldw, oldh)
        val keep = if (doc != null && laidOutWidth > 0) readingPosition() else null
        layoutPages()
        if (keep != null) restorePosition(keep)
    }

    /** Picks up the current document (or a switch to another one). */
    private fun bindDoc() {
        val newDoc = DataManager.currentDoc
        if (newDoc === doc) return
        savePosition()
        doc = newDoc
        choosing = false
        snipping = false
        hits.clear()
        hitsByPage.clear()
        hitIndex = -1
        tiles.clear()
        zoom = 1f
        scrollPx = 0f
        scrollPy = 0f
        stripScroll = 0f
        needsRestore = true
        laidOutWidth = 0
        layoutPages()
        invalidate()
        onToolsChanged?.invoke()
    }

    private fun layoutPages() {
        val d = doc ?: return
        val availW = (width - paddingLeft - paddingRight - stripW).toInt()
        if (availW <= 0) return
        laidOutWidth = availW
        columnW = (availW - 2 * sideMargin).coerceAtLeast(80f)
        val n = d.pageCount
        pLeft = FloatArray(n)
        pTop = FloatArray(n)
        pW = FloatArray(n)
        pH = FloatArray(n)
        rowOf = IntArray(n)
        // Rows: the cover alone, then pairs (like an open book) in a spread; one page per row otherwise.
        val starts = ArrayList<Int>()
        if (d.spread && n > 1) {
            starts.add(0)
            var i = 1
            while (i < n) {
                starts.add(i)
                i += 2
            }
        } else {
            for (i in 0 until n) starts.add(i)
        }
        val rows = starts.size
        rowTop = FloatArray(rows)
        rowH = FloatArray(rows)
        rowStart = IntArray(rows)
        rowEnd = IntArray(rows)
        var y = 0f
        val half = (columnW - gap) / 2f
        for ((r, s) in starts.withIndex()) {
            val e = if (r + 1 < rows) starts[r + 1] else n
            rowStart[r] = s
            rowEnd[r] = e
            rowTop[r] = y
            var h = 0f
            if (!d.spread || n == 1) {
                pLeft[s] = 0f
                pW[s] = columnW
                pH[s] = columnW * d.aspect(s)
                h = pH[s]
            } else if (e - s == 1) {
                pLeft[s] = (columnW - half) / 2f
                pW[s] = half
                pH[s] = half * d.aspect(s)
                h = pH[s]
            } else {
                for (k in s until e) {
                    pLeft[k] = if (k == s) 0f else half + gap
                    pW[k] = half
                    pH[k] = half * d.aspect(k)
                    h = max(h, pH[k])
                }
            }
            for (k in s until e) {
                rowOf[k] = r
                pTop[k] = y + (h - pH[k]) / 2f
            }
            rowH[r] = h
            y += h + gap
        }
        totalH = max(0f, y - gap)
        tiles.clear()
        layoutStrip()
        if (needsRestore) {
            needsRestore = false
            restorePosition(d.position)
        } else {
            clampScroll()
        }
        requestPages(force = true)
        invalidate()
    }

    // ---------------------------------------------------------------- Geometry

    private fun availW() = width - paddingLeft - paddingRight - stripW

    /** Screen x of the column's left edge. */
    private fun originX(): Float {
        val contentW = (columnW + 2 * sideMargin) * zoom
        val free = availW() - contentW
        return paddingLeft + stripW + (if (free > 0) free / 2f else -scrollPx) + sideMargin * zoom
    }

    /** Screen y of layout y = 0. */
    private fun originY(): Float = paddingTop + gap - scrollPy

    private fun maxScrollX(): Float = max(0f, (columnW + 2 * sideMargin) * zoom - availW())
    private fun maxScrollY(): Float = max(0f, totalH * zoom + 2 * gap + paddingTop + paddingBottom - height)

    private fun clampScroll() {
        scrollPx = scrollPx.coerceIn(0f, maxScrollX())
        scrollPy = scrollPy.coerceIn(0f, maxScrollY())
    }

    private fun pageRect(i: Int, out: RectF) {
        val left = originX() + pLeft[i] * zoom
        val top = originY() + pTop[i] * zoom
        out.set(left, top, left + pW[i] * zoom, top + pH[i] * zoom)
    }

    /** First row whose bottom is below screen y. */
    private fun firstRowBelow(screenY: Float): Int {
        val target = (screenY - originY()) / zoom
        var lo = 0
        var hi = rowTop.size - 1
        while (lo < hi) {
            val mid = (lo + hi) / 2
            if (rowTop[mid] + rowH[mid] < target) lo = mid + 1 else hi = mid
        }
        return lo
    }

    /** The page under a screen point, or -1. */
    private fun pageAt(x: Float, y: Float): Int {
        if (rowTop.isEmpty()) return -1
        val r = firstRowBelow(y)
        for (i in rowStart[r] until rowEnd[r]) {
            pageRect(i, tmp)
            if (x >= tmp.left - gap / 2f && x <= tmp.right + gap / 2f && y >= tmp.top && y <= tmp.bottom) return i
        }
        return -1
    }

    // ---------------------------------------------------------------- Position (saved per document)

    /** Page index + fraction at the top of the reading area. */
    private fun readingPosition(): Float {
        if (rowTop.isEmpty()) return 0f
        val y = (paddingTop - originY()) / zoom
        val r = firstRowBelow(paddingTop.toFloat())
        val frac = ((y - rowTop[r]) / rowH[r].coerceAtLeast(1f)).coerceIn(0f, 0.999f)
        return rowStart[r] + frac
    }

    private fun restorePosition(pos: Float) {
        if (rowTop.isEmpty()) return
        val i = pos.toInt().coerceIn(0, rowOf.size - 1)
        val r = rowOf[i]
        val y = rowTop[r] + (pos - i).coerceIn(0f, 1f) * rowH[r]
        scrollPy = gap + y * zoom - gap
        clampScroll()
        updateCurrentPage()
    }

    private fun savePosition() {
        val d = doc ?: return
        if (rowTop.isEmpty()) return
        val p = readingPosition()
        if (abs(p - d.position) > 0.001f) {
            d.position = p
            DataManager.docPositionChanged()
        }
    }

    private fun updateCurrentPage() {
        val d = doc ?: return
        if (rowTop.isEmpty()) return
        val probe = paddingTop + (height - paddingTop - paddingBottom) * 0.3f
        val p = rowStart[firstRowBelow(probe)]
        if (p != currentPage) {
            currentPage = p
            savePosition()
            if (!stripTouch) revealInStrip(p)
        }
        if (reportedPage != currentPage || reportedDoc !== d) {
            reportedPage = currentPage
            reportedDoc = d
            onPageChanged?.invoke(currentPage, d.pageCount)
        }
    }

    private var reportedPage = -1
    private var reportedDoc: ViewerDoc? = null

    /** Shows the page number again (used when a screen attaches its toolbar). */
    fun reportPage() {
        reportedPage = -1
        updateCurrentPage()
    }

    /** "12" or, side by side, "12–13". */
    fun pageLabel(page: Int): String {
        if (!spread || page !in rowOf.indices) return "${page + 1}"
        val r = rowOf[page]
        return if (rowEnd[r] - rowStart[r] > 1) "${rowStart[r] + 1}–${rowEnd[r]}" else "${rowStart[r] + 1}"
    }

    // ---------------------------------------------------------------- Public actions

    fun goToPage(page: Int, animate: Boolean = true) {
        if (rowTop.isEmpty()) return
        val i = page.coerceIn(0, rowOf.size - 1)
        val target = (rowTop[rowOf[i]] * zoom).coerceIn(0f, maxScrollY())
        if (animate) {
            scroller.forceFinished(true)
            scroller.startScroll(scrollPx.toInt(), scrollPy.toInt(), 0, (target - scrollPy).toInt(), 320)
            postInvalidateOnAnimation()
        } else {
            moveTo(scrollPx, target)
        }
    }

    fun nextPage() {
        if (rowTop.isEmpty()) return
        val r = rowOf[currentPage.coerceIn(0, rowOf.size - 1)]
        if (r + 1 < rowStart.size) goToPage(rowStart[r + 1])
    }

    fun prevPage() {
        if (rowTop.isEmpty()) return
        val r = rowOf[currentPage.coerceIn(0, rowOf.size - 1)]
        val inRow = readingPosition() - rowStart[r]
        goToPage(if (inRow > 0.05f || r == 0) rowStart[r] else rowStart[r - 1])
    }

    /** Back to page-width zoom, keeping the current page in view. */
    fun fitWidth() {
        animateZoom(width / 2f, paddingTop.toFloat(), 1f)
    }

    /** Switches between "fit page width" and "whole page on screen". */
    fun toggleFit() {
        if (rowTop.isEmpty()) return
        val row = rowOf[currentPage.coerceIn(0, rowOf.size - 1)]
        val availH = (height - paddingTop - paddingBottom).toFloat() - 2 * gap
        val wholePage = (availH / rowH[row].coerceAtLeast(1f)).coerceIn(MIN_ZOOM, 1f)
        val target = if (abs(zoom - 1f) < 0.03f && wholePage < 0.97f) wholePage else 1f
        zoomAnimator?.cancel()
        zoomAnimator = ValueAnimator.ofFloat(zoom, target).apply {
            duration = 220
            interpolator = DecelerateInterpolator()
            addUpdateListener {
                zoomAround(width / 2f, paddingTop.toFloat(), it.animatedValue as Float)
                // keep the row's top just under the bar
                scrollPy = (rowTop[row] * zoom).coerceIn(0f, maxScrollY())
                clampScroll()
                invalidate()
            }
            addListener(object : android.animation.AnimatorListenerAdapter() {
                override fun onAnimationEnd(animation: android.animation.Animator) {
                    afterMove()
                    scheduleDetail()
                }
            })
            start()
        }
    }

    // ---------------------------------------------------------------- Scrolling & zoom

    private fun moveTo(x: Float, y: Float) {
        scrollPx = x
        scrollPy = y
        clampScroll()
        afterMove()
    }

    private fun afterMove() {
        thumbVisibleUntil = System.currentTimeMillis() + 1200
        removeCallbacks(hideThumb)
        postDelayed(hideThumb, 1250)
        updateCurrentPage()
        requestPages()
        invalidate()
    }

    private fun zoomAround(fx: Float, fy: Float, newZoom: Float) {
        if (rowTop.isEmpty()) return
        val nz = newZoom.coerceIn(MIN_ZOOM, MAX_ZOOM)
        if (nz == zoom) return
        val lx = (fx - originX()) / zoom
        val ly = (fy - originY()) / zoom
        zoom = nz
        tiles.clear()
        val contentW = (columnW + 2 * sideMargin) * zoom
        scrollPx = if (contentW > availW()) paddingLeft + stripW + sideMargin * zoom + lx * zoom - fx else 0f
        scrollPy = paddingTop + gap + ly * zoom - fy
        clampScroll()
        afterMove()
    }

    private fun animateZoom(fx: Float, fy: Float, target: Float) {
        zoomAnimator?.cancel()
        zoomAnimator = ValueAnimator.ofFloat(zoom, target).apply {
            duration = 220
            interpolator = DecelerateInterpolator()
            addUpdateListener { zoomAround(fx, fy, it.animatedValue as Float) }
            addListener(object : android.animation.AnimatorListenerAdapter() {
                override fun onAnimationEnd(animation: android.animation.Animator) = scheduleDetail()
            })
            start()
        }
    }

    override fun computeScroll() {
        if (stripScroller.computeScrollOffset()) {
            stripScroll = stripScroller.currY.toFloat().coerceIn(0f, maxStripScroll())
            postInvalidateOnAnimation()
        }
        if (scroller.computeScrollOffset()) {
            scrollPx = scroller.currX.toFloat()
            scrollPy = scroller.currY.toFloat()
            clampScroll()
            afterMove()
            if (scroller.isFinished) scheduleDetail()
            else postInvalidateOnAnimation()
        }
    }

    // ---------------------------------------------------------------- Touch

    override fun onTouchEvent(e: MotionEvent): Boolean {
        if (doc == null || rowTop.isEmpty()) return true
        if (e.actionMasked == MotionEvent.ACTION_DOWN) {
            stripTouch = stripShown && e.x >= paddingLeft && e.x < paddingLeft + stripW &&
                e.y >= stripAreaTop() && e.y <= stripAreaBottom()
        }
        if (stripTouch) {
            if (e.actionMasked == MotionEvent.ACTION_DOWN) {
                onTouchStarted?.invoke()
                parent?.requestDisallowInterceptTouchEvent(true)
            }
            handleStripTouch(e)
            if (e.actionMasked == MotionEvent.ACTION_UP || e.actionMasked == MotionEvent.ACTION_CANCEL) stripTouch = false
            return true
        }
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                onTouchStarted?.invoke()
                parent?.requestDisallowInterceptTouchEvent(true)
                scroller.forceFinished(true)
                zoomAnimator?.cancel()
                interacting = true
                removeCallbacks(detailRunnable)
                draggingThumb = !snipping && isOnThumb(e.x, e.y)
                if (draggingThumb) dragThumb(e.y)
            }
            MotionEvent.ACTION_MOVE -> if (draggingThumb) dragThumb(e.y)
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                interacting = false
                draggingThumb = false
                savePosition()
                if (scroller.isFinished) scheduleDetail()
            }
        }
        scaleDetector.onTouchEvent(e)
        if (snipping) {
            snipTouch(e) // one finger draws the box; two fingers zoom
            return true
        }
        if (!draggingThumb) gestures.onTouchEvent(e)
        return true
    }

    private fun thumbTrack(out: RectF) {
        out.set(width - paddingRight - thumbTouchW, paddingTop + 8f * density, (width - paddingRight).toFloat(), height - paddingBottom - 8f * density)
    }

    private fun isOnThumb(x: Float, y: Float): Boolean {
        if ((doc?.pageCount ?: 0) < 4 || maxScrollY() <= 0f) return false
        if (System.currentTimeMillis() > thumbVisibleUntil) return false
        thumbTrack(tmp)
        return x >= tmp.left && y >= tmp.top && y <= tmp.bottom
    }

    private fun dragThumb(y: Float) {
        thumbTrack(tmp)
        val f = ((y - tmp.top - thumbH / 2f) / (tmp.height() - thumbH)).coerceIn(0f, 1f)
        moveTo(scrollPx, f * maxScrollY())
    }

    // ---------------------------------------------------------------- Rendering

    /** Asks for the pages on screen plus one row above and below. */
    private var requestedFirst = -1
    private var requestedLast = -1
    private var requestedDoc: ViewerDoc? = null

    private fun requestPages(force: Boolean = false) {
        val d = doc ?: return
        if (rowTop.isEmpty() || DataManager.mode != DataManager.MODE_PDF) return
        val firstRow = firstRowBelow(0f)
        val lastRow = firstRowBelow(height.toFloat())
        val first = rowStart[firstRow]
        val last = rowEnd[lastRow] - 1
        if (!force && first == requestedFirst && last == requestedLast && requestedDoc === d) return
        requestedFirst = first
        requestedLast = last
        requestedDoc = d
        val list = ArrayList<Pose.PdfPage>(last - first + 5)
        for (i in first..last) list.add(Pose.PdfPage(d.docId, i))
        if (lastRow + 1 < rowStart.size) for (i in rowStart[lastRow + 1] until rowEnd[lastRow + 1]) list.add(Pose.PdfPage(d.docId, i))
        if (firstRow - 1 >= 0) for (i in rowStart[firstRow - 1] until rowEnd[firstRow - 1]) list.add(Pose.PdfPage(d.docId, i))
        PdfPages.focus(this, list)
    }

    override fun onDraw(canvas: Canvas) {
        canvas.drawColor(bg)
        val d = doc ?: return
        if (rowTop.isEmpty()) return
        val firstRow = firstRowBelow(0f)
        val shadow = 3f * density
        var missing = false
        var r = firstRow
        while (r < rowTop.size) {
            if (originY() + rowTop[r] * zoom > height) break
            for (i in rowStart[r] until rowEnd[r]) {
                pageRect(i, rect)
                canvas.drawRect(rect.left + shadow, rect.top + shadow, rect.right + shadow, rect.bottom + shadow, shadowPaint)
                canvas.drawRect(rect, pagePaint)
                val bmp = PdfPages.get(d.docId, i)
                if (bmp != null) {
                    if (canvas.canDraw(bmp)) canvas.drawBitmap(bmp, null, rect, Paints.normal)
                } else {
                    canvas.drawText("${i + 1}", rect.centerX(), rect.centerY(), numberPaint)
                    if (!PdfPages.hasFailed(d.docId, i)) missing = true
                }
            }
            r++
        }
        if (missing) post { requestPages(force = true) } // e.g. pages dropped to save memory
        // Sharp tiles on top, only when they match the current zoom.
        for (t in tiles) {
            if (t.docId != d.docId || t.zoom != zoom || t.page !in pTop.indices) continue
            pageRect(t.page, rect)
            tmp.set(rect.left + t.area.left * zoom, rect.top + t.area.top * zoom, rect.left + t.area.right * zoom, rect.top + t.area.bottom * zoom)
            if (canvas.canDraw(t.bitmap)) canvas.drawBitmap(t.bitmap, null, tmp, Paints.normal)
        }
        // Overlays: search results, bookmarks, choosing, snipping.
        r = firstRow
        while (r < rowTop.size) {
            if (originY() + rowTop[r] * zoom > height) break
            for (i in rowStart[r] until rowEnd[r]) {
                pageRect(i, rect)
                if (hitsByPage.isNotEmpty()) drawHits(canvas, i, rect)
                if (d.bookmarks.contains(i)) drawRibbon(canvas, rect, (14f * density * min(zoom, 1.5f)).coerceAtLeast(8f * density))
                if (choosing) drawChoice(canvas, i, rect)
            }
            r++
        }
        if (snipping) {
            if (snipPage >= 0) {
                snipRect(tmp)
                canvas.drawRect(0f, 0f, width.toFloat(), tmp.top, snipShade)
                canvas.drawRect(0f, tmp.bottom, width.toFloat(), height.toFloat(), snipShade)
                canvas.drawRect(0f, tmp.top, tmp.left, tmp.bottom, snipShade)
                canvas.drawRect(tmp.right, tmp.top, width.toFloat(), tmp.bottom, snipShade)
                canvas.drawRect(tmp, snipFill)
                canvas.drawRect(tmp, snipEdge)
            } else {
                canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), snipShade)
            }
        }
        drawThumb(canvas)
        if (stripShown) drawStrip(canvas, d)
    }

    private fun drawThumb(canvas: Canvas) {
        if ((doc?.pageCount ?: 0) < 4 || maxScrollY() <= 0f) return
        if (!draggingThumb && System.currentTimeMillis() > thumbVisibleUntil) return
        thumbTrack(tmp)
        val x = tmp.right - 8f * density - thumbW / 2f
        val top = tmp.top + (scrollPy / maxScrollY()) * (tmp.height() - thumbH)
        canvas.drawRoundRect(x - thumbW / 2f, tmp.top, x + thumbW / 2f, tmp.bottom, thumbW, thumbW, thumbTrackPaint)
        canvas.drawRoundRect(x - thumbW / 2f - (if (draggingThumb) 2f * density else 0f), top, x + thumbW / 2f, top + thumbH, thumbW, thumbW, thumbPaint)
    }

    private fun scheduleDetail() {
        removeCallbacks(detailRunnable)
        postDelayed(detailRunnable, 160)
    }

    /** Re-renders what is on screen at full sharpness when zoomed past the cached page quality. */
    private fun requestDetail() {
        val d = doc ?: return
        if (interacting || !scroller.isFinished || rowTop.isEmpty() || visibility != VISIBLE) return
        if (DataManager.mode != DataManager.MODE_PDF) return
        val token = ++detailToken
        val z = zoom
        val screen = RectF(paddingLeft + stripW, 0f, width.toFloat(), height.toFloat())
        // Keep only sharp tiles that are still on screen at this zoom (each can be screen-sized).
        tiles.removeAll { t ->
            if (t.zoom != z || t.docId != d.docId || t.page !in pTop.indices) return@removeAll true
            pageRect(t.page, rect)
            !RectF.intersects(RectF(rect.left + t.area.left * z, rect.top + t.area.top * z, rect.left + t.area.right * z, rect.top + t.area.bottom * z), screen)
        }
        var r = firstRowBelow(0f)
        while (r < rowTop.size) {
            if (originY() + rowTop[r] * zoom > height) break
            for (i in rowStart[r] until rowEnd[r]) {
                pageRect(i, rect)
                val displayW = rect.width()
                if (displayW <= PdfPages.baseWidth(d.aspect(i)) * 1.12f) continue
                tmp.set(rect)
                if (!tmp.intersect(screen)) continue
                // The wanted area, in this page's layout units at the current zoom (relative to the page).
                val area = RectF((tmp.left - rect.left) / z, (tmp.top - rect.top) / z, (tmp.right - rect.left) / z, (tmp.bottom - rect.top) / z)
                val covered = tiles.any { it.page == i && it.zoom == z && it.area.contains(area) }
                if (covered) continue
                val page = i
                PdfPages.renderDetail(
                    d.docId, page, displayW,
                    tmp.left - rect.left, tmp.top - rect.top,
                    tmp.width().toInt(), tmp.height().toInt(),
                    isStale = { token != detailToken },
                ) { bmp ->
                    if (bmp != null && token == detailToken && zoom == z && doc === d) {
                        tiles.add(Tile(d.docId, page, z, area, bmp))
                        while (tiles.size > 4) tiles.removeAt(0)
                        invalidate()
                    }
                }
            }
            r++
        }
    }

    companion object {
        private const val MIN_ZOOM = 0.35f
        private const val MAX_ZOOM = 6f
    }
}
