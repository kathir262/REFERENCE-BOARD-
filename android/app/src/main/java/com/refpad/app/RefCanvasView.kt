package com.refpad.app

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapShader
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Shader
import android.os.SystemClock
import android.util.AttributeSet
import android.view.GestureDetector
import android.view.HapticFeedbackConstants
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.View
import android.view.ViewConfiguration
import kotlin.math.abs
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min

/**
 * The infinite reference board and the practice viewer.
 * It draws straight from [DataManager], so several of these (full screen + floating window) stay in sync.
 *
 * Board:    drag image = move · corner handle or pinch on selected image = resize · drag empty space = pan
 *           pinch elsewhere = zoom · double-tap = fit · long-press = menu
 * Practice: swipe = next/previous · pinch = zoom · double-tap = reset zoom · long-press = menu
 */
class RefCanvasView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr), DataManager.Listener {

    var onItemLongPressed: ((item: RefBoardItem, x: Float, y: Float) -> Unit)? = null
    var onCanvasLongPressed: ((x: Float, y: Float) -> Unit)? = null
    var onTouchStarted: (() -> Unit)? = null
    var onSelectionChanged: (() -> Unit)? = null

    var selectedItem: RefBoardItem? = null
        private set

    private val density = resources.displayMetrics.density
    private val mode get() = DataManager.mode

    // Board camera
    private var boardScale = 1f
    private var boardOffX = 0f
    private var boardOffY = 0f
    private var needsFit = true

    // Practice camera (extra zoom on top of the fitted page)
    private var poseZoom = 1f
    private var poseOffX = 0f
    private var poseOffY = 0f
    private var shownPose: Pose? = null

    // Reused objects so drawing never allocates
    private val itemRect = RectF()
    private val drawRect = RectF()
    private val visibleRect = RectF()

