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
    class Item(
        val label: String,
        val icon: Int,
        val danger: Boolean = false,
        val enabled: Boolean = true,
        /** If set, the first tap shows this text and only the second tap runs [action]. */
        val confirm: String? = null,
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

    private fun place(v: View, ax: Float, ay: Float) {
        if (card !== v) return
        val margin = dp(8)
        val maxH = host.height - 2 * margin
        if (maxH > 0 && v.height > maxH) {
            v.layoutParams = v.layoutParams.apply { height = maxH }
        }
        val h = if (maxH > 0) min(v.height, maxH) else v.height
        val w = v.width
        val x = (ax - dp(20)).coerceIn(margin.toFloat(), max(margin, host.width - w - margin).toFloat())
        val below = ay + dp(4)
        val y = if (below + h + margin <= host.height) below else ay - h - dp(4)
        v.translationX = x
        v.translationY = y.coerceIn(margin.toFloat(), max(margin, host.height - h - margin).toFloat())
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

    private fun item(row: Item) = TextView(ctx).apply {
        text = row.label
        textSize = if (compact) 13.5f else 15f
        setTextColor(ctx.getColor(if (row.danger) R.color.danger else R.color.text_primary))
        gravity = Gravity.CENTER_VERTICAL
        minHeight = dp(if (compact) 40 else 48)
        setPadding(dp(12), 0, dp(14), 0)
        compoundDrawablePadding = dp(14)
        background = ctx.getDrawable(R.drawable.bg_menu_item)
        ctx.getDrawable(row.icon)?.mutate()?.let { icon ->
            icon.setBounds(0, 0, dp(20), dp(20))
            setCompoundDrawablesRelative(icon, null, null, null)
        }
        compoundDrawableTintList = ColorStateList.valueOf(ctx.getColor(if (row.danger) R.color.danger else R.color.text_secondary))
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
