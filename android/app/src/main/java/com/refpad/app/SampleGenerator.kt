package com.refpad.app

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF

object SampleGenerator {

    fun createSamplePoses(): List<Bitmap> {
        return listOf(
            createDynamicActionPose(),
            createContrappostoPose(),
            createGestureStudyPose()
        )
    }

    private fun createDynamicActionPose(): Bitmap {
        val width = 800
        val height = 1100
        val bmp = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bmp)

        // Studio Dark Background with grid
        val bgPaint = Paint().apply { color = Color.parseColor("#1c1c20") }
        canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), bgPaint)

        // Subtle anatomical grid lines
        val gridPaint = Paint().apply {
            color = Color.parseColor("#2a2a32")
            strokeWidth = 2f
        }
        for (i in 100..height step 150) {
            canvas.drawLine(40f, i.toFloat(), width - 40f, i.toFloat(), gridPaint)
        }

        // Action Line (Dynamic Curve)
        val lineOfActionPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.parseColor("#facc15") // Studio Yellow action line
            strokeWidth = 4f
            style = Paint.Style.STROKE
        }
        val actionPath = Path().apply {
            moveTo(400f, 180f)
            cubicTo(450f, 350f, 320f, 650f, 520f, 950f)
        }
        canvas.drawPath(actionPath, lineOfActionPaint)

        // Figure Silhouette
        val figurePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.parseColor("#e4e4e7")
            style = Paint.Style.FILL
        }

        // Head
        canvas.drawOval(RectF(360f, 140f, 440f, 240f), figurePaint)
        // Torso
        val torsoPath = Path().apply {
            moveTo(350f, 260f)
            lineTo(450f, 250f)
            lineTo(430f, 520f)
            lineTo(340f, 510f)
            close()
        }
        canvas.drawPath(torsoPath, figurePaint)
        // Arms (Dynamic Reach)
        val limbPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.parseColor("#d4d4d8")
            strokeWidth = 36f
            strokeCap = Paint.Cap.ROUND
        }
        canvas.drawLine(440f, 270f, 620f, 200f, limbPaint)
        canvas.drawLine(620f, 200f, 720f, 150f, limbPaint)
        canvas.drawLine(350f, 280f, 240f, 380f, limbPaint)
        canvas.drawLine(240f, 380f, 180f, 500f, limbPaint)

        // Legs
        canvas.drawLine(360f, 520f, 300f, 750f, limbPaint)
        canvas.drawLine(300f, 750f, 280f, 960f, limbPaint)
        canvas.drawLine(420f, 520f, 490f, 720f, limbPaint)
        canvas.drawLine(490f, 720f, 560f, 940f, limbPaint)

        // Studio Label
        val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.parseColor("#a1a1aa")
            textSize = 28f
            isFakeBoldText = true
        }
        canvas.drawText("REFERENCE 01 // DYNAMIC ACTION POSE", 50f, height - 50f, textPaint)

        return bmp
    }

    private fun createContrappostoPose(): Bitmap {
        val width = 800
        val height = 1100
        val bmp = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bmp)

        // Deep studio slate
        val bgPaint = Paint().apply { color = Color.parseColor("#18181b") }
        canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), bgPaint)

        // Action Line
        val lineOfActionPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.parseColor("#facc15")
            strokeWidth = 4f
            style = Paint.Style.STROKE
        }
        val actionPath = Path().apply {
            moveTo(400f, 160f)
            cubicTo(370f, 380f, 440f, 600f, 420f, 960f)
        }
        canvas.drawPath(actionPath, lineOfActionPaint)

        // Silhouette
        val figurePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.parseColor("#f4f4f5")
            style = Paint.Style.FILL
        }
        canvas.drawOval(RectF(365f, 130f, 435f, 230f), figurePaint)

        // Torso with tilt
        val torsoPath = Path().apply {
            moveTo(330f, 250f)
            lineTo(470f, 270f)
            lineTo(450f, 540f)
            lineTo(340f, 510f)
            close()
        }
        canvas.drawPath(torsoPath, figurePaint)

        val limbPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.parseColor("#d4d4d8")
            strokeWidth = 38f
            strokeCap = Paint.Cap.ROUND
        }
        // Arms
        canvas.drawLine(340f, 260f, 290f, 430f, limbPaint)
        canvas.drawLine(290f, 430f, 340f, 540f, limbPaint)
        canvas.drawLine(460f, 275f, 520f, 440f, limbPaint)
        canvas.drawLine(520f, 440f, 530f, 620f, limbPaint)

        // Weight-bearing leg
        canvas.drawLine(360f, 530f, 380f, 750f, limbPaint)
        canvas.drawLine(380f, 750f, 390f, 980f, limbPaint)
        // Relaxed leg
        canvas.drawLine(440f, 540f, 480f, 760f, limbPaint)
        canvas.drawLine(480f, 760f, 460f, 960f, limbPaint)

        // Studio Label
        val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.parseColor("#a1a1aa")
            textSize = 28f
            isFakeBoldText = true
        }
        canvas.drawText("REFERENCE 02 // CONTRAPPOSTO FIGURE", 50f, height - 50f, textPaint)

        return bmp
    }

    private fun createGestureStudyPose(): Bitmap {
        val width = 800
        val height = 1100
        val bmp = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bmp)

        // Studio charcoal
        val bgPaint = Paint().apply { color = Color.parseColor("#151518") }
        canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), bgPaint)

        // Action Line
        val lineOfActionPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.parseColor("#facc15")
            strokeWidth = 4f
            style = Paint.Style.STROKE
        }
        val actionPath = Path().apply {
            moveTo(500f, 220f)
            cubicTo(320f, 380f, 280f, 620f, 460f, 900f)
        }
        canvas.drawPath(actionPath, lineOfActionPaint)

        val figurePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.parseColor("#e4e4e7")
            style = Paint.Style.FILL
        }
        // Head tilted
        canvas.drawOval(RectF(470f, 180f, 550f, 270f), figurePaint)

        // Torso arched
        val torsoPath = Path().apply {
            moveTo(450f, 290f)
            lineTo(530f, 310f)
            lineTo(430f, 570f)
            lineTo(330f, 520f)
            close()
        }
        canvas.drawPath(torsoPath, figurePaint)

        val limbPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.parseColor("#d4d4d8")
            strokeWidth = 36f
            strokeCap = Paint.Cap.ROUND
        }
        canvas.drawLine(460f, 300f, 300f, 370f, limbPaint)
        canvas.drawLine(300f, 370f, 200f, 440f, limbPaint)
        canvas.drawLine(520f, 320f, 620f, 460f, limbPaint)
        canvas.drawLine(620f, 460f, 580f, 620f, limbPaint)

        canvas.drawLine(350f, 540f, 290f, 730f, limbPaint)
        canvas.drawLine(290f, 730f, 220f, 880f, limbPaint)
        canvas.drawLine(420f, 570f, 460f, 750f, limbPaint)
        canvas.drawLine(460f, 750f, 480f, 920f, limbPaint)

        val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.parseColor("#a1a1aa")
            textSize = 28f
            isFakeBoldText = true
        }
        canvas.drawText("REFERENCE 03 // GESTURE & RHYTHM", 50f, height - 50f, textPaint)

        return bmp
    }
}