    private val bgColor = Color.parseColor("#0E0E10")
    private val accent = Color.parseColor("#FACC15")
    private val selectPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = accent; style = Paint.Style.STROKE }
    private val handleFill = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = accent; style = Paint.Style.FILL }
    private val handleRing = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = bgColor; style = Paint.Style.STROKE }
    private val hintPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#71717A")
        textSize = 15f * density
        textAlign = Paint.Align.CENTER
    }
    private val shadowPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#66000000") }

    // Dot grid drawn with one tiled shader (a single draw call, however large the board).
    private val gridTile = 64
    // The tile is opaque (background + dot), so the grid also paints the background in the same single pass.
    private val gridShader = Bitmap.createBitmap(gridTile, gridTile, Bitmap.Config.ARGB_8888).let { tile ->
        tile.eraseColor(bgColor)
        Canvas(tile).drawCircle(gridTile / 2f, gridTile / 2f, 2.2f, Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.parseColor("#2A2A30")
        })
        BitmapShader(tile, Shader.TileMode.REPEAT, Shader.TileMode.REPEAT)
    }
    private val gridPaint = Paint().apply { shader = gridShader }
    private val gridMatrix = Matrix()

    // ---------------------------------------------------------------- Touch state

    private enum class Drag { NONE, PENDING_ITEM, ITEM, RESIZE, PAN, PINCH }

    private var drag = Drag.NONE
    private val touchSlop = ViewConfiguration.get(context).scaledTouchSlop.toFloat()
    private var downX = 0f
    private var downY = 0f
    private var lastX = 0f
    private var lastY = 0f
    private var itemStartX = 0f
    private var itemStartY = 0f
    private var resizeStartScale = 1f
    private var resizeStartDist = 1f
    private var resizeCenterX = 0f
    private var resizeCenterY = 0f
    private var pinchItem: RefBoardItem? = null
    private var lastFocusX = 0f
    private var lastFocusY = 0f
    private var boardDirty = false

    private val scaleDetector = ScaleGestureDetector(context, object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
        override fun onScaleBegin(d: ScaleGestureDetector): Boolean {
            drag = Drag.PINCH
            lastFocusX = d.focusX
            lastFocusY = d.focusY
            pinchItem = null
            if (mode == DataManager.MODE_BOARD) {
                selectedItem?.let { sel ->
                    sel.boundsInto(itemRect)
                    if (itemRect.contains(toBoardX(d.focusX), toBoardY(d.focusY))) pinchItem = sel
                }
            }
            return true
        }

        override fun onScale(d: ScaleGestureDetector): Boolean {
            val f = d.scaleFactor
            if (mode == DataManager.MODE_PRACTICE) {
                val old = poseZoom
                poseZoom = (poseZoom * f).coerceIn(1f, 8f)
                val k = poseZoom / old
                val cx = contentCenterX()
                val cy = contentCenterY()
                poseOffX = d.focusX + (cx + poseOffX - d.focusX) * k - cx + (d.focusX - lastFocusX)
                poseOffY = d.focusY + (cy + poseOffY - d.focusY) * k - cy + (d.focusY - lastFocusY)
                if (poseZoom <= 1.001f) {
                    poseOffX = 0f
                    poseOffY = 0f
                }
                invalidate()
            } else {
                val item = pinchItem
                if (item != null) {
                    item.setScaleAroundCenter(item.scale * f)
                    boardDirty = true
                    DataManager.itemsMoved()
                } else {
                    val old = boardScale
                    boardScale = (boardScale * f).coerceIn(MIN_ZOOM, MAX_ZOOM)
                    val k = boardScale / old
                    boardOffX = d.focusX - (d.focusX - boardOffX) * k + (d.focusX - lastFocusX)
                    boardOffY = d.focusY - (d.focusY - boardOffY) * k + (d.focusY - lastFocusY)
                    invalidate()
                }
            }
            lastFocusX = d.focusX
            lastFocusY = d.focusY
            return true
        }
    }).apply { isQuickScaleEnabled = false }

    private val gestures = GestureDetector(context, object : GestureDetector.SimpleOnGestureListener() {
        override fun onDown(e: MotionEvent) = true

        override fun onLongPress(e: MotionEvent) {
            if (drag == Drag.PINCH || drag == Drag.ITEM || drag == Drag.RESIZE || scaleDetector.isInProgress) return
            drag = Drag.NONE
            performHapticFeedback(HapticFeedbackConstants.LONG_PRESS)
            if (mode == DataManager.MODE_BOARD) {
                val hit = hitTest(e.x, e.y)
                if (hit != null) {
                    select(hit)
                    onItemLongPressed?.invoke(hit, e.x, e.y)
                    return
                }
            }
            onCanvasLongPressed?.invoke(e.x, e.y)
        }

        override fun onDoubleTap(e: MotionEvent): Boolean {
            if (mode == DataManager.MODE_BOARD) {
                val hit = hitTest(e.x, e.y)
                if (hit != null) fitItem(hit) else fitAll()
            } else {
                resetPoseZoom()
            }
            return true
        }

        override fun onFling(e1: MotionEvent?, e2: MotionEvent, vx: Float, vy: Float): Boolean {
            if (mode != DataManager.MODE_PRACTICE || poseZoom > 1.01f) return false
            if (abs(vx) < 600 * density || abs(vx) < abs(vy) * 1.3f) return false
            if (vx < 0) DataManager.nextPose() else DataManager.prevPose()
            PracticeTimer.restartPose()
            return true
        }
    })

    // ---------------------------------------------------------------- Lifecycle

    private val pageReady: () -> Unit = { if (mode == DataManager.MODE_PRACTICE) invalidate() }

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        DataManager.addListener(this)
        PdfPages.addListener(pageReady)
        focusPdfPages()
    }

    override fun onDetachedFromWindow() {
        DataManager.removeListener(this)
        PdfPages.removeListener(pageReady)
        PdfPages.release(this)
        super.onDetachedFromWindow()
    }

    override fun onBoardChanged() {
        val sel = selectedItem
        if (sel != null && !DataManager.items.contains(sel)) select(null)
        if (needsFit && DataManager.items.isNotEmpty()) fitAll()
        invalidate()
    }

    override fun onPracticeChanged() {
        val newPose = DataManager.currentPose()
        val idx = DataManager.practiceIndex
        val n = DataManager.practice.size
        if (newPose != shownPose) {
            // Slide to the next/previous pose instead of jumping.
            val old = lastPoseIndex
            slideDir = when {
                shownPose == null || old < 0 || n < 2 || mode != DataManager.MODE_PRACTICE || !isShown -> 0
                (idx - old + n) % n == 1 -> 1
                (old - idx + n) % n == 1 -> -1
                else -> 0
            }
            if (slideDir != 0) {
                outgoingPose = shownPose
                outgoingFlipped = shownFlipped
                slideStart = SystemClock.uptimeMillis()
            }
            resetPoseZoom()
        }
        lastPoseIndex = idx
        focusPdfPages()
        invalidate()
    }

    // Pose slide animation
    private var lastPoseIndex = -1
    private var slideDir = 0
    private var slideStart = 0L
    private var outgoingPose: Pose? = null
    private var outgoingFlipped = false
    private var shownFlipped = false
    private val slideInterpolator = android.view.animation.DecelerateInterpolator(1.6f)

    override fun onModeChanged() {
        drag = Drag.NONE
        focusPdfPages()
        invalidate()
    }

    override fun onFitRequested() = fitAll()

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        super.onSizeChanged(w, h, oldw, oldh)
        val cw = w - paddingLeft - paddingRight
        val ch = h - paddingTop - paddingBottom
        if (cw > 0 && ch > 0) DataManager.screenAspect = cw.toFloat() / ch
        if (needsFit || oldw == 0 || oldh == 0) {
            fitAll()
        } else {
            // Keep what was in the middle in the middle (rotating, resizing the floating window).
            boardOffX += (w - oldw) / 2f
            boardOffY += (h - oldh) / 2f
        }
    }

    // ---------------------------------------------------------------- Public actions

    fun select(item: RefBoardItem?) {
        if (selectedItem === item) return
        selectedItem = item
        onSelectionChanged?.invoke()
        invalidate()
    }

    /** The board position under a screen point. */
    fun boardPointAt(x: Float, y: Float) = toBoardX(x) to toBoardY(y)

    /** The board position in the middle of the view. */
    fun boardCenter() = boardPointAt(contentCenterX(), contentCenterY())

    fun fitAll() {
        if (width == 0 || height == 0) {
            needsFit = true
            return
        }
        val items = DataManager.items
        if (items.isEmpty()) {
            needsFit = true
            boardScale = 1f
            boardOffX = contentCenterX()
            boardOffY = contentCenterY()
            invalidate()
            return
        }
        var l = Float.MAX_VALUE
        var t = Float.MAX_VALUE
        var r = -Float.MAX_VALUE
        var b = -Float.MAX_VALUE
        for (it in items) {
            it.boundsInto(itemRect)
            l = min(l, itemRect.left)
            t = min(t, itemRect.top)
            r = max(r, itemRect.right)
            b = max(b, itemRect.bottom)
        }
        fitRect(l, t, r, b, 1.5f)
        needsFit = false
    }

    fun fitItem(item: RefBoardItem) {
        item.boundsInto(itemRect)
        fitRect(itemRect.left, itemRect.top, itemRect.right, itemRect.bottom, MAX_ZOOM)
    }

    private fun fitRect(l: Float, t: Float, r: Float, b: Float, maxScale: Float) {
        val margin = 20f * density
        val availW = (width - paddingLeft - paddingRight - 2 * margin).coerceAtLeast(1f)
        val availH = (height - paddingTop - paddingBottom - 2 * margin).coerceAtLeast(1f)
        val w = (r - l).coerceAtLeast(1f)
        val h = (b - t).coerceAtLeast(1f)
        boardScale = min(availW / w, availH / h).coerceIn(MIN_ZOOM, maxScale)
        boardOffX = paddingLeft + margin + (availW - w * boardScale) / 2f - l * boardScale
        boardOffY = paddingTop + margin + (availH - h * boardScale) / 2f - t * boardScale
        invalidate()
    }

    fun resetPoseZoom() {
        poseZoom = 1f
        poseOffX = 0f
        poseOffY = 0f
        invalidate()
    }

    // ---------------------------------------------------------------- Drawing

    override fun onDraw(canvas: Canvas) {
        if (mode == DataManager.MODE_PRACTICE) {
            canvas.drawColor(bgColor)
            drawPractice(canvas)
        } else {
            drawBoard(canvas) // the grid pass paints the background too
        }
    }

    private fun drawBoard(canvas: Canvas) {
        // Dot grid that keeps a comfortable spacing at any zoom level.
        var spacing = gridTile * boardScale
        while (spacing < 22f * density) spacing *= 2f
        while (spacing > 48f * density) spacing /= 2f
        val s = spacing / gridTile
        gridMatrix.setScale(s, s)
        gridMatrix.postTranslate(boardOffX % spacing, boardOffY % spacing)
        gridShader.setLocalMatrix(gridMatrix)
        canvas.drawPaint(gridPaint)

        val items = DataManager.items
        if (items.isEmpty()) return

        canvas.save()
        canvas.translate(boardOffX, boardOffY)
        canvas.scale(boardScale, boardScale)
        visibleRect.set(toBoardX(0f), toBoardY(0f), toBoardX(width.toFloat()), toBoardY(height.toFloat()))
        val shadow = 3f * density / boardScale
        for (item in items) {
            item.boundsInto(itemRect)
            if (!RectF.intersects(itemRect, visibleRect)) continue // off screen: skip
            if (!item.image.bitmap.hasAlpha()) {
                canvas.drawRect(itemRect.left + shadow, itemRect.top + shadow, itemRect.right + shadow, itemRect.bottom + shadow, shadowPaint)
            }
            item.draw(canvas, drawRect, boardScale)
        }
        selectedItem?.let { sel ->
            sel.boundsInto(itemRect)
            selectPaint.strokeWidth = 2.5f * density / boardScale
            canvas.drawRect(itemRect, selectPaint)
            val r = HANDLE_RADIUS_DP * density / boardScale
            handleRing.strokeWidth = 2.5f * density / boardScale
            canvas.drawCircle(itemRect.right, itemRect.bottom, r, handleFill)
            canvas.drawCircle(itemRect.right, itemRect.bottom, r, handleRing)
        }
        canvas.restore()
    }

    private fun poseBitmap(pose: Pose): Bitmap? = when (pose) {
        is Pose.Image -> pose.image.bitmap
        is Pose.PdfPage -> PdfPages.get(pose.docId, pose.page)
    }

    private fun drawPractice(canvas: Canvas) {
        val pose = DataManager.currentPose() ?: return // the host shows its own empty message
        shownPose = pose
        shownFlipped = DataManager.practiceFlipped

        // Slide transition between poses (about a quarter of a second).
        var shift = 0f
        if (slideDir != 0) {
            val t = (SystemClock.uptimeMillis() - slideStart) / SLIDE_MS
            if (t >= 1f) {
                slideDir = 0
                outgoingPose = null
            } else {
                val p = slideInterpolator.getInterpolation(t)
                val w = width.toFloat()
                outgoingPose?.let { out -> poseBitmap(out)?.let { drawPose(canvas, it, -slideDir * p * w, outgoingFlipped, 1f) } }
                shift = slideDir * (1f - p) * w
                postInvalidateOnAnimation()
            }
        }

        val bmp = poseBitmap(pose)
        if (bmp == null) {
            val failed = pose is Pose.PdfPage && PdfPages.hasFailed(pose.docId, pose.page)
            val page = (pose as? Pose.PdfPage)?.page?.plus(1) ?: 0
            canvas.drawText(if (failed) "Could not show page $page" else "Loading page $page…", contentCenterX() + shift, contentCenterY(), hintPaint)
            if (!failed) focusPdfPages()
            return
        }
        drawPose(canvas, bmp, shift, DataManager.practiceFlipped, poseZoom)
    }

    private fun drawPose(canvas: Canvas, bmp: Bitmap, shiftX: Float, flipped: Boolean, zoom: Float) {
        if (!canvas.canDraw(bmp)) return
        val availW = (width - paddingLeft - paddingRight).toFloat()
        val availH = (height - paddingTop - paddingBottom).toFloat()
        val fit = min(availW / bmp.width, availH / bmp.height) * 0.96f * zoom
        val w = bmp.width * fit
        val h = bmp.height * fit
        val cx = contentCenterX() + (if (zoom == poseZoom) poseOffX else 0f) + shiftX
        val cy = contentCenterY() + (if (zoom == poseZoom) poseOffY else 0f)
        drawRect.set(cx - w / 2f, cy - h / 2f, cx + w / 2f, cy + h / 2f)
        canvas.save()
        if (flipped) canvas.scale(-1f, 1f, cx, cy)
        canvas.drawBitmap(bmp, null, drawRect, if (DataManager.practiceGrayscale) Paints.gray else Paints.normal)
        canvas.restore()
    }

    /** Ask the PDF renderer for the current page and its neighbours. */
    private fun focusPdfPages() {
        if (mode != DataManager.MODE_PRACTICE || !isAttachedToWindow) {
            PdfPages.release(this)
            return
        }
        val list = DataManager.practice
        if (list.isEmpty()) return
        val i = DataManager.practiceIndex
        // Current page first, then the next two (people usually go forward) and the previous one.
        val pages = ArrayList<Pose.PdfPage>(4)
        for (d in intArrayOf(0, 1, 2, -1)) {
            val p = list[((i + d) % list.size + list.size) % list.size]
            if (p is Pose.PdfPage && !pages.contains(p)) pages.add(p)
        }
        PdfPages.focus(this, pages)
    }

    // ---------------------------------------------------------------- Touch

    override fun onTouchEvent(e: MotionEvent): Boolean {
        scaleDetector.onTouchEvent(e)
        gestures.onTouchEvent(e)

        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                onTouchStarted?.invoke()
                parent?.requestDisallowInterceptTouchEvent(true)
                downX = e.x; downY = e.y; lastX = e.x; lastY = e.y
                if (mode == DataManager.MODE_BOARD) beginBoardTouch(e.x, e.y) else drag = Drag.PAN
            }
            MotionEvent.ACTION_POINTER_DOWN -> {
                if (drag == Drag.ITEM || drag == Drag.RESIZE) commitBoard()
                drag = Drag.PINCH
            }
            MotionEvent.ACTION_POINTER_UP -> {
                if (e.pointerCount == 2) {
                    // Keep panning with the finger that is still down.
                    val keep = if (e.actionIndex == 0) 1 else 0
                    lastX = e.getX(keep)
                    lastY = e.getY(keep)
                    drag = Drag.PAN
                }
            }
            MotionEvent.ACTION_MOVE -> if (e.pointerCount == 1) move(e.x, e.y)
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                commitBoard()
                drag = Drag.NONE
            }
        }
        return true
    }

    private fun beginBoardTouch(x: Float, y: Float) {
        val sel = selectedItem
        if (sel != null && isOnResizeHandle(sel, x, y)) {
            drag = Drag.RESIZE
            resizeStartScale = sel.scale
            resizeCenterX = boardOffX + sel.centerX * boardScale
            resizeCenterY = boardOffY + sel.centerY * boardScale
            resizeStartDist = hypot(x - resizeCenterX, y - resizeCenterY).coerceAtLeast(1f)
            return
        }
        val hit = hitTest(x, y)
        if (hit != null) {
            select(hit)
            DataManager.bringToFront(hit)
            drag = Drag.PENDING_ITEM
            itemStartX = hit.x
            itemStartY = hit.y
        } else {
            select(null)
            drag = Drag.PAN
        }
    }

    private fun move(x: Float, y: Float) {
        when (drag) {
            Drag.PENDING_ITEM -> if (hypot(x - downX, y - downY) > touchSlop) {
                drag = Drag.ITEM
                move(x, y)
                return
            }
            Drag.ITEM -> selectedItem?.let {
                it.x = itemStartX + (x - downX) / boardScale
                it.y = itemStartY + (y - downY) / boardScale
                boardDirty = true
                DataManager.itemsMoved()
            }
            Drag.RESIZE -> selectedItem?.let {
                val d = hypot(x - resizeCenterX, y - resizeCenterY)
                it.setScaleAroundCenter(resizeStartScale * d / resizeStartDist)
                boardDirty = true
                DataManager.itemsMoved()
            }
            Drag.PAN -> {
                if (mode == DataManager.MODE_BOARD) {
                    boardOffX += x - lastX
                    boardOffY += y - lastY
                    invalidate()
                } else if (poseZoom > 1.01f) {
                    poseOffX += x - lastX
                    poseOffY += y - lastY
                    invalidate()
                }
            }
            else -> {}
        }
        lastX = x
        lastY = y
    }

    private fun commitBoard() {
        if (boardDirty) {
            boardDirty = false
            DataManager.boardChanged()
        }
    }

    private fun hitTest(x: Float, y: Float): RefBoardItem? {
        val bx = toBoardX(x)
        val by = toBoardY(y)
        val items = DataManager.items
        for (i in items.indices.reversed()) if (items[i].hitTest(bx, by)) return items[i]
        return null
    }

    private fun isOnResizeHandle(item: RefBoardItem, x: Float, y: Float): Boolean {
        item.boundsInto(itemRect)
        val hx = boardOffX + itemRect.right * boardScale
        val hy = boardOffY + itemRect.bottom * boardScale
        return hypot(x - hx, y - hy) <= HANDLE_TOUCH_DP * density
    }

    private fun toBoardX(sx: Float) = (sx - boardOffX) / boardScale
    private fun toBoardY(sy: Float) = (sy - boardOffY) / boardScale
    private fun contentCenterX() = paddingLeft + (width - paddingLeft - paddingRight) / 2f
    private fun contentCenterY() = paddingTop + (height - paddingTop - paddingBottom) / 2f

    companion object {
        private const val SLIDE_MS = 240f
        private const val MIN_ZOOM = 0.03f
        private const val MAX_ZOOM = 12f
        private const val HANDLE_RADIUS_DP = 8f
        private const val HANDLE_TOUCH_DP = 28f
    }
}
