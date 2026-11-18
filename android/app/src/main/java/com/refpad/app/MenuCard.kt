package com.refpad.app

import android.content.res.ColorStateList
import android.graphics.Typeface
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import kotlin.math.max
import kotlin.math.min

/**
 * A small menu card that opens right where you tapped, inside the screen (or inside the floating window).
 * Tapping outside closes it. Destructive entries ask for a second tap instead of a pop-up dialog.
 */
class MenuCard(private val host: FrameLayout, private val compact: Boolean) {

    sealed class Row
    class Header(val title: String) : Row()
    /** Small icon buttons with a short label, several per line (quick actions without a long list). */
    class Grid(val items: List<Item>, val columns: Int = 5) : Row()
    class Item(
        val label: String,
        val icon: Int,
        val danger: Boolean = false,
        val enabled: Boolean = true,
        /** If set, the first tap shows this text and only the second tap runs [action]. */
        val confirm: String? = null,
        /** Drawn in the accent colour (for example "Settings · update available"). */
        val highlight: Boolean = false,
        val action: () -> Unit
    ) : Row()

    private val ctx = host.context
    private val density = ctx.resources.displayMetrics.density
    private var scrim: View? = null
    private var card: View? = null

    val isShowing: Boolean get() = card != null

    /** Told when the menu opens or closes (used to let the Back gesture close it). */
    var onShowingChanged: ((Boolean) -> Unit)? = null

    fun show(anchorX: Float, anchorY: Float, rows: List<Row>) {
        dismiss()
        onShowingChanged?.invoke(true)
        val scrimView = View(ctx).apply {
            elevation = dp(15).toFloat()
            setOnTouchListener { _, e ->
                if (e.actionMasked == MotionEvent.ACTION_DOWN) dismiss()
                true
            }
        }
        host.addView(scrimView, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))

