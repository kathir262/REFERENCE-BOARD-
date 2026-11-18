package com.refpad.app

import android.app.Activity
import android.app.AlertDialog
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.util.Log
import android.view.ContextThemeWrapper
import org.json.JSONArray
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Updates for the website / GitHub version of RefPad (the Google Play version is updated by Play and never
 * runs this). Once a day at most, RefPad asks GitHub whether a newer release exists. If you tap Update, it
 * downloads that release's APK from GitHub only, checks its SHA-256 checksum against the release's .sha256
 * file, and hands it to Android, which asks you to confirm the install. Your board stays.
 */
object AppUpdater {
    private const val TAG = "RefPad"
    private const val REPO = "kathir262/REFERENCE-BOARD-"
    private const val API = "https://api.github.com/repos/$REPO/releases?per_page=20"
    const val RELEASES_PAGE = "https://github.com/$REPO/releases/latest"
    private val ALLOWED_HOSTS = listOf(
        "api.github.com", "github.com", "objects.githubusercontent.com",
        "release-assets.githubusercontent.com", "github-releases.githubusercontent.com"
    )
    private const val MAX_APK_BYTES = 150L * 1024 * 1024
    private const val PREFS = "refpad"
    const val ACTION_INSTALL_STATUS = "com.refpad.app.INSTALL_STATUS"

    class Release(val version: String, val notes: String, val apkUrl: String, val shaUrl: String, val size: Long)

    private val main = Handler(Looper.getMainLooper())
    private val listeners = ArrayList<() -> Unit>()
    private const val KEY_AVAILABLE = "update_available"

    fun addListener(l: () -> Unit) {
        if (!listeners.contains(l)) listeners.add(l)
    }

    fun removeListener(l: () -> Unit) {
        listeners.remove(l)
    }

    /** A newer version found by the last check (and not skipped), or null. Shown as a dot on ⋮ and in Settings. */
    fun availableVersion(context: Context): String? {
        if (!isEnabled(context)) return null
        val p = prefs(context)
        val v = p.getString(KEY_AVAILABLE, null) ?: return null
        if (v == p.getString("skip_version", "")) return null
        val cur = parseVersion(BuildConfig.VERSION_NAME) ?: return null
        val new = parseVersion(v) ?: return null
        return if (compare(new, cur) > 0) v else null
    }

    private fun remember(context: Context, rel: Release?) {
        val e = prefs(context).edit()
        if (rel == null) e.remove(KEY_AVAILABLE) else e.putString(KEY_AVAILABLE, rel.version)
        e.apply()
        for (l in listeners.toTypedArray()) l()
    }

    /** True while a check or download is running. */
    val isBusy: Boolean get() = busy

    /** When the last successful check was (0 = never). */
    fun lastCheck(context: Context): Long = prefs(context).getLong("last_update_check", 0L)
    private val worker = Executors.newSingleThreadExecutor { r -> Thread(r, "refpad-update") }
    private var busy = false

    /** True for the website version installed from the website (not from Google Play). */
    fun isEnabled(context: Context): Boolean = BuildConfig.SELF_UPDATE && !fromPlay(context)

    private fun fromPlay(context: Context): Boolean = try {
        val installer = if (Build.VERSION.SDK_INT >= 30) {
            context.packageManager.getInstallSourceInfo(context.packageName).installingPackageName
        } else {
            @Suppress("DEPRECATION")
            context.packageManager.getInstallerPackageName(context.packageName)
        }
        installer == "com.android.vending"
    } catch (e: Exception) {
        false
    }

    private fun prefs(context: Context) = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun autoCheck(context: Context): Boolean = prefs(context).getBoolean("auto_update", true)

    fun setAutoCheck(context: Context, on: Boolean) = prefs(context).edit().putBoolean("auto_update", on).apply()

    // ---------------------------------------------------------------- Checking

