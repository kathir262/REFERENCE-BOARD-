package com.refpad.app

import android.content.Context
import android.util.Log
import org.json.JSONObject
import java.io.File
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Locale

/** Poses drawn and minutes practised per day, kept on this device only (shown in Practice history). */
object PracticeHistory {
    private var file: File? = null
    private val dayFormat = SimpleDateFormat("yyyy-MM-dd", Locale.US)

    class Day(val date: Calendar, val poses: Int, val seconds: Int)

    class Summary(
        val todayPoses: Int, val todaySeconds: Int,
        val weekPoses: Int, val weekSeconds: Int,
        val totalPoses: Int, val totalSeconds: Int,
        val streak: Int,
        /** The last 14 days, oldest first. */
        val days: List<Day>
    )

    fun init(context: Context) {
        if (file == null) file = File(context.filesDir, "history.json")
    }

    private fun load(): JSONObject = try {
        file?.takeIf { it.exists() }?.let { JSONObject(it.readText()) } ?: JSONObject()
    } catch (e: Exception) {
        Log.w("RefPad", "Practice history unreadable", e)
        JSONObject()
    }

    private fun save(data: JSONObject) {
        val f = file ?: return
        try {
            val tmp = File(f.parentFile, "history.json.tmp")
            tmp.writeText(data.toString())
            if (!tmp.renameTo(f)) {
                f.delete()
                tmp.renameTo(f)
            }
        } catch (e: Exception) {
            Log.w("RefPad", "Saving practice history failed", e)
        }
    }

    /** One pose practised for [seconds]. */
    fun add(seconds: Int) {
        val data = load()
        val key = dayFormat.format(Calendar.getInstance().time)
        val d = data.optJSONObject(key) ?: JSONObject().put("poses", 0).put("seconds", 0)
        d.put("poses", d.optInt("poses") + 1)
        d.put("seconds", d.optInt("seconds") + seconds)
        data.put(key, d)
        save(data)
    }

    fun clear() = save(JSONObject())

    fun summary(): Summary {
        val data = load()
        fun day(back: Int): Day {
            val c = Calendar.getInstance()
            c.add(Calendar.DAY_OF_YEAR, -back)
            val d = data.optJSONObject(dayFormat.format(c.time))
            return Day(c, d?.optInt("poses") ?: 0, d?.optInt("seconds") ?: 0)
        }
        val week = (0 until 7).map { day(it) }
        var streak = 0
        var n = if (day(0).poses > 0) 0 else 1 // today doesn't break the streak until it's over
        while (n < 3660 && day(n).poses > 0) {
            streak++
            n++
        }
        var totalPoses = 0
        var totalSeconds = 0
        for (k in data.keys()) {
            val d = data.optJSONObject(k) ?: continue
            totalPoses += d.optInt("poses")
            totalSeconds += d.optInt("seconds")
        }
        val today = day(0)
        return Summary(
            today.poses, today.seconds,
            week.sumOf { it.poses }, week.sumOf { it.seconds },
            totalPoses, totalSeconds, streak,
            (13 downTo 0).map { day(it) }
        )
    }
}
