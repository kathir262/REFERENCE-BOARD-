package com.refpad.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.content.res.Configuration
import android.graphics.PixelFormat
import android.graphics.drawable.Icon
import android.os.Build
import android.os.IBinder
import android.provider.Settings
import android.util.Log
import android.view.ContextThemeWrapper
import android.view.Gravity
import android.view.LayoutInflater
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.Toast
import kotlin.math.abs
import kotlin.math.roundToInt

/** The floating reference window that stays on top of drawing apps. */
class FloatingOverlayService : Service(), BoardController.Host {

    companion object {
        const val ACTION_STOP = "com.refpad.app.STOP_FLOATING"
        private const val NOTIFICATION_ID = 1001
        private const val CHANNEL_ID = "refpad_floating"
        private const val PREFS = "floating_window"
        private val OPACITY_STEPS = floatArrayOf(1f, 0.85f, 0.7f, 0.55f)

        @Volatile
        var isRunning = false
            private set

        private var instance: FloatingOverlayService? = null

        /** Called by [PickerActivity] when the picker closes, to bring the window back. */
        fun onPickerClosed() {
            instance?.restoreAfterPicker()
        }
    }

    /** True while the window is shrunk to the bubble so the picker is not covered. */
    private var minimizedForPicker = false

    private lateinit var wm: WindowManager
    private lateinit var params: WindowManager.LayoutParams
    private var overlayView: View? = null
    private var controller: BoardController? = null
    private var shownToTimer = false

    private lateinit var windowContainer: View
    private lateinit var resizeHandle: View
    private lateinit var bubble: View
    private var minimized = false
    private var expandedW = 0
    private var expandedH = 0

