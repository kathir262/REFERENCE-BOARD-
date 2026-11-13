package com.refpad.app

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapShader
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.PointF
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
import kotlin.math.roundToInt

/**
 * The infinite reference board and the practice viewer.
 * It draws straight from [DataManager], so several of these (full screen + floating window) stay in sync.
 *
 * Board:    drag image = move · corner handle or pinch on selected image = resize · drag empty space = pan
 *           pinch elsewhere = zoom · double-tap = fit · long-press = menu
 *           crop mode: drag the edges or corners, drag inside to move the crop, tap outside to finish
 *           colour picker: touch and drag over a picture, lift to copy the colour
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
    /** A note was double-tapped (edit it). */
    var onNoteDoubleTapped: ((RefBoardItem) -> Unit)? = null
    /** Crop mode or the colour picker started or ended. */
    var onToolChanged: (() -> Unit)? = null
    /** The colour picker picked a colour (lifted the finger over the board). */
    var onColorPicked: ((Int) -> Unit)? = null
    /** Memory mode: true while the finger is held down to peek at the hidden pose. */
    var peeking = false
        private set

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
    private val pt = PointF()

    private val accent = Color.parseColor("#FACC15")
    private val selectPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = accent; style = Paint.Style.STROKE }
    private val handleFill = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = accent; style = Paint.Style.FILL }
    private val handleRing = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#0E0E10"); style = Paint.Style.STROKE }
    private val hintPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#71717A")
        textSize = 15f * density
        textAlign = Paint.Align.CENTER
    }
    private val shadowPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#66000000") }
    private val dimPaint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG).apply { alpha = 80 }
    private val cropPaint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)
    private val loupeFill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val loupeRing = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE }
    private val loupeText = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE
        textSize = 13f * density
        textAlign = Paint.Align.CENTER
        typeface = android.graphics.Typeface.create("sans-serif-medium", android.graphics.Typeface.NORMAL)
    }
    private val pillPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#E6141417") }
    private val coverPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#A1A1AA")
        textSize = 17f * density
        textAlign = Paint.Align.CENTER
    }
    private val lockIcon = context.getDrawable(R.drawable.ic_lock)?.mutate()?.apply { setTint(Color.parseColor("#0A0A0B")) }

    // Dot grid drawn with one tiled shader (a single draw call, however large the board).
    private val gridTile = 64
    private var bgColor = 0
    private var shownBackground = -1
    private lateinit var gridShader: BitmapShader
    private val gridPaint = Paint()
    private val gridMatrix = Matrix()

    /** Background and dot colours for dark, neutral grey and light (the same as RefPad for Windows). */
    private fun updateBackground() {
        val bg = DataManager.background
        if (bg == shownBackground) return
        shownBackground = bg
        val (back, dot) = when (bg) {
            DataManager.BG_GREY -> "#76767A" to "#6A6A6E"
            DataManager.BG_LIGHT -> "#E8E8EB" to "#D2D2D8"
            else -> "#0E0E10" to "#2A2A30"
        }
        bgColor = Color.parseColor(back)
        // The tile is opaque (background + dot), so the grid also paints the background in the same single pass.
        val tile = Bitmap.createBitmap(gridTile, gridTile, Bitmap.Config.ARGB_8888)
        tile.eraseColor(bgColor)
        Canvas(tile).drawCircle(gridTile / 2f, gridTile / 2f, 2.2f, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor(dot) })
        gridShader = BitmapShader(tile, Shader.TileMode.REPEAT, Shader.TileMode.REPEAT)
        gridPaint.shader = gridShader
        hintPaint.color = if (bg == DataManager.BG_LIGHT) Color.parseColor("#52525B") else Color.parseColor("#A1A1AA")
    }

    init {
        updateBackground()
    }

    // ---------------------------------------------------------------- Touch state

    private enum class Drag { NONE, PENDING_ITEM, ITEM, RESIZE, PAN, PINCH, CROP, PICK }

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
            pickShown = false
            lastFocusX = d.focusX
            lastFocusY = d.focusY
            pinchItem = null
            if (mode == DataManager.MODE_BOARD && cropItem == null && !picking) {
                selectedItem?.let { sel ->
                    sel.boundsInto(itemRect)
                    if (!sel.locked && itemRect.contains(toBoardX(d.focusX), toBoardY(d.focusY))) pinchItem = sel
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
            if (drag == Drag.PINCH || drag == Drag.ITEM || drag == Drag.RESIZE || drag == Drag.CROP || drag == Drag.PICK ||
                scaleDetector.isInProgress || cropItem != null || picking
            ) return
            if (mode == DataManager.MODE_PRACTICE && PracticeTimer.covered) return // holding = peeking
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
                if (picking) return true
                if (cropItem != null) {
                    finishCrop()
                    return true
                }
                val hit = hitTest(e.x, e.y)
                when {
                    hit != null && hit.isNote -> onNoteDoubleTapped?.invoke(hit)
                    hit != null -> fitItem(hit)
                    else -> fitAll()
                }
            } else {
                resetPoseZoom()
            }
            return true
        }

        override fun onFling(e1: MotionEvent?, e2: MotionEvent, vx: Float, vy: Float): Boolean {
            if (mode != DataManager.MODE_PRACTICE || poseZoom > 1.01f) return false
            if (abs(vx) < 600 * density || abs(vx) < abs(vy) * 1.3f) return false
            if (vx < 0) PracticeTimer.next() else PracticeTimer.previous()
            return true
        }
    })

    // ---------------------------------------------------------------- Lifecycle

    private val pageReady: () -> Unit = { if (mode == DataManager.MODE_PRACTICE) invalidate() }
    private val lookReady: () -> Unit = { if (mode == DataManager.MODE_BOARD) invalidate() }

    override fun onAttachedToWindow() {
        super.onAttachedToWindow()
        DataManager.addListener(this)
        PdfPages.addListener(pageReady)
        Looks.addListener(lookReady)
        focusPdfPages()
    }

    override fun onDetachedFromWindow() {
        DataManager.removeListener(this)
        PdfPages.removeListener(pageReady)
        Looks.removeListener(lookReady)
        PdfPages.release(this)
        dropSample()
        super.onDetachedFromWindow()
    }

    override fun onBoardChanged() {
        val items = DataManager.items
        // Undo and redo put back copies of the items: keep the same one selected (and cropping).
        val sel = selectedItem
        if (sel != null && !items.containsRef(sel)) select(items.firstOrNull { it.id == sel.id })
        val c = cropItem
        if (c != null && !items.containsRef(c)) {
            cropItem = items.firstOrNull { it.id == c.id }
            if (cropItem == null) onToolChanged?.invoke()
        }
        if (needsFit && items.isNotEmpty()) fitAll()
        updateBackground()
        invalidate()
    }

    private fun List<RefBoardItem>.containsRef(item: RefBoardItem): Boolean {
        for (i in indices.reversed()) if (this[i] === item) return true
        return false
    }

    override fun onPracticeChanged() {
        updateBackground()
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
        if (mode != DataManager.MODE_BOARD) {
            finishCrop()
            setPicking(false)
        }
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
        if (width == 0 || height == 0) {
            pendingFitItem = item.id
            return
        }
        item.boundsInto(itemRect)
        fitRect(itemRect.left, itemRect.top, itemRect.right, itemRect.bottom, MAX_ZOOM)
        needsFit = false
    }

    /** Zoom to the item with this id as soon as the view has a size (the floating window opening on one picture). */
    private var pendingFitItem = 0L

    fun fitItemWhenReady(id: Long) {
        val item = DataManager.items.firstOrNull { it.id == id } ?: return
        if (width == 0 || height == 0) pendingFitItem = id else fitItem(item)
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

    // ---------------------------------------------------------------- Crop mode

    /** The picture being cropped, or null. */
    var cropItem: RefBoardItem? = null
        private set
    private var cropDirty = false
    private var cropEdges = 0 // 1 left, 2 top, 4 right, 8 bottom; 15 = move the whole crop
    private val cropStart = RectF()
    private val downImg = PointF()
    private var cropTapOutside = false

    fun startCrop(item: RefBoardItem) {
        if (item.isNote || item.image == null) return
        setPicking(false)
        finishCrop()
        cropItem = item
        cropDirty = false
        select(item)
        onToolChanged?.invoke()
        invalidate()
    }

    /** Ends crop mode; the new crop becomes one undo step. */
    fun finishCrop() {
        if (cropItem == null) return
        cropItem = null
        if (drag == Drag.CROP) drag = Drag.NONE
        if (cropDirty) {
            cropDirty = false
            DataManager.boardChanged()
        }
        onToolChanged?.invoke()
        invalidate()
    }

    private fun beginCropTouch(item: RefBoardItem, x: Float, y: Float) {
        val img = item.image ?: return
        item.boardToImage(toBoardX(x), toBoardY(y), downImg)
        val c = item.crop ?: RectF(0f, 0f, img.width.toFloat(), img.height.toFloat())
        cropStart.set(c)
        val tol = HANDLE_TOUCH_DP * density / (boardScale * item.scale)
        val px = downImg.x
        val py = downImg.y
        var e = 0
        if (px >= c.left - tol && px <= c.right + tol && py >= c.top - tol && py <= c.bottom + tol) {
            val dl = abs(px - c.left)
            val dr = abs(px - c.right)
            if (min(dl, dr) <= tol) e = e or (if (dl <= dr) 1 else 4)
            val dt = abs(py - c.top)
            val db = abs(py - c.bottom)
            if (min(dt, db) <= tol) e = e or (if (dt <= db) 2 else 8)
            if (e == 0) e = 15
        }
        cropEdges = e
        cropTapOutside = e == 0
        drag = if (e != 0) Drag.CROP else Drag.PAN
    }

    private fun moveCrop(item: RefBoardItem, x: Float, y: Float) {
        val img = item.image ?: return
        // The picture never moves while cropping, so a point keeps its picture pixel.
        item.boardToImage(toBoardX(x), toBoardY(y), pt)
        val dx = pt.x - downImg.x
        val dy = pt.y - downImg.y
        val w = img.width.toFloat()
        val h = img.height.toFloat()
        val minSide = max(8f, 24f * density / (boardScale * item.scale))
        val r = RectF(cropStart)
        if (cropEdges == 15) {
            r.offset(dx.coerceIn(-r.left, w - r.right), dy.coerceIn(-r.top, h - r.bottom))
        } else {
            if (cropEdges and 1 != 0) r.left = (cropStart.left + dx).coerceIn(0f, max(0f, r.right - minSide))
            if (cropEdges and 4 != 0) r.right = (cropStart.right + dx).coerceIn(min(w, r.left + minSide), w)
            if (cropEdges and 2 != 0) r.top = (cropStart.top + dy).coerceIn(0f, max(0f, r.bottom - minSide))
            if (cropEdges and 8 != 0) r.bottom = (cropStart.bottom + dy).coerceIn(min(h, r.top + minSide), h)
        }
        item.applyCrop(r)
        cropDirty = true
        DataManager.itemsMoved()
    }

    /** The picture being cropped: all of it dimmed, the part that stays bright, and the handles. */
    private fun drawCropping(canvas: Canvas, item: RefBoardItem) {
        val img = item.image ?: return
        val w = img.width.toFloat()
        val h = img.height.toFloat()
        val c = item.crop ?: RectF(0f, 0f, w, h)
        canvas.save()
        canvas.translate(item.centerX, item.centerY)
        if (item.rotation != 0) canvas.rotate(item.rotation.toFloat())
        if (item.flipped) canvas.scale(-1f, 1f)
        canvas.scale(item.scale, item.scale)
        canvas.translate(-c.centerX(), -c.centerY())
        drawRect.set(0f, 0f, w, h)
        val bmp = image(item)
        if (canvas.canDraw(bmp)) {
            val gray = item.grayscale || item.values > 0
            dimPaint.colorFilter = if (gray) ItemPaints.screen.gray.colorFilter else null
            cropPaint.colorFilter = dimPaint.colorFilter
            canvas.drawBitmap(bmp, null, drawRect, dimPaint)
            canvas.save()
            canvas.clipRect(c)
            canvas.drawBitmap(bmp, null, drawRect, cropPaint)
            canvas.restore()
        }
        val k = boardScale * item.scale // screen pixels per picture pixel
        selectPaint.strokeWidth = 2f * density / k
        canvas.drawRect(c, selectPaint)
        val r = 7f * density / k
        handleRing.strokeWidth = 2f * density / k
        for (hx in floatArrayOf(c.left, c.centerX(), c.right)) for (hy in floatArrayOf(c.top, c.centerY(), c.bottom)) {
            if (hx == c.centerX() && hy == c.centerY()) continue
            canvas.drawCircle(hx, hy, r, handleFill)
            canvas.drawCircle(hx, hy, r, handleRing)
        }
        canvas.restore()
    }

    private fun image(item: RefBoardItem): Bitmap {
        val img = item.image!!
        return (if (item.values > 0 || item.blur) Looks.get(img, item.values, item.blur) else null) ?: img.bitmap
    }

    // ---------------------------------------------------------------- Colour picker

    var picking = false
        private set
    private var pickShown = false
    private var pickX = 0f
    private var pickY = 0f
    private var pickColor = 0
    private var sampleKey: String? = null
    private var sampleBmp: Bitmap? = null

    fun setPicking(on: Boolean) {
        if (on == picking) return
        if (on) finishCrop()
        picking = on
        pickShown = false
        if (!on) dropSample()
        onToolChanged?.invoke()
        invalidate()
    }

    private fun dropSample() {
        sampleBmp = null
        sampleKey = null
    }

    /** The colour shown at a screen point (the top picture there, as it looks on the board). */
    private fun sampleAt(x: Float, y: Float): Int {
        val hit = hitTest(x, y) ?: return bgColor
        val img = hit.image ?: return Color.parseColor("#2A2A31")
        hit.boardToImage(toBoardX(x), toBoardY(y), pt)
        val key = "${img.fileName}|${hit.values}|${hit.blur}"
        if (sampleKey != key) {
            val src = Looks.source(img, ImageLoader.MAX_IMAGE_SIDE)
            sampleBmp = if (src != null && (hit.values > 0 || hit.blur)) Looks.make(src, hit.values, hit.blur) else src
            sampleKey = key
        }
        val b = sampleBmp ?: return bgColor
        val k = b.width / img.width.toFloat()
        var c = b.getPixel((pt.x * k).toInt().coerceIn(0, b.width - 1), (pt.y * k).toInt().coerceIn(0, b.height - 1))
        if (hit.grayscale || hit.values > 0) {
            val l = Looks.luma(c)
            c = Color.rgb(l, l, l)
        }
        if (hit.opacity < 1f) {
            val a = hit.opacity
            c = Color.rgb(
                (Color.red(c) * a + Color.red(bgColor) * (1 - a)).roundToInt(),
                (Color.green(c) * a + Color.green(bgColor) * (1 - a)).roundToInt(),
                (Color.blue(c) * a + Color.blue(bgColor) * (1 - a)).roundToInt()
            )
        }
        return c or 0xFF000000.toInt()
    }

    private fun pick(x: Float, y: Float) {
        pickX = x
        pickY = y
        pickColor = sampleAt(x, y)
        pickShown = true
        invalidate()
    }

    /** A circle of the colour above the finger, with its hex code. */
    private fun drawLoupe(canvas: Canvas) {
        val r = 34f * density
        var cy = pickY - 84f * density
        if (cy < r + 8f * density) cy = pickY + 84f * density
        val cx = pickX.coerceIn(r + 6f * density, width - r - 6f * density)
        loupeFill.color = pickColor
        canvas.drawCircle(cx, cy, r, loupeFill)
        loupeRing.strokeWidth = 4f * density
        loupeRing.color = Color.WHITE
        canvas.drawCircle(cx, cy, r, loupeRing)
        loupeRing.strokeWidth = 1f * density
        loupeRing.color = Color.parseColor("#80000000")
        canvas.drawCircle(cx, cy, r + 2.5f * density, loupeRing)
        val label = Looks.hex(pickColor)
        val tw = loupeText.measureText(label) / 2f + 10f * density
        val ty = cy + r + 22f * density
        drawRect.set(cx - tw, ty - 17f * density, cx + tw, ty + 7f * density)
        canvas.drawRoundRect(drawRect, 12f * density, 12f * density, pillPaint)
        canvas.drawText(label, cx, ty, loupeText)
        // A small ring right under the finger shows the exact spot.
        loupeRing.strokeWidth = 2f * density
        loupeRing.color = Color.WHITE
        canvas.drawCircle(pickX, pickY, 6f * density, loupeRing)
    }

    // ---------------------------------------------------------------- Drawing

    override fun onDraw(canvas: Canvas) {
        updateBackground()
        if (mode == DataManager.MODE_PRACTICE) {
            canvas.drawColor(bgColor)
            drawPractice(canvas)
        } else {
            drawBoard(canvas) // the grid pass paints the background too
            if (picking && pickShown) drawLoupe(canvas)
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
        val cropping = cropItem
        for (item in items) {
            if (item === cropping) continue
            item.boundsInto(itemRect)
            if (!RectF.intersects(itemRect, visibleRect)) continue // off screen: skip
            val img = item.image
            if (img != null && !img.bitmap.hasAlpha() && item.opacity >= 1f) {
                canvas.drawRect(itemRect.left + shadow, itemRect.top + shadow, itemRect.right + shadow, itemRect.bottom + shadow, shadowPaint)
            }
            item.draw(canvas, drawRect, boardScale)
        }
        if (cropping != null) {
            drawCropping(canvas, cropping)
        } else {
            selectedItem?.let { sel ->
                sel.boundsInto(itemRect)
                selectPaint.strokeWidth = 2.5f * density / boardScale
                canvas.drawRect(itemRect, selectPaint)
                if (!sel.locked) {
                    val r = HANDLE_RADIUS_DP * density / boardScale
                    handleRing.strokeWidth = 2.5f * density / boardScale
                    canvas.drawCircle(itemRect.right, itemRect.bottom, r, handleFill)
                    canvas.drawCircle(itemRect.right, itemRect.bottom, r, handleRing)
                }
            }
        }
        canvas.restore()
        // A locked picture shows a small lock instead of the resize handle.
        val sel = selectedItem
        if (cropping == null && sel != null && sel.locked) {
            sel.boundsInto(itemRect)
            val cx = boardOffX + itemRect.right * boardScale
            val cy = boardOffY + itemRect.top * boardScale
            val r = 13f * density
            canvas.drawCircle(cx, cy, r, handleFill)
            lockIcon?.let {
                val half = (8f * density).roundToInt()
                it.setBounds(cx.roundToInt() - half, cy.roundToInt() - half, cx.roundToInt() + half, cy.roundToInt() + half)
                it.draw(canvas)
            }
        }
    }

    private fun poseBitmap(pose: Pose): Bitmap? = when (pose) {
        is Pose.Image -> pose.image.bitmap
        is Pose.PdfPage -> PdfPages.get(pose.docId, pose.page)
    }

    private fun drawPractice(canvas: Canvas) {
        val pose = DataManager.currentPose() ?: return // the host shows its own empty message
        shownPose = pose
        shownFlipped = DataManager.practiceFlipped

        // Memory mode: the pose is hidden while you draw it from memory (hold a finger down to peek).
        if (PracticeTimer.covered && !peeking) {
            canvas.drawText("Draw it from memory", contentCenterX(), contentCenterY() - 6f * density, coverPaint)
            canvas.drawText("Hold a finger down to peek", contentCenterX(), contentCenterY() + 22f * density, hintPaint)
            return
        }

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

    override fun onLayout(changed: Boolean, left: Int, top: Int, right: Int, bottom: Int) {
        super.onLayout(changed, left, top, right, bottom)
        if (pendingFitItem != 0L && width > 0 && height > 0) {
            val id = pendingFitItem
            pendingFitItem = 0L
            DataManager.items.firstOrNull { it.id == id }?.let { post { fitItem(it) } }
        }
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
                if (mode == DataManager.MODE_BOARD) {
                    beginBoardTouch(e.x, e.y)
                } else {
                    drag = Drag.PAN
                    if (PracticeTimer.covered) {
                        peeking = true
                        invalidate()
                    }
                }
            }
            MotionEvent.ACTION_POINTER_DOWN -> {
                if (drag == Drag.ITEM || drag == Drag.RESIZE) commitBoard()
                drag = Drag.PINCH
                pickShown = false
            }
            MotionEvent.ACTION_POINTER_UP -> {
                if (e.pointerCount == 2) {
                    // Keep panning with the finger that is still down.
                    val keep = if (e.actionIndex == 0) 1 else 0
                    lastX = e.getX(keep)
                    lastY = e.getY(keep)
                    drag = Drag.PAN
                    cropTapOutside = false
                }
            }
            MotionEvent.ACTION_MOVE -> if (e.pointerCount == 1) move(e.x, e.y)
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                val up = e.actionMasked == MotionEvent.ACTION_UP
                if (drag == Drag.PICK) {
                    if (up && pickShown) {
                        val c = pickColor
                        setPicking(false)
                        onColorPicked?.invoke(c)
                    }
                    pickShown = false
                    invalidate()
                }
                if (up && cropItem != null && cropTapOutside && hypot(e.x - downX, e.y - downY) < touchSlop) finishCrop()
                if (peeking) {
                    peeking = false
                    invalidate()
                }
                commitBoard()
                drag = Drag.NONE
            }
        }
        return true
    }

    private fun beginBoardTouch(x: Float, y: Float) {
        if (picking) {
            drag = Drag.PICK
            pick(x, y)
            return
        }
        cropItem?.let {
            beginCropTouch(it, x, y)
            return
        }
        val sel = selectedItem
        if (sel != null && !sel.locked && isOnResizeHandle(sel, x, y)) {
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
            if (hit.locked) {
                // A locked picture stays put: dragging it moves the board instead.
                drag = Drag.PAN
                return
            }
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
            Drag.PICK -> pick(x, y)
            Drag.CROP -> cropItem?.let { moveCrop(it, x, y) }
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

    /** The visible board area in board units (for exporting what is on screen, placing notes). */
    fun visibleBoardRect(out: RectF) {
        out.set(toBoardX(paddingLeft.toFloat()), toBoardY(paddingTop.toFloat()),
            toBoardX((width - paddingRight).toFloat()), toBoardY((height - paddingBottom).toFloat()))
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
