package com.refpad.app

import android.app.Activity
import android.content.Intent
import android.content.res.ColorStateList
import android.graphics.Typeface
import android.net.Uri
import android.os.Bundle
import android.text.format.DateUtils
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.Switch
import android.widget.TextView

/** Settings: updates, board background, practice, and about / privacy. */
class SettingsActivity : Activity() {

    private lateinit var list: LinearLayout
    private val density by lazy { resources.displayMetrics.density }
    private val refresh: () -> Unit = { build() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)
        DataManager.init(this)
        list = findViewById(R.id.settings_list)
        // A comfortable reading width on a tablet, the full width on a phone.
        (list.layoutParams as android.widget.FrameLayout.LayoutParams).let {
            it.width = minOf(dp(680), resources.displayMetrics.widthPixels)
            it.gravity = Gravity.CENTER_HORIZONTAL
        }
        findViewById<View>(R.id.btn_back).setOnClickListener { finish() }
    }

    override fun onResume() {
        super.onResume()
        AppUpdater.addListener(refresh)
        build()
    }

    override fun onPause() {
        AppUpdater.removeListener(refresh)
        super.onPause()
    }

    private fun dp(v: Int) = (v * density).toInt()

    private fun build() {
        list.removeAllViews()

        // Updates
        section("Updates")
        val version = BuildConfig.VERSION_NAME
        if (AppUpdater.isEnabled(this)) {
            val waiting = AppUpdater.availableVersion(this)
            val last = AppUpdater.lastCheck(this)
            text("RefPad $version", 16f, R.color.text_primary, bold = true)
            when {
                waiting != null -> text("RefPad $waiting is available", 14f, R.color.accent, bold = true)
                last > 0 -> text("You have the latest version · checked " +
                    DateUtils.getRelativeTimeSpanString(last, System.currentTimeMillis(), DateUtils.MINUTE_IN_MILLIS), 14f, R.color.text_secondary)
                else -> text("Not checked yet", 14f, R.color.text_secondary)
            }
            button(if (waiting != null) "Update to $waiting" else "Check for updates", primary = waiting != null) {
                AppUpdater.checkNow(this)
            }
            switch("Check for updates every day", "Once a day, only to github.com", AppUpdater.autoCheck(this)) { on ->
                AppUpdater.setAutoCheck(this, on)
            }
        } else {
            text("RefPad $version", 16f, R.color.text_primary, bold = true)
            text("Updates come from Google Play", 14f, R.color.text_secondary)
        }

        // Board
        section("Board")
        text("Background", 15f, R.color.text_primary)
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        for ((i, name) in listOf("Dark", "Neutral grey", "Light").withIndex()) {
            row.addView(chip(name, i == DataManager.background) {
                DataManager.setBackground(i)
                build()
            }, LinearLayout.LayoutParams(0, dp(44), 1f).apply { if (i > 0) marginStart = dp(8) })
        }
        list.addView(row, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply {
            topMargin = dp(8)
        })

        // Toolbar
        section("Toolbar")
        text("Position (you can also drag the toolbar by the dotted handle at its start)", 15f, R.color.text_primary)
        val prefs = getSharedPreferences("refpad", MODE_PRIVATE)
        val side = prefs.getInt("toolbar_side", BoardController.SIDE_BOTTOM)
        val sides = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        for ((i, name) in listOf("Bottom", "Left side", "Right side").withIndex()) {
            sides.addView(chip(name, i == side) {
                prefs.edit().putInt("toolbar_side", i).apply()
                build()
            }, LinearLayout.LayoutParams(0, dp(44), 1f).apply { if (i > 0) marginStart = dp(8) })
        }
        list.addView(sides, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply {
            topMargin = dp(8)
        })

        // Practice
        section("Practice")
        switch("Memory mode", "When a pose's time is up it hides, and you draw it from memory", PracticeTimer.memory) { on ->
            PracticeTimer.setMemory(on)
        }
        button("Practice history", primary = false) { HistoryDialog.show(this, overlay = false) }

        // About
        section("About")
        button("Privacy policy", primary = false) { startActivity(Intent(this, PrivacyActivity::class.java)) }
        button("RefPad website", primary = false) {
            try {
                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://huashijie-pro.vercel.app/apps/refpad.html")))
            } catch (e: Exception) {
                DataManager.toast("No browser found")
            }
        }
        text("RefPad $version · free, no ads, no tracking", 13f, R.color.text_muted)
    }

    private fun section(title: String) {
        list.addView(TextView(this).apply {
            text = title.uppercase()
            textSize = 12f
            letterSpacing = 0.08f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(getColor(R.color.text_muted))
            setPadding(0, dp(if (list.childCount == 0) 4 else 28), 0, dp(6))
        })
    }

    private fun text(value: String, size: Float, color: Int, bold: Boolean = false) {
        list.addView(TextView(this).apply {
            text = value
            textSize = size
            setTextColor(getColor(color))
            if (bold) typeface = Typeface.DEFAULT_BOLD
            setPadding(0, dp(3), 0, dp(3))
        })
    }

    private fun button(label: String, primary: Boolean, action: () -> Unit) {
        list.addView(TextView(this).apply {
            text = label
            textSize = 15f
            gravity = Gravity.CENTER
            typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)
            setTextColor(getColor(if (primary) R.color.text_on_accent else R.color.text_primary))
            background = getDrawable(if (primary) R.drawable.bg_button_primary else R.drawable.bg_button_secondary)
            isClickable = true
            setOnClickListener { action() }
        }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(48)).apply { topMargin = dp(10) })
    }

    private fun chip(label: String, selected: Boolean, action: () -> Unit) = TextView(this).apply {
        text = label
        textSize = 14f
        gravity = Gravity.CENTER
        setTextColor(getColor(if (selected) R.color.text_on_accent else R.color.text_primary))
        background = getDrawable(if (selected) R.drawable.bg_button_primary else R.drawable.bg_button_secondary)
        isClickable = true
        setOnClickListener { action() }
    }

    private fun switch(label: String, detail: String, on: Boolean, changed: (Boolean) -> Unit) {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, dp(10), 0, dp(4))
        }
        val texts = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        texts.addView(TextView(this).apply {
            text = label
            textSize = 15f
            setTextColor(getColor(R.color.text_primary))
        })
        texts.addView(TextView(this).apply {
            text = detail
            textSize = 13f
            setTextColor(getColor(R.color.text_secondary))
        })
        row.addView(texts, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        row.addView(Switch(this).apply {
            isChecked = on
            thumbTintList = ColorStateList(arrayOf(intArrayOf(android.R.attr.state_checked), intArrayOf()),
                intArrayOf(getColor(R.color.accent), getColor(R.color.text_secondary)))
            trackTintList = ColorStateList(arrayOf(intArrayOf(android.R.attr.state_checked), intArrayOf()),
                intArrayOf(getColor(R.color.accent_soft), getColor(R.color.stroke_strong)))
            setOnCheckedChangeListener { _, checked -> changed(checked) }
        })
        list.addView(row)
    }
}