    /** Called when the app opens: checks at most once a day, and only offers versions you haven't skipped. */
    fun checkOnStart(activity: Activity) {
        if (!isEnabled(activity) || !autoCheck(activity) || busy) return
        val p = prefs(activity)
        if (System.currentTimeMillis() - p.getLong("last_update_check", 0L) < 20L * 3600 * 1000) return
        check(activity) { rel, error ->
            // Only a check that reached GitHub counts; offline, it simply tries again next time RefPad opens.
            if (error == null) {
                p.edit().putLong("last_update_check", System.currentTimeMillis()).apply()
                remember(activity, rel)
            }
            if (rel != null && rel.version != p.getString("skip_version", "")) offer(activity, rel, manual = false)
        }
    }

    /** "Check for updates" in the menu. */
    fun checkNow(activity: Activity) {
        if (busy) return
        DataManager.setStatus("Checking for updates…")
        check(activity) { rel, error ->
            DataManager.setStatus(null)
            if (error == null) {
                prefs(activity).edit().putLong("last_update_check", System.currentTimeMillis()).apply()
                remember(activity, rel)
            }
            when {
                error != null -> DataManager.toast(error)
                rel == null -> DataManager.toast("You have the latest version (${BuildConfig.VERSION_NAME})")
                else -> offer(activity, rel, manual = true)
            }
        }
    }

    private fun check(context: Context, done: (Release?, String?) -> Unit) {
        busy = true
        worker.execute {
            var rel: Release? = null
            var error: String? = null
            try {
                rel = newest(String(get(API, 4L * 1024 * 1024), Charsets.UTF_8))
            } catch (e: Exception) {
                Log.w(TAG, "Update check failed", e)
                error = "Couldn't check for updates. Check your internet connection."
            }
            main.post {
                busy = false
                done(rel, error)
            }
        }
    }

    /** The newest published release with an Android APK and checksum that is newer than this app. */
    private fun newest(json: String): Release? {
        val current = parseVersion(BuildConfig.VERSION_NAME) ?: return null
        var best: Release? = null
        var bestV: List<Int>? = null
        val list = JSONArray(json)
        for (i in 0 until list.length()) {
            val r = list.optJSONObject(i) ?: continue
            if (r.optBoolean("draft") || r.optBoolean("prerelease")) continue
            val v = parseVersion(r.optString("tag_name")) ?: continue
            if (compare(v, current) <= 0 || (bestV != null && compare(v, bestV) <= 0)) continue
            val text = v.joinToString(".")
            val apkName = "RefPad-$text-android.apk"
            var apk: String? = null
            var sha: String? = null
            var size = 0L
            val assets = r.optJSONArray("assets") ?: continue
            for (k in 0 until assets.length()) {
                val a = assets.optJSONObject(k) ?: continue
                when (a.optString("name")) {
                    apkName -> { apk = a.optString("browser_download_url"); size = a.optLong("size") }
                    "$apkName.sha256" -> sha = a.optString("browser_download_url")
                }
            }
            if (apk.isNullOrEmpty() || sha.isNullOrEmpty()) continue
            best = Release(text, r.optString("body"), apk, sha, size)
            bestV = v
        }
        return best
    }

    private fun parseVersion(tag: String): List<Int>? {
        val m = Regex("""(\d+)\.(\d+)(?:\.(\d+))?""").find(tag) ?: return null
        return listOf(m.groupValues[1].toInt(), m.groupValues[2].toInt(), m.groupValues[3].ifEmpty { "0" }.toInt())
    }

    private fun compare(a: List<Int>, b: List<Int>): Int {
        for (i in 0 until 3) if (a[i] != b[i]) return a[i].compareTo(b[i])
        return 0
    }

    // ---------------------------------------------------------------- Offering and installing

