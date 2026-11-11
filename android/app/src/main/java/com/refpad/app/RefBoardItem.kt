package com.refpad.app

import android.graphics.Canvas
import android.graphics.RectF
import kotlin.math.abs
import kotlin.math.max

/**
 * An image placed on the board. (x, y) is the top-left corner of the unrotated image in board units;
 * rotation and flipping happen around the image center.
 */
class RefBoardItem(
    val image: RefImage,
    var x: Float = 0f,
    var y: Float = 0f,
    var scale: Float = defaultScaleFor(image),
    var rotation: Int = 0,
    var flipped: Boolean = false,
    var grayscale: Boolean = false
) {
    companion object {
        /** Every new image starts with its long side at this many board units, whatever its pixel size. */
        const val DEFAULT_LONG_SIDE = 700f
        const val MIN_SCALE = 0.02f
        const val MAX_SCALE = 10f

        fun defaultScaleFor(image: RefImage): Float =
            (DEFAULT_LONG_SIDE / max(image.width, image.height).coerceAtLeast(1)).coerceIn(MIN_SCALE, MAX_SCALE)
    }

    val width: Float get() = image.width * scale
    val height: Float get() = image.height * scale
    private val isRotated90: Boolean get() = rotation % 180 != 0
    val effectiveWidth: Float get() = if (isRotated90) height else width
    val effectiveHeight: Float get() = if (isRotated90) width else height
    val centerX: Float get() = x + width / 2f
    val centerY: Float get() = y + height / 2f

    /** Writes the on-board bounds (after rotation) into [out] without allocating. */
    fun boundsInto(out: RectF) {
        val hw = effectiveWidth / 2f
        val hh = effectiveHeight / 2f
        val cx = centerX
        val cy = centerY
        out.set(cx - hw, cy - hh, cx + hw, cy + hh)
    }

    fun hitTest(px: Float, py: Float): Boolean =
        abs(px - centerX) <= effectiveWidth / 2f && abs(py - centerY) <= effectiveHeight / 2f

    /** Moves the item so its rotated bounds start at (left, top). */
    fun moveBoundsTo(left: Float, top: Float) {
        val cx = left + effectiveWidth / 2f
        val cy = top + effectiveHeight / 2f
        x = cx - width / 2f
        y = cy - height / 2f
    }

    /** Resizes the item in place (the center stays put). */
    fun setScaleAroundCenter(newScale: Float) {
        val cx = centerX
        val cy = centerY
        scale = newScale.coerceIn(MIN_SCALE, MAX_SCALE)
        x = cx - width / 2f
        y = cy - height / 2f
    }

    fun rotateCW() { rotation = (rotation + 90) % 360 }
    fun rotateCCW() { rotation = (rotation + 270) % 360 }

    fun resetTransforms() {
        flipped = false
        grayscale = false
        rotation = 0
        setScaleAroundCenter(defaultScaleFor(image))
    }

    fun draw(canvas: Canvas, scratch: RectF, boardScale: Float) {
        val cx = centerX
        val cy = centerY
        val needsTransform = rotation != 0 || flipped
        if (needsTransform) {
            canvas.save()
            if (rotation != 0) canvas.rotate(rotation.toFloat(), cx, cy)
            if (flipped) canvas.scale(-1f, 1f, cx, cy)
        }
        scratch.set(x, y, x + width, y + height)
        val bmp = image.bitmapFor(max(width, height) * boardScale)
        if (canvas.canDraw(bmp)) canvas.drawBitmap(bmp, null, scratch, if (grayscale) Paints.gray else Paints.normal)
        if (needsTransform) canvas.restore()
    }
}
