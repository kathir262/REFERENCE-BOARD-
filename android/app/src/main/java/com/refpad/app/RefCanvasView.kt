package com.refpad.app

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.ColorMatrix
import android.graphics.ColorMatrixColorFilter
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.GestureDetector
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.View

class RefCanvasView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {

    companion object {
        const val MODE_REFERENCE = 0
        const val MODE_PRACTICE = 1
    }

    var currentMode = MODE_REFERENCE
        set(value) {
            field = value
            invalidate()
        }

    // Reference Board Items
    val items = mutableListOf<RefBoardItem>()
    var selectedItem: RefBoardItem? = null
        private set

    // Practice Mode State
    val practiceItems = mutableListOf<Bitmap>()
    var practiceCurrentIndex = 0
        private set
    var practiceFlipped = false
    var practiceGrayscale = false

    var onPoseChanged: ((index: Int, total: Int) -> Unit)? = null
    var onItemsCountChanged: ((count: Int) -> Unit)? = null
    var onItemLongPressed: ((item: RefBoardItem, touchX: Float, touchY: Float, canvasX: Float, canvasY: Float) -> Unit)? = null
    var onCanvasLongPressed: ((touchX: Float, touchY: Float, canvasX: Float, canvasY: Float) -> Unit)? = null
    var onCanvasTapped: (() -> Unit)? = null

    // Canvas Transforms
    private var canvasScale = 1.0f
    private var canvasOffsetX = 0f
    private var canvasOffsetY = 0f

    // Touch Interaction State
    private var isDraggingItem = false
    private var dragTouchStartX = 0f
    private var dragTouchStartY = 0f
    private var itemStartX = 0f
    private var itemStartY = 0f

    private var lastPanX = 0f
    private var lastPanY = 0f
    private var isPanning = false

    private val bgPaint = Paint().apply {
        color = Color.parseColor("#121214")
    }