    private fun offer(activity: Activity, rel: Release, manual: Boolean) {
        if (activity.isFinishing) return
        val ctx = ContextThemeWrapper(activity, android.R.style.Theme_Material_Dialog_Alert)
        val notes = rel.notes.trim().take(1500).ifEmpty { "A new version of RefPad is ready." }
        val b = AlertDialog.Builder(ctx)
            .setTitle("RefPad ${rel.version} is available")
            .setMessage(if (notes.contains("kept", ignoreCase = true)) notes else "$notes\n\nYour board is kept.")
            .setPositiveButton("Update") { _, _ -> download(activity, rel) }
            .setNegativeButton("Later", null)
        if (!manual) b.setNeutralButton("Skip this version") { _, _ ->
            prefs(activity).edit().putString("skip_version", rel.version).apply()
            for (l in listeners.toTypedArray()) l()
        }
        b.show()
    }

    private fun download(activity: Activity, rel: Release) {
        if (rel.size > MAX_APK_BYTES) return DataManager.toast("The update is unexpectedly large, so it was not downloaded.")
        // Android 8+: RefPad needs your OK once to install updates. The install screen asks for it too,
        // but saying so first is clearer.
        if (Build.VERSION.SDK_INT >= 26 && !activity.packageManager.canRequestPackageInstalls()) {
            DataManager.toast("Allow RefPad to install updates, then tap Update again")
            try {
                activity.startActivity(
                    Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${activity.packageName}"))
                )
            } catch (e: Exception) {
                Log.w(TAG, "No install-permission screen", e)
            }
            return
        }
        busy = true
        val cancelled = AtomicBoolean(false)
        val stop: () -> Unit = { cancelled.set(true) }
        DataManager.setStatus("Downloading RefPad ${rel.version}…", stop)
        val app = activity.applicationContext
        worker.execute {
            var file: File? = null
            var error: String? = null
            try {
                val expected = String(get(rel.shaUrl, 4096), Charsets.UTF_8).trim().split(Regex("\\s+"))[0].lowercase()
                if (!Regex("[0-9a-f]{64}").matches(expected)) throw IllegalStateException("bad checksum file")
                val dir = File(app.cacheDir, "updates").apply { deleteRecursively(); mkdirs() }
                val out = File(dir, "RefPad-${rel.version}.apk")
                val digest = MessageDigest.getInstance("SHA-256")
                var lastShown = 0
                download(rel.apkUrl, out, digest, cancelled) { got, total ->
                    val pct = if (total > 0) (got * 100 / total).toInt() else 0
                    if (pct >= lastShown + 5) {
                        lastShown = pct
                        main.post { if (!cancelled.get()) DataManager.setStatus("Downloading RefPad ${rel.version}… $pct%", stop) }
                    }
                }
                if (cancelled.get()) throw InterruptedException()
                if (rel.size > 0 && out.length() != rel.size) throw IllegalStateException("incomplete")
                val got = digest.digest().joinToString("") { "%02x".format(it) }
                if (got != expected) {
                    out.delete()
                    error = "The download doesn't match its checksum, so it was not installed."
                } else {
                    file = out
                }
            } catch (e: InterruptedException) {
                error = "Download stopped"
            } catch (e: Exception) {
                Log.w(TAG, "Update download failed", e)
                error = "The download didn't finish. Check your internet connection and try again."
            }
            main.post {
                busy = false
                DataManager.setStatus(null)
                val f = file
                if (f == null) DataManager.toast(error ?: "Update failed") else install(activity, f)
            }
        }
    }

