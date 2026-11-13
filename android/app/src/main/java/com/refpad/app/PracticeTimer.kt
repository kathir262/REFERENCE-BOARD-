package com.refpad.app

import android.content.Context
import android.os.Handler
import android.os.Looper
import java.util.Locale
import kotlin.math.max
import kotlin.math.min

/**
 * One timer for the whole app, so the full screen and the floating window never both advance poses.
 * It pauses itself when no screen showing it is visible.
 *
 * Class: a planned run of poses (for example 10 × 30 s, then 5 × 1 min) that ends by itself.
 * Memory mode: when a pose's time is up it is hidden, and you draw it from memory for the same time.
 */
object PracticeTimer {
    private val seconds = intArrayOf(30, 60, 120, 300, 600)

    /** Ready-made classes: name and plan. */
    val CLASSES = listOf(
        "Warm-up · 10 min" to "10x30s, 5x1m",
        "Class · 30 min" to "10x30s, 5x1m, 5x2m, 2x5m",
        "Class · 60 min" to "10x30s, 5x1m, 5x2m, 3x5m, 1x10m, 1x15m"
    )

    private val handler = Handler(Looper.getMainLooper())
    private val listeners = ArrayList<() -> Unit>()
    private var visibleHosts = 0
    private var prefs: android.content.SharedPreferences? = null

    var intervalIndex = 2
        private set
    var remaining = seconds[intervalIndex]
        private set
    var running = false
        private set

    /** Seconds per pose while a class runs, else null. */
    var plan: IntArray? = null
        private set
    var planPos = 0
        private set
    var planName = ""
        private set
    var memory = false
        private set
    private var drawPhase = false
    /** Seconds actually spent on the pose that is showing (for the practice history). */
    private var poseSeconds = 0

    /** Memory mode: the pose is hidden while you draw it from memory. */
    val covered: Boolean get() = memory && drawPhase

    val duration: Int get() = plan?.let { it[min(planPos, it.size - 1)] } ?: seconds[intervalIndex]
    val label: String get() = durationLabel(duration)
    val text: String get() = String.format(Locale.US, "%d:%02d", remaining / 60, remaining % 60)

    /** 0..1000 elapsed fraction of the current pose. */
    val progress: Int get() = ((duration - remaining) * 1000 / max(1, duration))

    fun init(context: Context) {
        if (prefs != null) return
        val p = context.getSharedPreferences("refpad", Context.MODE_PRIVATE)
        prefs = p
        memory = p.getBoolean("memory_mode", false)
        intervalIndex = p.getInt("interval", 2).coerceIn(0, seconds.size - 1)
        remaining = duration
    }

    private val tick = object : Runnable {
        override fun run() {
            if (!running) return
            remaining--
            poseSeconds++
            if (remaining <= 0) {
                if (memory && !drawPhase) {
                    drawPhase = true // hide the pose: now draw it from memory, for the same time
                    remaining = duration
                    DataManager.poseCoverChanged()
                } else {
                    advance()
                    if (!running) return
                }
            }
            notifyListeners()
            handler.postDelayed(this, 1000)
        }
    }

    fun toggle() = if (running) pause() else play()

    fun play() {
        if (running || DataManager.practice.isEmpty()) return
        running = true
        handler.postDelayed(tick, 1000)
        notifyListeners()
    }

    fun pause() {
        if (!running) return
        running = false
        handler.removeCallbacks(tick)
        notifyListeners()
    }

    /** Next pose (when the time is up, or the Next button). A class moves on too, and ends after its last pose. */
    fun next() = advance()

    fun previous() {
        logPose()
        DataManager.prevPose()
        newPose()
    }

    private fun advance() {
        plan?.let { p ->
            planPos++
            if (planPos >= p.size) {
                finishClass()
                return
            }
        }
        logPose()
        DataManager.nextPose()
        newPose()
    }

    private fun newPose() {
        val wasCovered = covered
        drawPhase = false
        poseSeconds = 0
        restartPose()
        if (wasCovered) DataManager.poseCoverChanged()
    }

    /** Starts the countdown for the current pose again (after next/previous, or a new list). */
    fun restartPose() {
        remaining = duration
        if (running) {
            handler.removeCallbacks(tick)
            handler.postDelayed(tick, 1000)
        }
        notifyListeners()
    }