    private val practicePaint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)
    private val grayscaleFilter by lazy {
        val matrix = ColorMatrix().apply { setSaturation(0f) }
        ColorMatrixColorFilter(matrix)
    }

    private val scaleDetector = ScaleGestureDetector(context, object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
        override fun onScale(detector: ScaleGestureDetector): Boolean {
            val scaleFactor = detector.scaleFactor
            val prevScale = canvasScale
            canvasScale = (canvasScale * scaleFactor).coerceIn(0.1f, 8.0f)

            val focusX = detector.focusX
            val focusY = detector.focusY
            canvasOffsetX = focusX - (focusX - canvasOffsetX) * (canvasScale / prevScale)
            canvasOffsetY = focusY - (focusY - canvasOffsetY) * (canvasScale / prevScale)

            invalidate()
            return true
        }
    })

    private val gestureDetector = GestureDetector(context, object : GestureDetector.SimpleOnGestureListener() {
        override fun onLongPress(e: MotionEvent) {
            val touchX = e.x
            val touchY = e.y
            val canvasX = (touchX - canvasOffsetX) / canvasScale
            val canvasY = (touchY - canvasOffsetY) / canvasScale

            if (currentMode == MODE_REFERENCE) {
                val hit = items.findLast { it.hitTest(canvasX, canvasY) }
                if (hit != null) {
                    items.forEach { it.isSelected = false }
                    hit.isSelected = true
                    selectedItem = hit
                    isDraggingItem = false
                    isPanning = false
                    invalidate()
                    onItemLongPressed?.invoke(hit, touchX, touchY, canvasX, canvasY)
                } else {
                    isDraggingItem = false
                    isPanning = false
                    onCanvasLongPressed?.invoke(touchX, touchY, canvasX, canvasY)
                }
            } else {
                isDraggingItem = false
                isPanning = false
                onCanvasLongPressed?.invoke(touchX, touchY, canvasX, canvasY)
            }
        }
    })

    fun addReferenceItem(bitmap: Bitmap, atX: Float? = null, atY: Float? = null) {
        val itemScale = 0.5f
        val itemW = bitmap.width * itemScale
        val itemH = bitmap.height * itemScale

        val posX: Float
        val posY: Float

        if (atX != null && atY != null) {
            posX = atX - itemW / 2f
            posY = atY - itemH / 2f
        } else if (items.isEmpty()) {
            posX = 60f
            posY = 100f
        } else {
            val last = items.last()
            val candidateX = last.x + last.effectiveWidth + 40f
            val maxRowWidth = 2200f

            if (candidateX + itemW <= maxRowWidth) {
                posX = candidateX
                posY = last.y
            } else {
                var lowestY = 0f
                for (it in items) {
                    val bottom = it.y + it.effectiveHeight
                    if (bottom > lowestY) lowestY = bottom
                }
                posX = 60f
                posY = lowestY + 40f
            }
        }

        val item = RefBoardItem(
            bitmap = bitmap,
            x = posX,
            y = posY,
            scale = itemScale
        )
        items.forEach { it.isSelected = false }
        item.isSelected = true
        selectedItem = item
        items.add(item)
        onItemsCountChanged?.invoke(items.size)
        invalidate()
    }

    fun flipSelected() {
        if (currentMode == MODE_REFERENCE) {
            selectedItem?.let {
                it.isFlipped = !it.isFlipped
                invalidate()
            }
        } else {
            flipPracticePose()
        }
    }

    fun rotateSelectedCW() {
        selectedItem?.let {
            it.rotateCW()
            invalidate()
        }
    }

    fun rotateSelectedCCW() {
        selectedItem?.let {
            it.rotateCCW()
            invalidate()
        }
    }

    fun resetSelectedTransforms() {
        selectedItem?.let {
            it.resetTransforms()
            invalidate()
        }
    }

    fun toggleGrayscaleSelected() {
        if (currentMode == MODE_REFERENCE) {
            selectedItem?.let {
                it.isGrayscale = !it.isGrayscale
                invalidate()
            }
        } else {
            toggleGrayscalePracticePose()
        }
    }

    fun deleteSelected() {
        selectedItem?.let {
            items.remove(it)
            selectedItem = items.lastOrNull()?.also { last -> last.isSelected = true }
            onItemsCountChanged?.invoke(items.size)
            invalidate()
        }
    }

    fun copySelected(): Boolean {
        val bmp = selectedItem?.bitmap ?: return false
        DataManager.copiedBitmap = bmp
        return true
    }

    fun pasteCopied(atX: Float? = null, atY: Float? = null): Boolean {
        val bmp = DataManager.copiedBitmap ?: return false
        addReferenceItem(bmp, atX, atY)
        return true
    }

    fun clearAll() {
        items.clear()
        selectedItem = null
        onItemsCountChanged?.invoke(0)
        invalidate()
    }

    fun autoArrange() {
        if (items.isEmpty()) return
        var curX = 60f
        val startY = 120f
        val padding = 50f
        for (item in items) {
            item.x = curX
            item.y = startY
            curX += item.effectiveWidth + padding
        }
        resetCanvasTransform()
        invalidate()
    }

    fun resetCanvasTransform() {
        canvasScale = 1.0f
        canvasOffsetX = 0f
        canvasOffsetY = 0f
        invalidate()
    }

    // Practice Mode Functions
    fun setPracticeList(list: List<Bitmap>) {
        practiceItems.clear()
        practiceItems.addAll(list)
        practiceCurrentIndex = 0
        practiceFlipped = false
        practiceGrayscale = false
        notifyPoseChanged()
        invalidate()
    }

    fun nextPracticePose() {
        if (practiceItems.isNotEmpty()) {
            practiceCurrentIndex = (practiceCurrentIndex + 1) % practiceItems.size
            practiceFlipped = false
            notifyPoseChanged()
            invalidate()
        }
    }

    fun prevPracticePose() {
        if (practiceItems.isNotEmpty()) {
            practiceCurrentIndex = if (practiceCurrentIndex > 0) practiceCurrentIndex - 1 else practiceItems.size - 1
            practiceFlipped = false
            notifyPoseChanged()
            invalidate()
        }
    }

    fun flipPracticePose() {
        practiceFlipped = !practiceFlipped
        invalidate()
    }

    fun toggleGrayscalePracticePose() {
        practiceGrayscale = !practiceGrayscale
        invalidate()
    }

    private fun notifyPoseChanged() {
        if (practiceItems.isNotEmpty()) {
            onPoseChanged?.invoke(practiceCurrentIndex + 1, practiceItems.size)
        } else {
            onPoseChanged?.invoke(0, 0)
        }
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        scaleDetector.onTouchEvent(event)
        gestureDetector.onTouchEvent(event)

        if (event.pointerCount > 1) {
            isDraggingItem = false
            isPanning = false
            return true
        }

        val touchX = event.x
        val touchY = event.y

        val canvasX = (touchX - canvasOffsetX) / canvasScale
        val canvasY = (touchY - canvasOffsetY) / canvasScale

        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                onCanvasTapped?.invoke()
                if (currentMode == MODE_REFERENCE) {
                    val hit = items.findLast { it.hitTest(canvasX, canvasY) }
                    if (hit != null) {
                        items.forEach { it.isSelected = false }
                        hit.isSelected = true
                        selectedItem = hit
                        isDraggingItem = true
                        dragTouchStartX = canvasX
                        dragTouchStartY = canvasY
                        itemStartX = hit.x
                        itemStartY = hit.y
                    } else {
                        isDraggingItem = false
                        isPanning = true
                        lastPanX = touchX
                        lastPanY = touchY
                        items.forEach { it.isSelected = false }
                        selectedItem = null
                    }
                } else {
                    isPanning = true
                    lastPanX = touchX
                    lastPanY = touchY
                }
                invalidate()
                return true
            }

            MotionEvent.ACTION_MOVE -> {
                if (isDraggingItem && selectedItem != null) {
                    val deltaX = canvasX - dragTouchStartX
                    val deltaY = canvasY - dragTouchStartY
                    selectedItem?.let {
                        it.x = itemStartX + deltaX
                        it.y = itemStartY + deltaY
                    }
                    invalidate()
                    return true
                } else if (isPanning) {
                    val dx = touchX - lastPanX
                    val dy = touchY - lastPanY
                    canvasOffsetX += dx
                    canvasOffsetY += dy
                    lastPanX = touchX
                    lastPanY = touchY
                    invalidate()
                    return true
                }
            }

            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                isDraggingItem = false
                isPanning = false
            }
        }

        return true
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)

        canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), bgPaint)

        canvas.save()
        canvas.translate(canvasOffsetX, canvasOffsetY)
        canvas.scale(canvasScale, canvasScale)

        if (currentMode == MODE_REFERENCE) {
            for (item in items) {
                item.draw(canvas)
            }
        } else {
            if (practiceItems.isNotEmpty() && practiceCurrentIndex < practiceItems.size) {
                val pose = practiceItems[practiceCurrentIndex]
                val viewW = width / canvasScale
                val viewH = height / canvasScale

                val scaleToFit = Math.min(viewW / pose.width, viewH / pose.height) * 0.9f
                val destW = pose.width * scaleToFit
                val destH = pose.height * scaleToFit
                val left = (viewW - destW) / 2f
                val top = (viewH - destH) / 2f

                practicePaint.colorFilter = if (practiceGrayscale) grayscaleFilter else null

                canvas.save()
                if (practiceFlipped) {
                    canvas.scale(-1f, 1f, left + destW / 2f, top + destH / 2f)
                }
                canvas.drawBitmap(pose, null, RectF(left, top, left + destW, top + destH), practicePaint)
                canvas.restore()
            }
        }

        canvas.restore()
    }
}
