package com.refpad.app

import android.app.AlertDialog
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.PixelFormat
import android.os.Build
import android.os.CountDownTimer
import android.os.IBinder
import android.view.Gravity
import android.view.LayoutInflater
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.TextView

class FloatingOverlayService : Service() {

    private lateinit var windowManager: WindowManager
    private lateinit var overlayView: View
    private lateinit var params: WindowManager.LayoutParams

    private lateinit var windowContainer: View
    private lateinit var minimizedBubble: View
    private lateinit var refCanvas: RefCanvasView
    private lateinit var hudCard: View
    private lateinit var tvCountdown: TextView
    private lateinit var tvBadge: TextView
    private lateinit var tvPoseCounter: TextView

    private lateinit var btnModeToggle: Button
    private lateinit var btnPlayPause: Button
    private lateinit var btnInterval: Button
    private lateinit var refControls: View
    private lateinit var practiceControls: View

    private var initialX = 0
    private var initialY = 0
    private var initialTouchX = 0f
    private var initialTouchY = 0f

    private var savedWidth = 800
    private var savedHeight = 1000

    // Practice Timer State
    private val intervals = intArrayOf(30, 60, 120, 300)
    private val intervalLabels = arrayOf("30s", "1m", "2m", "5m")
    private var currentIntervalIndex = 2 // default 120s (2m)
    private var durationSeconds = 120
    private var timeRemainingSeconds = 120
    private var isPlaying = false
    private var timer: CountDownTimer? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        windowManager = getSystemService(Context.WINDOW_SERVICE) as WindowManager