    /** Hands the verified APK to Android's installer; Android shows its own "Update RefPad?" screen. */
    private fun install(activity: Activity, apk: File) {
        try {
            val installer = activity.packageManager.packageInstaller
            val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL)
            params.setAppPackageName(activity.packageName)
            val id = installer.createSession(params)
            installer.openSession(id).use { session ->
                session.openWrite("refpad.apk", 0, apk.length()).use { out ->
                    apk.inputStream().use { it.copyTo(out, 256 * 1024) }
                    session.fsync(out)
                }
                // The result comes back to the main screen (MainActivity.onNewIntent -> handleInstallStatus).
                val intent = Intent(activity, MainActivity::class.java).setAction(ACTION_INSTALL_STATUS)
                val flags = PendingIntent.FLAG_UPDATE_CURRENT or (if (Build.VERSION.SDK_INT >= 31) PendingIntent.FLAG_MUTABLE else 0)
                session.commit(PendingIntent.getActivity(activity, 7, intent, flags).intentSender)
            }
        } catch (e: Exception) {
            Log.w(TAG, "Install failed", e)
            DataManager.toast("Couldn't start the update. You can also download RefPad from the website.")
        }
    }

    /** What Android says about the install: ask the user to confirm, or report a failure. */
    fun handleInstallStatus(activity: Activity, intent: Intent): Boolean {
        if (intent.action != ACTION_INSTALL_STATUS) return false
        when (intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)) {
            PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                @Suppress("DEPRECATION")
                val confirm: Intent? = if (Build.VERSION.SDK_INT >= 33) intent.getParcelableExtra(Intent.EXTRA_INTENT, Intent::class.java)
                else intent.getParcelableExtra(Intent.EXTRA_INTENT)
                confirm?.let {
                    try {
                        activity.startActivity(it)
                    } catch (e: Exception) {
                        Log.w(TAG, "Can't show install confirmation", e)
                    }
                }
            }
            PackageInstaller.STATUS_SUCCESS -> DataManager.toast("RefPad is up to date")
            PackageInstaller.STATUS_FAILURE_ABORTED -> DataManager.toast("Update cancelled")
            else -> {
                val msg = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE) ?: ""
                Log.w(TAG, "Install failed: $msg")
                DataManager.toast(
                    if (msg.contains("signature", ignoreCase = true) || msg.contains("conflict", ignoreCase = true))
                        "This update can't replace your copy of RefPad (it was installed from somewhere else). Save your board as a file, then reinstall RefPad from the website."
                    else "The update couldn't be installed. Please try again."
                )
            }
        }
        return true
    }

    // ---------------------------------------------------------------- Network (GitHub only)

    private fun open(url: String): HttpURLConnection {
        checkHost(url)
        val c = URL(url).openConnection() as HttpURLConnection
        c.connectTimeout = 15000
        c.readTimeout = 30000
        c.instanceFollowRedirects = true
        c.setRequestProperty("User-Agent", "RefPad-Android/${BuildConfig.VERSION_NAME}")
        c.setRequestProperty("Accept", "application/vnd.github+json")
        val code = c.responseCode
        checkHost(c.url.toString()) // after redirects
        if (code !in 200..299) throw IllegalStateException("HTTP $code")
        return c
    }

    private fun checkHost(url: String) {
        val u = Uri.parse(url)
        val host = (u.host ?: "").lowercase()
        if (u.scheme != "https" || ALLOWED_HOSTS.none { host == it || host.endsWith(".$it") }) {
            throw SecurityException("Unexpected address")
        }
    }

    private fun get(url: String, limit: Long): ByteArray {
        val c = open(url)
        try {
            return c.inputStream.use { inp ->
                val out = java.io.ByteArrayOutputStream()
                val buf = ByteArray(64 * 1024)
                while (true) {
                    val n = inp.read(buf)
                    if (n < 0) break
                    out.write(buf, 0, n)
                    if (out.size() > limit) throw IllegalStateException("too large")
                }
                out.toByteArray()
            }
        } finally {
            c.disconnect()
        }
    }

    private fun download(url: String, dest: File, digest: MessageDigest, cancelled: AtomicBoolean, progress: (Long, Long) -> Unit) {
        val c = open(url)
        try {
            val total = c.contentLengthLong
            if (total > MAX_APK_BYTES) throw IllegalStateException("too large")
            c.inputStream.use { inp ->
                FileOutputStream(dest).use { out ->
                    val buf = ByteArray(256 * 1024)
                    var got = 0L
                    while (!cancelled.get()) {
                        val n = inp.read(buf)
                        if (n < 0) break
                        got += n
                        if (got > MAX_APK_BYTES) throw IllegalStateException("too large")
                        digest.update(buf, 0, n)
                        out.write(buf, 0, n)
                        progress(got, total)
                    }
                }
            }
        } finally {
            c.disconnect()
        }
    }
}