    fun cycleInterval() {
        if (plan != null) return
        intervalIndex = (intervalIndex + 1) % seconds.size
        prefs?.edit()?.putInt("interval", intervalIndex)?.apply()
        restartPose()
    }

    // ---------------------------------------------------------------- Classes

    fun startClass(p: IntArray, name: String) {
        if (p.isEmpty() || DataManager.practice.isEmpty()) return
        plan = p
        planPos = 0
        planName = name
        newPose()
        play()
    }

    fun stopClass() {
        if (plan == null) return
        plan = null
        restartPose()
    }

    private fun finishClass() {
        val p = plan ?: return
        val minutes = p.sum() / 60.0
        val name = planName.ifEmpty { "Class" }
        logPose()
        pause()
        plan = null
        drawPhase = false
        poseSeconds = 0
        remaining = duration
        DataManager.poseCoverChanged()
        notifyListeners()
        val m = if (minutes == Math.floor(minutes)) minutes.toInt().toString() else String.format(Locale.US, "%.1f", minutes)
        DataManager.toast("$name finished · ${p.size} poses · $m min. Well done!")
    }

    // ---------------------------------------------------------------- Memory mode

    fun setMemory(on: Boolean) {
        memory = on
        prefs?.edit()?.putBoolean("memory_mode", on)?.apply()
        if (!on && drawPhase) {
            drawPhase = false
            DataManager.poseCoverChanged()
        }
        notifyListeners()
    }

    /** The practice list was cleared or replaced. */
    fun listChanged() {
        if (DataManager.practice.isEmpty()) {
            pause()
            plan = null
        }
        drawPhase = false
        poseSeconds = 0
        restartPose()
    }

    private fun logPose() {
        if (poseSeconds >= max(5, duration / 2)) PracticeHistory.add(poseSeconds)
        poseSeconds = 0
    }

    // ---------------------------------------------------------------- Hosts and listeners

    fun hostShown() {
        visibleHosts++
    }

    fun hostHidden() {
        visibleHosts = max(0, visibleHosts - 1)
        if (visibleHosts == 0) pause()
    }

    fun addListener(l: () -> Unit) {
        if (!listeners.contains(l)) listeners.add(l)
    }

    fun removeListener(l: () -> Unit) {
        listeners.remove(l)
    }

    private fun notifyListeners() {
        for (l in listeners.toTypedArray()) l()
    }

    // ---------------------------------------------------------------- Plans

    fun durationLabel(sec: Int): String = when {
        sec < 60 -> "$sec sec"
        sec % 60 == 0 -> "${sec / 60} min"
        else -> String.format(Locale.US, "%d:%02d", sec / 60, sec % 60)
    }

    /** "10x30s, 5x1m" -> 30 s ten times, then 60 s five times. Null if it can't be read. */
    fun parsePlan(text: String): IntArray? {
        val out = ArrayList<Int>()
        val re = Regex("""^(\d+)\s*[x×*]\s*(\d+(?:[.,]\d+)?)\s*(s|sec|secs|seconds?|m|min|mins|minutes?)?$""", RegexOption.IGNORE_CASE)
        for (raw in text.split(',', ';', '+')) {
            val part = raw.trim()
            if (part.isEmpty()) continue
            val m = re.find(part) ?: return null
            val count = m.groupValues[1].toIntOrNull() ?: return null
            val amount = m.groupValues[2].replace(',', '.').toDoubleOrNull() ?: return null
            val unit = m.groupValues[3].ifEmpty { if (amount > 10) "s" else "m" }.lowercase()
            val sec = if (unit.startsWith("m")) Math.round(amount * 60).toInt() else Math.round(amount).toInt()
            if (count !in 1..200 || sec !in 5..3600) return null
            repeat(count) { out.add(sec) }
        }
        return if (out.isEmpty()) null else out.toIntArray()
    }

    /** The opposite of [parsePlan]: "10×30s, 5×1m". */
    fun planText(p: IntArray): String {
        val out = ArrayList<String>()
        var i = 0
        while (i < p.size) {
            var j = i
            while (j < p.size && p[j] == p[i]) j++
            val sec = p[i]
            out += "${j - i}×" + if (sec < 60 || sec % 60 != 0) "${sec}s" else "${sec / 60}m"
            i = j
        }
        return out.joinToString(", ")
    }

    var lastCustomPlan: String
        get() = prefs?.getString("class_plan", "") ?: ""
        set(v) {
            prefs?.edit()?.putString("class_plan", v)?.apply()
        }
}
