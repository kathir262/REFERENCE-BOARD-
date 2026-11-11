package com.refpad.app

import android.os.Handler
import android.os.Looper
import java.util.Locale
import kotlin.math.max

/**
 * One timer for the whole app, so the full screen and the floating window never both advance poses.
 * It pauses itself when no screen showing it is visible.
 */
object PracticeTimer {
    private val seconds = intArrayOf(30, 60, 120, 300, 600)
    private val labels = arrayOf("30 sec", "1 min", "2 min", "5 min", "10 min")

    private val handler = Handler(Looper.getMainLooper())
    private val listeners = ArrayList<() -> Unit>()
    private var visibleHosts = 0

    var intervalIndex = 2
        private set
    var remaining = seconds[intervalIndex]
        private set
    var running = false
        private set

    val duration: Int get() = seconds[intervalIndex]
    val label: String get() = labels[intervalIndex]
    val text: String get() = String.format(Locale.US, "%d:%02d", remaining / 60, remaining % 60)

    /** 0..1000 elapsed fraction of the current pose. */
    val progress: Int get() = ((duration - remaining) * 1000 / duration)

    private val tick = object : Runnable {
        override fun run() {
            if (!running) return
            remaining--
            if (remaining <= 0) {
                remaining = duration
                DataManager.nextPose()
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

    /** Starts the countdown for the current pose again (after next/previous). */
    fun restartPose() {
        remaining = duration
        if (running) {
            handler.removeCallbacks(tick)
            handler.postDelayed(tick, 1000)
        }
        notifyListeners()
    }

    fun cycleInterval() {
        intervalIndex = (intervalIndex + 1) % seconds.size
        restartPose()
    }

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
}