        val list = LinearLayout(ctx).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(6), dp(6), dp(6), dp(6))
        }
        for ((i, row) in rows.withIndex()) {
            when (row) {
                is Header -> list.addView(header(row.title, first = i == 0))
                is Item -> list.addView(item(row))
                is Grid -> grid(row).forEach { list.addView(it) }
            }
        }
        val scroll = ScrollView(ctx).apply {
            isVerticalScrollBarEnabled = false
            overScrollMode = View.OVER_SCROLL_NEVER
            background = ctx.getDrawable(R.drawable.bg_menu)
            elevation = dp(16).toFloat()
            clipToOutline = true
            alpha = 0f
            addView(list)
        }
        host.addView(scroll, FrameLayout.LayoutParams(dp(if (compact) 220 else 270), ViewGroup.LayoutParams.WRAP_CONTENT).apply {
            gravity = Gravity.TOP or Gravity.START
        })
        scrim = scrimView
        card = scroll
        scroll.post { place(scroll, anchorX, anchorY) }
    }

    fun dismiss() {
        val wasShowing = card != null
        card?.let { host.removeView(it) }
        scrim?.let { host.removeView(it) }
        card = null
        scrim = null
        if (wasShowing) onShowingChanged?.invoke(false)
    }

    /** The status bar / navigation bar sizes over the menu host (the app draws behind them). */
    private fun systemBars(): Pair<Int, Int> {
        val insets = host.rootWindowInsets ?: return 0 to 0
        return if (android.os.Build.VERSION.SDK_INT >= 30) {
            val i = insets.getInsets(android.view.WindowInsets.Type.systemBars() or android.view.WindowInsets.Type.displayCutout())
            i.top to i.bottom
        } else {
            @Suppress("DEPRECATION")
            insets.systemWindowInsetTop to insets.systemWindowInsetBottom
        }
    }

    private fun place(v: View, ax: Float, ay: Float) {
        if (card !== v) return
        val margin = dp(8)
        // Keep the whole menu between the status bar and the navigation bar, so no row hides under them.
        val (barTop, barBottom) = systemBars()
        val top = barTop + margin
        val bottom = host.height - barBottom - margin
        val maxH = bottom - top
        if (maxH > 0 && v.height > maxH) {
            v.layoutParams = v.layoutParams.apply { height = maxH }
        }
        val h = if (maxH > 0) min(v.height, maxH) else v.height
        val w = v.width
        val x = (ax - dp(20)).coerceIn(margin.toFloat(), max(margin, host.width - w - margin).toFloat())
        val below = ay + dp(4)
        val y = if (below + h <= bottom) below else ay - h - dp(4)
        v.translationX = x
        v.translationY = y.coerceIn(top.toFloat(), max(top, bottom - h).toFloat())
        v.pivotX = (ax - x).coerceIn(0f, w.toFloat())
        v.pivotY = 0f
        v.scaleX = 0.94f
        v.scaleY = 0.94f
        v.animate().alpha(1f).scaleX(1f).scaleY(1f).setDuration(110).start()
    }

    private fun header(title: String, first: Boolean) = TextView(ctx).apply {
        text = title.uppercase()
        textSize = 11f
        letterSpacing = 0.08f
        typeface = Typeface.DEFAULT_BOLD
        setTextColor(ctx.getColor(R.color.text_muted))
        setPadding(dp(12), dp(if (first) 6 else 14), dp(12), dp(4))
    }

    private fun grid(g: Grid): List<View> {
        val lines = ArrayList<View>()
        for (chunk in g.items.chunked(g.columns.coerceAtLeast(1))) {
            val line = LinearLayout(ctx).apply { orientation = LinearLayout.HORIZONTAL }
            for (row in chunk) {
                val cell = TextView(ctx).apply {
                    text = row.label
                    textSize = 10.5f
                    gravity = Gravity.CENTER
                    maxLines = 1
                    setTextColor(ctx.getColor(if (row.danger) R.color.danger else R.color.text_primary))
                    setPadding(dp(2), dp(8), dp(2), dp(6))
                    compoundDrawablePadding = dp(4)
                    background = ctx.getDrawable(R.drawable.bg_menu_item)
                    ctx.getDrawable(row.icon)?.mutate()?.let { icon ->
                        icon.setBounds(0, 0, dp(22), dp(22))
                        setCompoundDrawablesRelative(null, icon, null, null)
                    }
                    compoundDrawableTintList = ColorStateList.valueOf(ctx.getColor(if (row.danger) R.color.danger else R.color.text_secondary))
                    isEnabled = row.enabled
                    alpha = if (row.enabled) 1f else 0.38f
                    setOnClickListener {
                        dismiss()
                        row.action()
                    }
                }
                line.addView(cell, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            }
            // Keep cells the same width on a last, shorter line.
            repeat(g.columns - chunk.size) { line.addView(View(ctx), LinearLayout.LayoutParams(0, 1, 1f)) }
            lines += line
        }
        return lines
    }

    private fun item(row: Item) = TextView(ctx).apply {
        text = row.label
        textSize = if (compact) 13.5f else 15f
        setTextColor(ctx.getColor(if (row.danger) R.color.danger else if (row.highlight) R.color.accent else R.color.text_primary))
        if (row.highlight) typeface = Typeface.DEFAULT_BOLD
        gravity = Gravity.CENTER_VERTICAL
        minHeight = dp(if (compact) 40 else 48)
        setPadding(dp(12), 0, dp(14), 0)
        compoundDrawablePadding = dp(14)
        background = ctx.getDrawable(R.drawable.bg_menu_item)
        ctx.getDrawable(row.icon)?.mutate()?.let { icon ->
            icon.setBounds(0, 0, dp(20), dp(20))
            setCompoundDrawablesRelative(icon, null, null, null)
        }
        compoundDrawableTintList = ColorStateList.valueOf(
            ctx.getColor(if (row.danger) R.color.danger else if (row.highlight) R.color.accent else R.color.text_secondary)
        )
        isEnabled = row.enabled
        alpha = if (row.enabled) 1f else 0.38f
        var armed = false
        setOnClickListener {
            if (row.confirm != null && !armed) {
                armed = true
                text = row.confirm
                typeface = Typeface.DEFAULT_BOLD
                return@setOnClickListener
            }
            dismiss()
            row.action()
        }
    }

    private fun dp(v: Int) = (v * density).toInt()
}