        val layoutFlag = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        } else {
            @Suppress("DEPRECATION")
            WindowManager.LayoutParams.TYPE_PHONE
        }

        params = WindowManager.LayoutParams(
            savedWidth,
            savedHeight,
            layoutFlag,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = 80
            y = 120
        }

        val inflater = getSystemService(Context.LAYOUT_INFLATER_SERVICE) as LayoutInflater
        overlayView = inflater.inflate(R.layout.floating_overlay, null)

        initViews()
        setupDragAndResize()
        setupListeners()
        setupLongPressMenus()
        setupDataManagerSync()

        windowManager.addView(overlayView, params)
        startForegroundNotification()
    }

    private fun initViews() {
        windowContainer = overlayView.findViewById(R.id.window_container)
        minimizedBubble = overlayView.findViewById(R.id.minimized_bubble)
        refCanvas = overlayView.findViewById(R.id.ref_canvas)
        hudCard = overlayView.findViewById(R.id.hud_card)
        tvCountdown = overlayView.findViewById(R.id.tv_countdown)
        tvBadge = overlayView.findViewById(R.id.tv_badge)
        tvPoseCounter = overlayView.findViewById(R.id.tv_pose_counter)

        btnModeToggle = overlayView.findViewById(R.id.btn_mode_toggle)
        btnPlayPause = overlayView.findViewById(R.id.btn_play_pause)
        btnInterval = overlayView.findViewById(R.id.btn_interval)
        refControls = overlayView.findViewById(R.id.ref_controls)
        practiceControls = overlayView.findViewById(R.id.practice_controls)

        refCanvas.onPoseChanged = { current, total ->
            tvPoseCounter.text = "Pose $current/$total"
        }
    }

    private fun setupDragAndResize() {
        val header = overlayView.findViewById<View>(R.id.header_bar)
        header.setOnTouchListener { _, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    initialX = params.x
                    initialY = params.y
                    initialTouchX = event.rawX
                    initialTouchY = event.rawY
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    params.x = initialX + (event.rawX - initialTouchX).toInt()
                    params.y = initialY + (event.rawY - initialTouchY).toInt()
                    windowManager.updateViewLayout(overlayView, params)
                    true
                }
                else -> false
            }
        }

        minimizedBubble.setOnTouchListener { _, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    initialX = params.x
                    initialY = params.y
                    initialTouchX = event.rawX
                    initialTouchY = event.rawY
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    params.x = initialX + (event.rawX - initialTouchX).toInt()
                    params.y = initialY + (event.rawY - initialTouchY).toInt()
                    windowManager.updateViewLayout(overlayView, params)
                    true
                }
                MotionEvent.ACTION_UP -> {
                    if (Math.abs(event.rawX - initialTouchX) < 15 && Math.abs(event.rawY - initialTouchY) < 15) {
                        expandWindow()
                    }
                    true
                }
                else -> false
            }
        }

        val resizeHandle = overlayView.findViewById<View>(R.id.resize_handle)
        var startW = 0
        var startH = 0
        resizeHandle.setOnTouchListener { _, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    startW = params.width
                    startH = params.height
                    initialTouchX = event.rawX
                    initialTouchY = event.rawY
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    val newW = startW + (event.rawX - initialTouchX).toInt()
                    val newH = startH + (event.rawY - initialTouchY).toInt()
                    if (newW > 350 && newH > 350) {
                        params.width = newW
                        params.height = newH
                        savedWidth = newW
                        savedHeight = newH
                        windowManager.updateViewLayout(overlayView, params)
                    }
                    true
                }
                else -> false
            }
        }
    }

    private fun setupListeners() {
        overlayView.findViewById<View>(R.id.btn_close).setOnClickListener {
            stopSelf()
        }

        overlayView.findViewById<View>(R.id.btn_minimize).setOnClickListener {
            minimizeWindow()
        }

        btnModeToggle.setOnClickListener {
            if (refCanvas.currentMode == RefCanvasView.MODE_REFERENCE) {
                switchToPracticeMode()
            } else {
                switchToReferenceMode()
            }
        }

        // Reference Mode Toolbar
        overlayView.findViewById<View>(R.id.btn_pdf_ref).setOnClickListener {
            val intent = Intent(this, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP
                putExtra("action", "pick_pdf_ref")
            }
            startActivity(intent)
        }

        overlayView.findViewById<View>(R.id.btn_add_ref).setOnClickListener {
            val intent = Intent(this, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP
                putExtra("action", "pick_image")
            }
            startActivity(intent)
        }

        overlayView.findViewById<View>(R.id.btn_flip_ref).setOnClickListener {
            refCanvas.flipSelected()
        }

        overlayView.findViewById<View>(R.id.btn_bw_ref).setOnClickListener {
            refCanvas.toggleGrayscaleSelected()
        }

        overlayView.findViewById<View>(R.id.btn_reset_ref).setOnClickListener {
            refCanvas.resetCanvasTransform()
        }

        overlayView.findViewById<View>(R.id.btn_del_ref).setOnClickListener {
            refCanvas.deleteSelected()
        }

        // Practice Mode Toolbar
        btnInterval.setOnClickListener {
            currentIntervalIndex = (currentIntervalIndex + 1) % intervals.size
            durationSeconds = intervals[currentIntervalIndex]
            timeRemainingSeconds = durationSeconds
            btnInterval.text = intervalLabels[currentIntervalIndex]
            tvBadge.text = "${intervalLabels[currentIntervalIndex].uppercase()} POSE"
            updateTimerDisplay()
            if (isPlaying) {
                startTimer(durationSeconds)
            }
        }

        overlayView.findViewById<View>(R.id.btn_pdf_practice).setOnClickListener {
            val intent = Intent(this, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP
                putExtra("action", "pick_pdf_practice")
            }
            startActivity(intent)
        }

        btnPlayPause.setOnClickListener {
            togglePlayPause()
        }

        overlayView.findViewById<View>(R.id.btn_next_pose).setOnClickListener {
            refCanvas.nextPracticePose()
            if (isPlaying) startTimer(durationSeconds)
        }

        overlayView.findViewById<View>(R.id.btn_prev_pose).setOnClickListener {
            refCanvas.prevPracticePose()
            if (isPlaying) startTimer(durationSeconds)
        }

        overlayView.findViewById<View>(R.id.btn_flip_practice).setOnClickListener {
            refCanvas.flipPracticePose()
        }

        overlayView.findViewById<View>(R.id.btn_bw_practice).setOnClickListener {
            refCanvas.toggleGrayscalePracticePose()
        }
    }

    private fun setupLongPressMenus() {
        refCanvas.onItemLongPressed = { item, _, _ ->
            showOverlayItemDialog(item)
        }

        refCanvas.onCanvasLongPressed = { _, _ ->
            showOverlayCanvasDialog()
        }
    }

    private fun showOverlayItemDialog(item: RefBoardItem) {
        val options = arrayOf(
            "Flip Horizontal",
            "Rotate 90 CW",
            "Rotate 90 CCW",
            "Toggle Grayscale (B&W)",
            "Send to Practice Mode",
            "Reset Transforms",
            "Delete Reference"
        )
        val dialog = AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog_Alert)
            .setTitle("Reference Operations")
            .setItems(options) { _, which ->
                when (which) {
                    0 -> refCanvas.flipSelected()
                    1 -> refCanvas.rotateSelectedCW()
                    2 -> refCanvas.rotateSelectedCCW()
                    3 -> refCanvas.toggleGrayscaleSelected()
                    4 -> {
                        refCanvas.practiceItems.add(item.bitmap)
                        DataManager.addPracticeImages(listOf(item.bitmap))
                        switchToPracticeMode()
                    }
                    5 -> refCanvas.resetSelectedTransforms()
                    6 -> refCanvas.deleteSelected()
                }
            }
            .setNegativeButton("Cancel", null)
            .create()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            dialog.window?.setType(WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY)
        } else {
            @Suppress("DEPRECATION")
            dialog.window?.setType(WindowManager.LayoutParams.TYPE_SYSTEM_ALERT)
        }
        dialog.show()
    }

    private fun showOverlayCanvasDialog() {
        val options = arrayOf(
            "Import PDF Reference",
            "Import Image(s)",
            "Auto Arrange References",
            "Switch to Practice Mode",
            "Clear Canvas"
        )
        val dialog = AlertDialog.Builder(this, android.R.style.Theme_DeviceDefault_Dialog_Alert)
            .setTitle("Reference Board")
            .setItems(options) { _, which ->
                when (which) {
                    0 -> {
                        val intent = Intent(this, MainActivity::class.java).apply {
                            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP
                            putExtra("action", "pick_pdf_ref")
                        }
                        startActivity(intent)
                    }
                    1 -> {
                        val intent = Intent(this, MainActivity::class.java).apply {
                            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP
                            putExtra("action", "pick_image")
                        }
                        startActivity(intent)
                    }
                    2 -> refCanvas.autoArrange()
                    3 -> switchToPracticeMode()
                    4 -> {
                        refCanvas.clearAll()
                        DataManager.referenceImages.clear()
                    }
                }
            }
            .setNegativeButton("Cancel", null)
            .create()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            dialog.window?.setType(WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY)
        } else {
            @Suppress("DEPRECATION")
            dialog.window?.setType(WindowManager.LayoutParams.TYPE_SYSTEM_ALERT)
        }
        dialog.show()
    }

    private fun switchToReferenceMode() {
        refCanvas.currentMode = RefCanvasView.MODE_REFERENCE
        btnModeToggle.text = "Ref Board"
        refControls.visibility = View.VISIBLE
        practiceControls.visibility = View.GONE
        hudCard.visibility = View.GONE
        pauseTimer()
    }

    private fun switchToPracticeMode() {
        if (refCanvas.practiceItems.isEmpty() && refCanvas.items.isNotEmpty()) {
            val bitmaps = refCanvas.items.map { it.bitmap }
            refCanvas.setPracticeList(bitmaps)
            DataManager.addPracticeImages(bitmaps)
        }
        refCanvas.currentMode = RefCanvasView.MODE_PRACTICE
        btnModeToggle.text = "Practice"
        refControls.visibility = View.GONE
        practiceControls.visibility = View.VISIBLE
        hudCard.visibility = View.VISIBLE
        updateTimerDisplay()
    }

    private fun minimizeWindow() {
        savedWidth = params.width
        savedHeight = params.height
        windowContainer.visibility = View.GONE
        minimizedBubble.visibility = View.VISIBLE

        params.width = 160
        params.height = 160
        windowManager.updateViewLayout(overlayView, params)
    }

    private fun expandWindow() {
        minimizedBubble.visibility = View.GONE
        windowContainer.visibility = View.VISIBLE

        params.width = savedWidth
        params.height = savedHeight
        windowManager.updateViewLayout(overlayView, params)
    }

    private fun togglePlayPause() {
        if (isPlaying) {
            pauseTimer()
        } else {
            playTimer()
        }
    }

    private fun playTimer() {
        isPlaying = true
        btnPlayPause.text = "Pause"
        startTimer(timeRemainingSeconds)
    }

    private fun pauseTimer() {
        isPlaying = false
        timer?.cancel()
        btnPlayPause.text = "Play"
    }

    private fun startTimer(seconds: Int) {
        timer?.cancel()
        timeRemainingSeconds = seconds
        timer = object : CountDownTimer((timeRemainingSeconds * 1000).toLong(), 1000) {
            override fun onTick(millisUntilFinished: Long) {
                timeRemainingSeconds = (millisUntilFinished / 1000).toInt()
                updateTimerDisplay()
            }

            override fun onFinish() {
                refCanvas.nextPracticePose()
                timeRemainingSeconds = durationSeconds
                startTimer(durationSeconds)
            }
        }.start()
    }

    private fun updateTimerDisplay() {
        val mins = timeRemainingSeconds / 60
        val secs = timeRemainingSeconds % 60
        tvCountdown.text = String.format("%02d:%02d", mins, secs)
    }

    private fun setupDataManagerSync() {
        for (bmp in DataManager.referenceImages) {
            refCanvas.addReferenceItem(bmp)
        }
        if (DataManager.practiceImages.isNotEmpty()) {
            refCanvas.setPracticeList(DataManager.practiceImages)
        }

        DataManager.onNewReferenceAdded = { bmp ->
            refCanvas.addReferenceItem(bmp)
        }
        DataManager.onPracticeImagesUpdated = {
            refCanvas.setPracticeList(DataManager.practiceImages)
        }
    }

    private fun startForegroundNotification() {
        val channelId = "refpad_floating_service"
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                channelId,
                "Reference Board Overlay",
                NotificationManager.IMPORTANCE_LOW
            )
            val manager = getSystemService(NotificationManager::class.java)
            manager?.createNotificationChannel(channel)
        }

        val notification = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, channelId)
                .setContentTitle("Reference Board Active")
                .setContentText("Floating companion over drawing apps")
                .setSmallIcon(android.R.drawable.ic_menu_gallery)
                .build()
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
                .setContentTitle("Reference Board Active")
                .setContentText("Floating companion over drawing apps")
                .setSmallIcon(android.R.drawable.ic_menu_gallery)
                .build()
        }

        startForeground(1001, notification)
    }

    override fun onDestroy() {
        super.onDestroy()
        timer?.cancel()
        DataManager.onNewReferenceAdded = null
        DataManager.onPracticeImagesUpdated = null
        if (::overlayView.isInitialized) {
            windowManager.removeView(overlayView)
        }
    }
}
