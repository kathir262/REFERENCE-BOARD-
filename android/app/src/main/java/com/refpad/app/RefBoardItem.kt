package com.refpad.app

import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.PointF
import android.graphics.Rect
import android.graphics.RectF
import android.text.Layout
import android.text.StaticLayout
import android.text.TextPaint
import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.max
import kotlin.math.roundToInt

/**
 * A picture (or a text note) placed on the board. (x, y) is the top-left corner of the part that shows
 * (the crop), unrotated, in board units; rotation and flipping happen around its center.
 *
 * [crop] is in the picture's pixels; null shows the whole picture. A note has no picture: it is a card
 * [noteW] x [noteH] board units big at scale 1.
 */
class RefBoardItem(
    val image: RefImage?,
    var x: Float = 0f,
    var y: Float = 0f,
    var scale: Float = image?.let { defaultScaleFor(it) } ?: 1f,
    var rotation: Int = 0,
    var flipped: Boolean = false,
    var grayscale: Boolean = false,
    var crop: RectF? = null,
    var opacity: Float = 1f,
    var locked: Boolean = false,
    /** 0 = no grid, otherwise an N x N grid over the picture. */
    var grid: Int = 0,
    /** 0 = off, otherwise the picture in that many grey steps (a value study). */
    var values: Int = 0,
    /** "Squint": blurred, to judge the big shapes. */
    var blur: Boolean = false,
    var note: String = "",
    var noteW: Float = NOTE_WIDTH,
    var noteH: Float = 100f,
    /** Stays the same in undo copies, so the selection survives undo and redo. */
    val id: Long = nextId++
) {
    companion object {
        /** Every new image starts with its long side at this many board units, whatever its pixel size. */
        const val DEFAULT_LONG_SIDE = 700f
        const val MIN_SCALE = 0.02f
        const val MAX_SCALE = 10f
        const val NOTE_WIDTH = 320f
        const val NOTE_FONT = 22f
        const val NOTE_PAD = 16f
        private var nextId = 1L

        fun defaultScaleFor(image: RefImage): Float =
            (DEFAULT_LONG_SIDE / max(image.width, image.height).coerceAtLeast(1)).coerceIn(MIN_SCALE, MAX_SCALE)

        /** A new note with its middle at (cx, cy). */
        fun newNote(text: String, cx: Float, cy: Float): RefBoardItem {
            val n = RefBoardItem(null, note = text)
            n.sizeNote()
            n.x = cx - n.width / 2f
            n.y = cy - n.height / 2f
            return n
        }

    }

    val isNote: Boolean get() = image == null

    /** Size of the part that shows, before scaling and rotation (picture pixels, or note units). */
    val srcW: Float get() = image?.let { crop?.width() ?: it.width.toFloat() } ?: noteW
    val srcH: Float get() = image?.let { crop?.height() ?: it.height.toFloat() } ?: noteH

    val width: Float get() = srcW * scale
    val height: Float get() = srcH * scale
    private val isRotated90: Boolean get() = rotation % 180 != 0
    val effectiveWidth: Float get() = if (isRotated90) height else width
    val effectiveHeight: Float get() = if (isRotated90) width else height
    val centerX: Float get() = x + width / 2f
    val centerY: Float get() = y + height / 2f

    /** An exact copy for undo (same id, same picture in memory). */
    fun snapshot(): RefBoardItem = RefBoardItem(
        image, x, y, scale, rotation, flipped, grayscale, crop?.let { RectF(it) }, opacity, locked, grid, values, blur,
        note, noteW, noteH, id
    ).also { it.layout = layout; it.layoutKey = layoutKey }

    /** A new item that looks the same (for copy and paste). */
    fun duplicate(): RefBoardItem = RefBoardItem(
        image, x, y, scale, rotation, flipped, grayscale, crop?.let { RectF(it) }, opacity, false, grid, values, blur,
        note, noteW, noteH
    )

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
        values = 0
        blur = false
        opacity = 1f
        grid = 0
        setScaleAroundCenter(image?.let { defaultScaleFor(it) } ?: 1f)
    }

    // ---------------------------------------------------------------- Picture pixels <-> board

    /** Middle of the part that shows, in picture pixels. */
    private fun cropCenterX() = crop?.centerX() ?: (image?.width ?: 0) / 2f
    private fun cropCenterY() = crop?.centerY() ?: (image?.height ?: 0) / 2f

    /**
     * Picture pixel -> board point. Android draws the picture flipped first, then turned:
     * board = center + R(F(scale * (p - cropCenter))).
     */
    fun imageToBoard(px: Float, py: Float, out: PointF) {
        var vx = (px - cropCenterX()) * scale
        val vy = (py - cropCenterY()) * scale
        if (flipped) vx = -vx
        when (rotation) {
            90 -> out.set(centerX - vy, centerY + vx)
            180 -> out.set(centerX - vx, centerY - vy)
            270 -> out.set(centerX + vy, centerY - vx)
            else -> out.set(centerX + vx, centerY + vy)
        }
    }

    /** Board point -> picture pixel (the inverse of [imageToBoard]). */
    fun boardToImage(bx: Float, by: Float, out: PointF) {
        val dx = bx - centerX
        val dy = by - centerY
        var vx: Float
        val vy: Float
        when (rotation) {
            90 -> { vx = dy; vy = -dx }
            180 -> { vx = -dx; vy = -dy }
            270 -> { vx = -dy; vy = dx }
            else -> { vx = dx; vy = dy }
        }
        if (flipped) vx = -vx
        out.set(cropCenterX() + vx / scale, cropCenterY() + vy / scale)
    }

    /** Changes the crop without moving the picture on the board (null shows all of it). */
    fun applyCrop(newCrop: RectF?) {
        val img = image ?: return
        val c = newCrop?.let {
            RectF(it).apply {
                intersect(0f, 0f, img.width.toFloat(), img.height.toFloat())
            }
        }?.takeIf { it.width() >= 1f && it.height() >= 1f }
        val whole = c == null || (c.left <= 0.5f && c.top <= 0.5f && c.right >= img.width - 0.5f && c.bottom >= img.height - 0.5f)
        val nc = if (whole) null else c
        val p = PointF()
        imageToBoard(nc?.centerX() ?: img.width / 2f, nc?.centerY() ?: img.height / 2f, p)
        crop = nc
        x = p.x - width / 2f
        y = p.y - height / 2f
    }

    // ---------------------------------------------------------------- Notes

    private var layout: StaticLayout? = null
    private var layoutKey: String? = null

    /** The note's text laid out at scale 1 (kept for the screen's paints; made fresh for any other). */
    private fun noteLayout(p: ItemPaints = ItemPaints.screen): StaticLayout {
        val inner = (noteW - 2 * NOTE_PAD - 3f).roundToInt().coerceAtLeast(10)
        val key = "$inner|$note"
        if (p === ItemPaints.screen) layout?.let { if (layoutKey == key) return it }
        val text = note.ifEmpty { " " }
        @Suppress("DEPRECATION")
        val l = if (android.os.Build.VERSION.SDK_INT >= 23) {
            StaticLayout.Builder.obtain(text, 0, text.length, p.noteText, inner).setIncludePad(false).build()
        } else {
            StaticLayout(text, p.noteText, inner, Layout.Alignment.ALIGN_NORMAL, 1f, 0f, false)
        }
        if (p === ItemPaints.screen) {
            layout = l
            layoutKey = key
        }
        return l
    }

    /** Sets a note's height to fit its text (its width stays). */
    fun sizeNote() {
        if (!isNote) return
        noteH = ceil(noteLayout().height + NOTE_PAD * 1.4f).coerceAtLeast(NOTE_FONT + NOTE_PAD * 1.4f)
    }

    private fun drawNote(canvas: Canvas, boardScale: Float, p: ItemPaints) {
        val a = (opacity * 255).roundToInt()
        val k = scale // board units per note unit
        val r = p.rect
        r.set(x, y, x + width, y + height)
        val rad = 8f * k
        p.noteShadow.alpha = (60 * opacity).roundToInt()
        canvas.save()
        canvas.translate(0f, 3f * k)
        canvas.drawRoundRect(r, rad, rad, p.noteShadow)
        canvas.restore()
        p.noteFill.alpha = a
        canvas.drawRoundRect(r, rad, rad, p.noteFill)
        p.noteBar.alpha = a
        canvas.save()
        canvas.clipRect(r.left, r.top, r.left + 5f * k, r.bottom)
        canvas.drawRoundRect(r, rad, rad, p.noteBar)
        canvas.restore()
        val onScreenFont = NOTE_FONT * k * boardScale
        if (onScreenFont >= 4f) {
            canvas.save()
            canvas.translate(x + (NOTE_PAD + 3f) * k, y + NOTE_PAD * 0.7f * k)
            canvas.scale(k, k)
            canvas.clipRect(0f, 0f, noteW, noteH)
            p.noteText.alpha = a
            noteLayout(p).draw(canvas)
            canvas.restore()
        } else {
            // Too small to read: a few grey lines stand in for the text.
            p.noteLines.alpha = (70 * opacity).roundToInt()
            val lh = height / 6f
            for (i in 1..3) {
                val w = width * (if (i == 3) 0.6f else 0.75f)
                canvas.drawRect(x + width * 0.12f, y + lh * i * 1.3f, x + width * 0.12f + w, y + lh * i * 1.3f + lh * 0.5f, p.noteLines)
            }
        }
    }

    // ---------------------------------------------------------------- Drawing

    /**
     * Draws the item. [picture] overrides the bitmap to use (exporting); otherwise the best one for the
     * screen size is used, with its value-steps / squint look once that is ready.
     */
    fun draw(
        canvas: Canvas, scratch: RectF, boardScale: Float,
        p: ItemPaints = ItemPaints.screen, picture: android.graphics.Bitmap? = null
    ) {
        if (image == null) {
            drawNote(canvas, boardScale, p)
            return
        }
        val cx = centerX
        val cy = centerY
        val needsTransform = rotation != 0 || flipped
        if (needsTransform) {
            canvas.save()
            if (rotation != 0) canvas.rotate(rotation.toFloat(), cx, cy)
            if (flipped) canvas.scale(-1f, 1f, cx, cy)
        }
        scratch.set(x, y, x + width, y + height)
        val bmp = picture ?: (if (values > 0 || blur) Looks.get(image, values, blur) else null)
            ?: image.bitmapFor(max(width, height) * boardScale)
        if (canvas.canDraw(bmp)) {
            val paint = if (grayscale || values > 0) p.gray else p.image
            val oldAlpha = paint.alpha
            if (opacity < 1f) paint.alpha = (opacity * 255).roundToInt()
            val c = crop
            if (c == null) {
                canvas.drawBitmap(bmp, null, scratch, paint)
            } else {
                val k = bmp.width / image.width.toFloat()
                val srcRect = p.src
                srcRect.set(
                    (c.left * k).roundToInt(), (c.top * k).roundToInt(),
                    (c.right * k).roundToInt().coerceAtMost(bmp.width), (c.bottom * k).roundToInt().coerceAtMost(bmp.height)
                )
                canvas.drawBitmap(bmp, srcRect, scratch, paint)
            }
            paint.alpha = oldAlpha
        }
        if (grid > 1) drawGrid(canvas, scratch, boardScale, p)
        if (needsTransform) canvas.restore()
    }

    private fun drawGrid(canvas: Canvas, r: RectF, boardScale: Float, p: ItemPaints) {
        val px = 1f / boardScale
        p.gridDark.strokeWidth = px * 1.5f
        p.gridLight.strokeWidth = px
        for ((paint, off) in arrayOf(p.gridDark to px, p.gridLight to 0f)) {
            for (i in 1 until grid) {
                val gx = r.left + r.width() * i / grid + off
                val gy = r.top + r.height() * i / grid + off
                canvas.drawLine(gx, r.top, gx, r.bottom, paint)
                canvas.drawLine(r.left, gy, r.right, gy, paint)
            }
        }
    }
}

/**
 * The paints used to draw board items. The screen uses [ItemPaints.screen] (main thread only);
 * exporting a picture in the background makes its own set.
 */
class ItemPaints {
    companion object {
        val screen = ItemPaints()
    }

    val image = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)
    val gray = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG).apply {
        colorFilter = android.graphics.ColorMatrixColorFilter(android.graphics.ColorMatrix().apply { setSaturation(0f) })
    }
    val noteText = TextPaint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#F4F4F5")
        textSize = RefBoardItem.NOTE_FONT
    }
    val noteFill = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#2A2A31") }
    val noteShadow = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#3C000000") }
    val noteBar = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#FACC15") }
    val noteLines = Paint().apply { color = Color.parseColor("#46FFFFFF") }
    val gridDark = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.argb(90, 0, 0, 0); style = Paint.Style.STROKE }
    val gridLight = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.argb(150, 255, 255, 255); style = Paint.Style.STROKE }
    val src = Rect()
    val rect = RectF()
}