    private val prefs by lazy { getSharedPreferences(PREFS, MODE_PRIVATE) }
    private val density get() = resources.displayMetrics.density

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        isRunning = true
        instance = this
        DataManager.init(this)
        // Must happen first: Android kills a foreground service that does not show its notification in time.
        if (!startInForeground()) {
            stopSelf()
            return
        }
        if (Build.VERSION.SDK_INT >= 23 && !Settings.canDrawOverlays(this)) {
            toast("Allow \"Appear on top\" for RefPad to use the floating window")
            stopSelf()
            return
        }
        try {
            createWindow()
        } catch (e: Exception) {
            Log.e("RefPad", "Could not show floating window", e)
            toast("Could not show the floating window")
            stopSelf()
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelf()
            return START_NOT_STICKY
        }
        startInForeground()
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        isRunning = false
        if (instance === this) instance = null
        controller?.detach()
        if (shownToTimer) PracticeTimer.hostHidden()
        overlayView?.let {
            try {
                wm.removeView(it)
            } catch (_: Exception) {
            }
        }
        overlayView = null
        DataManager.saveNow()
        super.onDestroy()
    }

    override fun onConfigurationChanged(newConfig: Configuration) {
        super.onConfigurationChanged(newConfig)
        if (overlayView != null) {
            clampToScreen()
            updateLayout()
        }
    }

    // ---------------------------------------------------------------- Window

    private fun createWindow() {
        wm = getSystemService(WINDOW_SERVICE) as WindowManager
        val (screenW, screenH) = screenSize()
        val defW = (screenW * 0.36f).roundToInt().coerceIn(dp(360), dp(560)).coerceAtMost(screenW)
        val defH = (defW * 1.3f).roundToInt().coerceAtMost((screenH * 0.85f).roundToInt())

        @Suppress("DEPRECATION")
        val type = if (Build.VERSION.SDK_INT >= 26) WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        else WindowManager.LayoutParams.TYPE_PHONE

        params = WindowManager.LayoutParams(
            prefs.getInt("w", defW),
            prefs.getInt("h", defH),
            type,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_HARDWARE_ACCELERATED,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = prefs.getInt("x", dp(24))
            y = prefs.getInt("y", dp(80))
            alpha = prefs.getFloat("alpha", 1f)
        }
        clampToScreen()

        val view = LayoutInflater.from(ContextThemeWrapper(this, R.style.AppTheme)).inflate(R.layout.floating_overlay, null)
        windowContainer = view.findViewById(R.id.window_container)
        resizeHandle = view.findViewById(R.id.resize_handle)
        bubble = view.findViewById(R.id.minimized_bubble)

        val c = BoardController(view, view.findViewById<FrameLayout>(R.id.content_area), compact = true, host = this)
        view.findViewById<View>(R.id.btn_close).setOnClickListener { stopSelf() }
        view.findViewById<View>(R.id.btn_minimize).setOnClickListener { minimize() }
        setupMoveAndResize(view)

        wm.addView(view, params)
        overlayView = view
        controller = c
        c.attach()
        PracticeTimer.hostShown()
        shownToTimer = true
    }

    private fun setupMoveAndResize(view: View) {
        var startX = 0
        var startY = 0
        var touchX = 0f
        var touchY = 0f
        var startW = 0
        var startH = 0

        val mover = View.OnTouchListener { v, e ->
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    startX = params.x; startY = params.y
                    touchX = e.rawX; touchY = e.rawY
                }
                MotionEvent.ACTION_MOVE -> {
                    params.x = startX + (e.rawX - touchX).roundToInt()
                    params.y = startY + (e.rawY - touchY).roundToInt()
                    clampToScreen()
                    updateLayout()
                }
                MotionEvent.ACTION_UP -> {
                    val tapped = abs(e.rawX - touchX) < dp(8) && abs(e.rawY - touchY) < dp(8)
                    if (v === bubble && tapped) expand() else savePlacement()
                }
            }
            true
        }
        view.findViewById<View>(R.id.header_bar).setOnTouchListener(mover)
        bubble.setOnTouchListener(mover)

        resizeHandle.setOnTouchListener { _, e ->
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    startW = params.width; startH = params.height
                    touchX = e.rawX; touchY = e.rawY
                }
                MotionEvent.ACTION_MOVE -> {
                    params.width = startW + (e.rawX - touchX).roundToInt()
                    params.height = startH + (e.rawY - touchY).roundToInt()
                    clampToScreen()
                    updateLayout()
                }
                MotionEvent.ACTION_UP -> savePlacement()
            }
            true
        }
    }

    private fun minimize() {
        if (minimized) return
        controller?.menu?.dismiss()
        minimized = true
        expandedW = params.width
        expandedH = params.height
        windowContainer.visibility = View.GONE
        resizeHandle.visibility = View.GONE
        bubble.visibility = View.VISIBLE
        params.width = dp(64)
        params.height = dp(64)
        updateLayout()
    }

    private fun restoreAfterPicker() {
        if (minimizedForPicker) expand()
    }

    private fun expand() {
        minimizedForPicker = false
        if (!minimized) return
        minimized = false
        bubble.visibility = View.GONE
        windowContainer.visibility = View.VISIBLE
        resizeHandle.visibility = View.VISIBLE
        params.width = expandedW
        params.height = expandedH
        clampToScreen()
        updateLayout()
    }

    private fun cycleOpacity() {
        val i = OPACITY_STEPS.indexOfFirst { abs(it - params.alpha) < 0.01f }
        params.alpha = OPACITY_STEPS[(i + 1) % OPACITY_STEPS.size]
        updateLayout()
        prefs.edit().putFloat("alpha", params.alpha).apply()
    }

    private fun screenSize(): Pair<Int, Int> {
        if (Build.VERSION.SDK_INT >= 30 && ::wm.isInitialized) {
            val b = wm.currentWindowMetrics.bounds
            return b.width() to b.height()
        }
        val dm = resources.displayMetrics
        return dm.widthPixels to dm.heightPixels
    }

    /** Keeps the window a sensible size and always reachable on screen. */
    private fun clampToScreen() {
        val (sw, sh) = screenSize()
        if (!minimized) {
            params.width = params.width.coerceIn(dp(340).coerceAtMost(sw), sw)
            params.height = params.height.coerceIn(dp(240), sh)
        }
        val keep = dp(64)
        params.x = params.x.coerceIn(-(params.width - keep), sw - keep)
        params.y = params.y.coerceIn(0, (sh - keep).coerceAtLeast(0))
    }

    private fun updateLayout() {
        val v = overlayView ?: return
        try {
            wm.updateViewLayout(v, params)
        } catch (_: Exception) {
        }
    }

    private fun savePlacement() {
        val e = prefs.edit().putInt("x", params.x).putInt("y", params.y)
        if (!minimized) e.putInt("w", params.width).putInt("h", params.height)
        e.apply()
    }

    // ---------------------------------------------------------------- BoardController.Host

    override fun pickImages(target: Importer.Target) = launchPicker(PickerActivity.PICK_IMAGES, target)

    override fun pickPdf(target: Importer.Target) = launchPicker(PickerActivity.PICK_PDF, target)

    private fun launchPicker(action: String, target: Importer.Target) {
        try {
            startActivity(
                Intent(this, PickerActivity::class.java)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    .putExtra(PickerActivity.EXTRA_ACTION, action)
                    .putExtra(PickerActivity.EXTRA_TARGET, target.name)
            )
            // Floating windows sit above every app, including the picker; shrink to the bubble meanwhile.
            if (!minimized) {
                minimize()
                minimizedForPicker = true
            }
        } catch (e: Exception) {
            Log.w("RefPad", "Could not open picker", e)
            toast("Could not open the file picker")
        }
    }

    override fun extraMenuItems(): List<MenuCard.Item> = listOf(
        MenuCard.Item("Window opacity  ${(params.alpha * 100).roundToInt()}%", R.drawable.ic_opacity) { cycleOpacity() },
        MenuCard.Item("Open full screen", R.drawable.ic_open_full) { openFullApp() },
        MenuCard.Item("Close floating window", R.drawable.ic_close) { stopSelf() }
    )

    private fun openFullApp() {
        try {
            startActivity(mainAppIntent().addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT))
            stopSelf()
        } catch (e: Exception) {
            toast("Could not open RefPad")
        }
    }

    override fun toast(text: String) = Toast.makeText(this, text, Toast.LENGTH_SHORT).show()

    /** Opens the full app. Matches the launcher filter, as Android 15+ requires for intents to it. */
    private fun mainAppIntent() = Intent(this, MainActivity::class.java)
        .setAction(Intent.ACTION_MAIN)
        .addCategory(Intent.CATEGORY_LAUNCHER)
        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

    // ---------------------------------------------------------------- Notification

    private fun startInForeground(): Boolean = try {
        val nm = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= 26) {
            nm?.createNotificationChannel(
                NotificationChannel(CHANNEL_ID, "Floating window", NotificationManager.IMPORTANCE_LOW).apply { setShowBadge(false) }
            )
        }
        val flags = PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        val open = PendingIntent.getActivity(this, 0, mainAppIntent(), flags)
        val stop = PendingIntent.getService(this, 1, Intent(this, FloatingOverlayService::class.java).setAction(ACTION_STOP), flags)
        @Suppress("DEPRECATION")
        val builder = if (Build.VERSION.SDK_INT >= 26) Notification.Builder(this, CHANNEL_ID) else Notification.Builder(this)
        val notification = builder
            .setContentTitle("RefPad is floating")
            .setContentText("Tap to open the full board")
            .setSmallIcon(R.drawable.ic_stat_refpad)
            .setContentIntent(open)
            .setOngoing(true)
            .addAction(Notification.Action.Builder(Icon.createWithResource(this, R.drawable.ic_close), "Close", stop).build())
            .build()
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
        true
    } catch (e: Exception) {
        Log.e("RefPad", "Could not start foreground service", e)
        false
    }

    private fun dp(v: Int) = (v * density).roundToInt()
}
