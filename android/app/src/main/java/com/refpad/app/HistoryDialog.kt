package com.refpad.app

import android.app.AlertDialog
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.os.Build
import android.view.ContextThemeWrapper
import android.view.View
import android.view.WindowManager
import android.widget.LinearLayout
import android.widget.TextView
import java.util.Calendar
import java.util.Locale
import kotlin.math.max

/** Practice history: poses and minutes today, this week and in total, the streak, and the last two weeks. */
object HistoryDialog {

    fun show(context: Context, overlay: Boolean) {
        val ctx = ContextThemeWrapper(context, android.R.style.Theme_Material_Dialog_Alert)
        val d = context.resources.displayMetrics.density
        val s = PracticeHistory.summary()

        fun line(text: String, size: Float, color: Int, top: Int = 0) = TextView(ctx).apply {
            this.text = text
            textSize = size
            setTextColor(color)
            setPadding(0, (top * d).toInt(), 0, 0)
        }

        val box = LinearLayout(ctx).apply {
            orientation = LinearLayout.VERTICAL
            setPadding((22 * d).toInt(), (8 * d).toInt(), (22 * d).toInt(), 0)
        }
        val main = Color.parseColor("#F4F4F5")
        val muted = Color.parseColor("#A1A1AA")
        box.addView(line("Today:  ${poses(s.todayPoses)} · ${minutes(s.todaySeconds)}", 16f, main))
        box.addView(line("Last 7 days:  ${poses(s.weekPoses)} · ${minutes(s.weekSeconds)}", 14f, muted, 6))
        box.addView(line("All time:  ${poses(s.totalPoses)} · ${minutes(s.totalSeconds)}", 14f, muted, 2))
        box.addView(line(
            if (s.streak > 0) "Streak:  ${s.streak} day${if (s.streak == 1) "" else "s"} in a row" else "Practise today to start a streak",
            14f, Color.parseColor("#FACC15"), 6
        ))
        box.addView(Bars(ctx, s.days), LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, (150 * d).toInt()).apply {
            topMargin = (14 * d).toInt()
        })
        box.addView(line("Poses count when you spend at least half their time on them. Kept on this device only.", 12f, muted, 10))

        val dialog = AlertDialog.Builder(ctx)
            .setTitle("Practice history")
            .setView(box)
            .setPositiveButton("Close", null)
            .setNeutralButton("Clear") { _, _ -> PracticeHistory.clear() }
            .create()
        if (overlay) {
            dialog.window?.setType(
                if (Build.VERSION.SDK_INT >= 26) WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
                else @Suppress("DEPRECATION") WindowManager.LayoutParams.TYPE_PHONE
            )
        }
        dialog.show()
    }

    private fun poses(n: Int) = if (n == 1) "1 pose" else "$n poses"

    private fun minutes(sec: Int): String {
        val m = sec / 60
        return if (m < 60) "$m min" else String.format(Locale.US, "%d h %02d min", m / 60, m % 60)
    }

    /** Minutes practised per day for the last 14 days. */
    private class Bars(context: Context, private val days: List<PracticeHistory.Day>) : View(context) {
        private val d = resources.displayMetrics.density
        private val bar = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#FACC15") }
        private val empty = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#2C2C33") }
        private val label = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.parseColor("#71717A")
            textSize = 10f * d
            textAlign = Paint.Align.CENTER
        }
        private val r = RectF()

        override fun onDraw(canvas: Canvas) {
            if (days.isEmpty()) return
            val most = max(60, days.maxOf { it.seconds })
            val labelH = 16f * d
            val chartH = height - labelH
            val slot = width / days.size.toFloat()
            val w = slot * 0.62f
            for ((i, day) in days.withIndex()) {
                val cx = slot * i + slot / 2f
                val h = if (day.seconds > 0) max(3f * d, chartH * day.seconds / most) else 2f * d
                r.set(cx - w / 2f, chartH - h, cx + w / 2f, chartH)
                canvas.drawRoundRect(r, 3f * d, 3f * d, if (day.seconds > 0) bar else empty)
                if (i % 2 == 1 || i == days.size - 1) {
                    canvas.drawText(day.date.get(Calendar.DAY_OF_MONTH).toString(), cx, height - 3f * d, label)
                }
            }
        }
    }
}
