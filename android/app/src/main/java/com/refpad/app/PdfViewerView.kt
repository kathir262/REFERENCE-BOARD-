package com.refpad.app

import android.animation.ValueAnimator
import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.GestureDetector
import android.view.HapticFeedbackConstants
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.View
import android.view.animation.DecelerateInterpolator
import android.widget.OverScroller
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/**
 * A light PDF reader: pages in one continuous column, pinch to zoom, fling to scroll,
 * and a scroll thumb on the right for long books.
 *
 * Only the pages on screen (and their neighbours) are rendered. When you zoom in, the visible
 * part is re-rendered at full sharpness as soon as you stop moving.
 */
class PdfViewerView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr), DataManager.Listener {

    var onPageChanged: ((page: Int, count: Int) -> Unit)? = null
    var onLongPressed: ((x: Float, y: Float, page: Int) -> Unit)? = null
    var onTouchStarted: (() -> Unit)? = null

    private val density = resources.displayMetrics.density
    private val gap = 14f * density
    private val sideMargin = 14f * density

    private var doc: ViewerDoc? = null
    private var tops = FloatArray(0)      // page tops in layout units (zoom 1)
    private var heights = FloatArray(0)
    private var pageW = 0f                // page width in layout units
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
    private val pagePaint = Paint().apply { color = Color.WHITE }
    private val shadowPaint = Paint().apply { color = Color.parseColor("#55000000") }
    private val numberPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#A1A1AA")
        textSize = 16f * density
        textAlign = Paint.Align.CENTER
    }
    private val thumbPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#FACC15") }
    private val thumbTrackPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#33FFFFFF") }
    private val rect = RectF()
    private val tmp = RectF()

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

        override fun onDoubleTap(e: MotionEvent): Boolean {
            animateZoom(e.x, e.y, if (zoom < 1.6f) 2.5f else 1f)
            return true
        }

        override fun onLongPress(e: MotionEvent) {
            if (scaleDetector.isInProgress || draggingThumb) return
            val page = pageAt(e.y)
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
        tiles.clear()
        zoom = 1f
        scrollPx = 0f
        scrollPy = 0f
        needsRestore = true
        laidOutWidth = 0
        layoutPages()
        invalidate()
    }

    private fun layoutPages() {
        val d = doc ?: return
        val availW = width - paddingLeft - paddingRight
        if (availW <= 0) return
        laidOutWidth = availW
        pageW = (availW - 2 * sideMargin).coerceAtLeast(80f)
        val n = d.pageCount
        tops = FloatArray(n)
        heights = FloatArray(n)
        var y = 0f
        for (i in 0 until n) {
            tops[i] = y
            heights[i] = pageW * d.aspect(i)
            y += heights[i] + gap
        }
        totalH = max(0f, y - gap)
        tiles.clear()
        if (needsRestore) {
            needsRestore = false
            restorePosition(d.position)
        } else {
            clampScroll()
        }
        requestPages()
        invalidate()
    }

    // ---------------------------------------------------------------- Geometry

    private fun availW() = (width - paddingLeft - paddingRight).toFloat()

    /** Screen x of the pages' left edge. */
    private fun originX(): Float {
        val contentW = (pageW + 2 * sideMargin) * zoom
        val free = availW() - contentW
        return paddingLeft + (if (free > 0) free / 2f else -scrollPx) + sideMargin * zoom
    }

    /** Screen y of layout y = 0. */
    private fun originY(): Float = paddingTop + gap - scrollPy

    private fun maxScrollX(): Float = max(0f, (pageW + 2 * sideMargin) * zoom - availW())
    private fun maxScrollY(): Float = max(0f, totalH * zoom + 2 * gap + paddingTop + paddingBottom - height)

    private fun clampScroll() {
        scrollPx = scrollPx.coerceIn(0f, maxScrollX())
        scrollPy = scrollPy.coerceIn(0f, maxScrollY())
    }

    private fun pageRect(i: Int, out: RectF) {
        val left = originX()
        val top = originY() + tops[i] * zoom
        out.set(left, top, left + pageW * zoom, top + heights[i] * zoom)
    }

    /** First page whose bottom is below screen y. */
    private fun firstPageBelow(screenY: Float): Int {
        val target = (screenY - originY()) / zoom
        var lo = 0
        var hi = tops.size - 1
        while (lo < hi) {
            val mid = (lo + hi) / 2
            if (tops[mid] + heights[mid] < target) lo = mid + 1 else hi = mid
        }
        return lo
    }

    private fun pageAt(screenY: Float): Int {
        if (tops.isEmpty()) return -1
        val i = firstPageBelow(screenY)
        pageRect(i, tmp)
        return if (screenY >= tmp.top && screenY <= tmp.bottom) i else -1
    }

    // ---------------------------------------------------------------- Position (saved per document)

    /** Page index + fraction at the top of the reading area. */
    private fun readingPosition(): Float {
        if (tops.isEmpty()) return 0f
        val y = (paddingTop - originY()) / zoom
        val i = firstPageBelow(paddingTop.toFloat())
        val frac = ((y - tops[i]) / heights[i].coerceAtLeast(1f)).coerceIn(0f, 1f)
        return i + frac
    }

    private fun restorePosition(pos: Float) {
        if (tops.isEmpty()) return
        val i = pos.toInt().coerceIn(0, tops.size - 1)
        val y = tops[i] + (pos - i).coerceIn(0f, 1f) * heights[i]
        scrollPy = gap + y * zoom - gap
        clampScroll()
        updateCurrentPage()
    }

    private fun savePosition() {
        val d = doc ?: return
        if (tops.isEmpty()) return
        val p = readingPosition()
        if (abs(p - d.position) > 0.001f) {
            d.position = p
            DataManager.docPositionChanged()
        }
    }

    private fun updateCurrentPage() {
        val d = doc ?: return
        if (tops.isEmpty()) return
        val probe = paddingTop + (height - paddingTop - paddingBottom) * 0.3f
        val p = firstPageBelow(probe)
        if (p != currentPage) {
            currentPage = p
            savePosition()
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

    // ---------------------------------------------------------------- Public actions

    fun goToPage(page: Int, animate: Boolean = true) {
        if (tops.isEmpty()) return
        val i = page.coerceIn(0, tops.size - 1)
        val target = (tops[i] * zoom).coerceIn(0f, maxScrollY())
        if (animate) {
            scroller.forceFinished(true)
            scroller.startScroll(scrollPx.toInt(), scrollPy.toInt(), 0, (target - scrollPy).toInt(), 320)
            postInvalidateOnAnimation()
        } else {
            moveTo(scrollPx, target)
        }
    }

    fun nextPage() = goToPage(currentPage + 1)
    fun prevPage() = goToPage(if (readingPosition() - currentPage > 0.05f) currentPage else currentPage - 1)

    /** Back to page-width zoom, keeping the current page in view. */
    fun fitWidth() {
        animateZoom(width / 2f, paddingTop.toFloat(), 1f)
    }

    /** Switches between "fit page width" and "whole page on screen". */
    fun toggleFit() {
        if (tops.isEmpty()) return
        val page = currentPage
        val availH = (height - paddingTop - paddingBottom).toFloat() - 2 * gap
        val wholePage = (availH / heights[page].coerceAtLeast(1f)).coerceIn(MIN_ZOOM, 1f)
        val target = if (abs(zoom - 1f) < 0.03f && wholePage < 0.97f) wholePage else 1f
        zoomAnimator?.cancel()
        zoomAnimator = ValueAnimator.ofFloat(zoom, target).apply {
            duration = 220
            interpolator = DecelerateInterpolator()
            addUpdateListener {
                zoomAround(width / 2f, paddingTop.toFloat(), it.animatedValue as Float)
                // keep the page's top just under the bar
                scrollPy = (tops[page] * zoom).coerceIn(0f, maxScrollY())
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
        if (tops.isEmpty()) return
        val nz = newZoom.coerceIn(MIN_ZOOM, MAX_ZOOM)
        if (nz == zoom) return
        val lx = (fx - originX()) / zoom
        val ly = (fy - originY()) / zoom
        zoom = nz
        tiles.clear()
        val contentW = (pageW + 2 * sideMargin) * zoom
        scrollPx = if (contentW > availW()) paddingLeft + sideMargin * zoom + lx * zoom - fx else 0f
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
        if (doc == null || tops.isEmpty()) return true
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                onTouchStarted?.invoke()
                parent?.requestDisallowInterceptTouchEvent(true)
                scroller.forceFinished(true)
                zoomAnimator?.cancel()
                interacting = true
                removeCallbacks(detailRunnable)
                draggingThumb = isOnThumb(e.x, e.y)
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

    /** Asks for the pages on screen plus one above and below. */
    private var requestedFirst = -1
    private var requestedLast = -1
    private var requestedDoc: ViewerDoc? = null

    private fun requestPages(force: Boolean = false) {
        val d = doc ?: return
        if (tops.isEmpty() || DataManager.mode != DataManager.MODE_PDF) return
        val first = firstPageBelow(0f)
        val last = firstPageBelow(height.toFloat())
        if (!force && first == requestedFirst && last == requestedLast && requestedDoc === d) return
        requestedFirst = first
        requestedLast = last
        requestedDoc = d
        val list = ArrayList<Pose.PdfPage>(last - first + 3)
        for (i in first..last) list.add(Pose.PdfPage(d.docId, i))
        if (last + 1 < tops.size) list.add(Pose.PdfPage(d.docId, last + 1))
        if (first - 1 >= 0) list.add(Pose.PdfPage(d.docId, first - 1))
        PdfPages.focus(this, list)
    }

    override fun onDraw(canvas: Canvas) {
        canvas.drawColor(bg)
        val d = doc ?: return
        if (tops.isEmpty()) return
        val first = firstPageBelow(0f)
        val shadow = 3f * density
        var i = first
        var missing = false
        while (i < tops.size) {
            pageRect(i, rect)
            if (rect.top > height) break
            canvas.drawRect(rect.left + shadow, rect.top + shadow, rect.right + shadow, rect.bottom + shadow, shadowPaint)
            canvas.drawRect(rect, pagePaint)
            val bmp = PdfPages.get(d.docId, i)
            if (bmp != null) {
                if (canvas.canDraw(bmp)) canvas.drawBitmap(bmp, null, rect, Paints.normal)
            } else {
                canvas.drawText("${i + 1}", rect.centerX(), rect.centerY(), numberPaint)
                if (!PdfPages.hasFailed(d.docId, i)) missing = true
            }
            i++
        }
        if (missing) post { requestPages(force = true) } // e.g. pages dropped to save memory
        // Sharp tiles on top, only when they match the current zoom.
        for (t in tiles) {
            if (t.docId != d.docId || t.zoom != zoom) continue
            val ox = originX()
            val oy = originY()
            tmp.set(ox + t.area.left * zoom, oy + t.area.top * zoom, ox + t.area.right * zoom, oy + t.area.bottom * zoom)
            if (canvas.canDraw(t.bitmap)) canvas.drawBitmap(t.bitmap, null, tmp, Paints.normal)
        }
        drawThumb(canvas)
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
        if (interacting || !scroller.isFinished || tops.isEmpty() || visibility != VISIBLE) return
        if (DataManager.mode != DataManager.MODE_PDF) return
        val token = ++detailToken
        val z = zoom
        // Keep only sharp tiles that are still on screen at this zoom (each can be screen-sized).
        val ox0 = originX()
        val oy0 = originY()
        tiles.removeAll { t ->
            t.zoom != z || t.docId != d.docId ||
                !RectF.intersects(
                    RectF(ox0 + t.area.left * z, oy0 + t.area.top * z, ox0 + t.area.right * z, oy0 + t.area.bottom * z),
                    RectF(0f, 0f, width.toFloat(), height.toFloat())
                )
        }
        val first = firstPageBelow(0f)
        var i = first
        while (i < tops.size) {
            pageRect(i, rect)
            if (rect.top > height) break
            val displayW = rect.width()
            if (displayW > PdfPages.baseWidth(d.aspect(i)) * 1.12f) {
                tmp.set(rect)
                if (tmp.intersect(0f, 0f, width.toFloat(), height.toFloat())) {
                    val ox = originX()
                    val oy = originY()
                    val area = RectF((tmp.left - ox) / z, (tmp.top - oy) / z, (tmp.right - ox) / z, (tmp.bottom - oy) / z)
                    val covered = tiles.any { it.page == i && it.zoom == z && it.area.contains(area) }
                    if (!covered) {
                        val page = i
                        PdfPages.renderDetail(
                            d.docId, page, displayW,
                            tmp.left - rect.left, tmp.top - rect.top,
                            tmp.width().toInt(), tmp.height().toInt(),
                            isStale = { token != detailToken },
                        ) { bmp ->
                            if (bmp != null && token == detailToken && zoom == z && doc === d) {
                                tiles.add(Tile(d.docId, page, z, area, bmp))
                                while (tiles.size > 3) tiles.removeAt(0)
                                invalidate()
                            }
                        }
                    }
                }
            }
            i++
        }
    }

    companion object {
        private const val MIN_ZOOM = 0.35f
        private const val MAX_ZOOM = 6f
    }
}
