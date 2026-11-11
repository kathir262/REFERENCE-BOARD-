package com.refpad.app

import android.view.View
import android.view.ViewGroup
import android.widget.HorizontalScrollView
import android.widget.LinearLayout

/**
 * Makes a bottom toolbar fit the space it has (phone, tablet, split screen, floating window).
 * When every tool fits, all are shown. When they don't, the least important tools are hidden one
 * by one and a "More" button appears at the end; the hidden tools are offered in a small menu.
 */
class AdaptiveToolbar(
    scroll: HorizontalScrollView,
    private val moreButton: View,
    /** Tools that may be hidden, the first one is hidden first. */
    private val hideOrder: List<View>,
    private val availableWidth: () -> Int,
    private val onMore: (anchor: View, hidden: List<View>) -> Unit
) {
    private val row = scroll.getChildAt(0) as LinearLayout
    /** Plain separator views (no id); dropped first when space is short. */
    private val dividers = (0 until row.childCount).map { row.getChildAt(it) }
        .filter { it.javaClass == View::class.java && it.id == View.NO_ID }
    private val hidden = ArrayList<View>()
    private var lastWidth = -1

    init {
        // List hidden tools in the order they appear on the toolbar.
        moreButton.setOnClickListener { onMore(it, hidden.sortedBy { v -> row.indexOfChild(v) }) }
        // Text inside the row (timer, page number) can grow after the last fit; re-fit if it now overflows.
        row.addOnLayoutChangeListener { _, l, _, r, _, ol, _, or_, _ ->
            if (r - l > or_ - ol) row.post { if (row.width > availableWidth().coerceAtLeast(1)) update(force = true) }
        }
    }

    fun update(force: Boolean = false) {
        val avail = availableWidth()
        if (avail <= 0 || (!force && avail == lastWidth)) return
        lastWidth = avail
        hidden.clear()
        setShown(moreButton, false)
        for (d in dividers) setShown(d, true)
        for (v in hideOrder) setShown(v, true)
        if (naturalWidth() <= avail) return

        for (d in dividers) setShown(d, false)
        setShown(moreButton, true)
        for (v in hideOrder) {
            if (naturalWidth() <= avail) break
            setShown(v, false)
            hidden.add(v)
        }
    }

    private fun setShown(v: View, shown: Boolean) {
        val vis = if (shown) View.VISIBLE else View.GONE
        if (v.visibility != vis) v.visibility = vis
    }

    private fun naturalWidth(): Int {
        var w = row.paddingLeft + row.paddingRight
        val unspecified = View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED)
        for (i in 0 until row.childCount) {
            val c = row.getChildAt(i)
            if (c.visibility == View.GONE) continue
            val lp = c.layoutParams
            // Respect fixed sizes (e.g. 40dp tool buttons, 1dp dividers); measure wrap_content views.
            val widthSpec = if (lp != null && lp.width >= 0)
                View.MeasureSpec.makeMeasureSpec(lp.width, View.MeasureSpec.EXACTLY) else unspecified
            val heightSpec = if (lp != null && lp.height >= 0)
                View.MeasureSpec.makeMeasureSpec(lp.height, View.MeasureSpec.EXACTLY) else unspecified
            c.measure(widthSpec, heightSpec)
            val mlp = lp as? ViewGroup.MarginLayoutParams
            w += c.measuredWidth + (mlp?.leftMargin ?: 0) + (mlp?.rightMargin ?: 0)
        }
        return w
    }
}
