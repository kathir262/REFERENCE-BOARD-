package com.refpad.app

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.ColorMatrix
import android.graphics.ColorMatrixColorFilter
import android.graphics.Paint
import android.graphics.RectF

class RefBoardItem(
    val bitmap: Bitmap,
    var x: Float = 100f,
    var y: Float = 100f,
    var scale: Float = 1.0f,
    var isFlipped: Boolean = false,
    var isGrayscale: Boolean = false,
    var rotationDegrees: Float = 0f,
    var isSelected: Boolean = false
) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)
    private val borderPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#facc15") // Studio Yellow
        style = Paint.Style.STROKE
        strokeWidth = 6f
    }
    private val handlePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#facc15")
        style = Paint.Style.FILL
    }
    private val badgeBgPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#facc15")
        style = Paint.Style.FILL
    }
    private val badgeTextPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#09090b")
        textSize = 22f
        isFakeBoldText = true
    }

    private val grayscaleFilter by lazy {
        val matrix = ColorMatrix().apply { setSaturation(0f) }
        ColorMatrixColorFilter(matrix)
    }

    val width: Float
        get() = bitmap.width * scale

    val height: Float
        get() = bitmap.height * scale

    val isRotated90: Boolean
        get() = (Math.abs(rotationDegrees.toInt()) % 180) != 0

    val effectiveWidth: Float
        get() = if (isRotated90) height else width

    val effectiveHeight: Float
        get() = if (isRotated90) width else height

    val bounds: RectF
        get() {
            val centerX = x + width / 2f
            val centerY = y + height / 2f
            val ew = effectiveWidth
            val eh = effectiveHeight
            return RectF(centerX - ew / 2f, centerY - eh / 2f, centerX + ew / 2f, centerY + eh / 2f)
        }

    fun hitTest(touchX: Float, touchY: Float): Boolean {
        return bounds.contains(touchX, touchY)
    }

    fun rotateCW() {
        rotationDegrees = (rotationDegrees + 90f) % 360f
    }

    fun rotateCCW() {
        rotationDegrees = (rotationDegrees - 90f) % 360f
    }

    fun resetTransforms() {
        isFlipped = false
        isGrayscale = false
        rotationDegrees = 0f
        scale = 0.5f
    }

    fun draw(canvas: Canvas) {
        val centerX = x + width / 2f
        val centerY = y + height / 2f

        canvas.save()

        // Grayscale filter
        paint.colorFilter = if (isGrayscale) grayscaleFilter else null

        // Rotation & Flip around item center
        if (rotationDegrees != 0f) {
            canvas.rotate(rotationDegrees, centerX, centerY)
        }
        if (isFlipped) {
            canvas.scale(-1f, 1f, centerX, centerY)
        }

        // Draw scaled bitmap
        val destRect = RectF(x, y, x + width, y + height)
        canvas.drawBitmap(bitmap, null, destRect, paint)

        canvas.restore()

        // Draw Studio Yellow border & handles when selected
        if (isSelected) {
            val r = bounds
            canvas.drawRect(r, borderPaint)

            // Draw 4 corner handles
            val handleSize = 12f
            canvas.drawRect(r.left - handleSize / 2, r.top - handleSize / 2, r.left + handleSize / 2, r.top + handleSize / 2, handlePaint)
            canvas.drawRect(r.right - handleSize / 2, r.top - handleSize / 2, r.right + handleSize / 2, r.top + handleSize / 2, handlePaint)
            canvas.drawRect(r.left - handleSize / 2, r.bottom - handleSize / 2, r.left + handleSize / 2, r.bottom + handleSize / 2, handlePaint)
            canvas.drawRect(r.right - handleSize / 2, r.bottom - handleSize / 2, r.right + handleSize / 2, r.bottom + handleSize / 2, handlePaint)

            // Draw yellow SELECTED badge at top-left
            val badgeWidth = 110f
            val badgeHeight = 28f
            canvas.drawRoundRect(r.left, r.top - badgeHeight - 4, r.left + badgeWidth, r.top - 4, 6f, 6f, badgeBgPaint)
            canvas.drawText("SELECTED", r.left + 8f, r.top - 10f, badgeTextPaint)
        }
    }
}
