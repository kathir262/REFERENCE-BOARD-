package com.refpad.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.ColorMatrix
import android.graphics.ColorMatrixColorFilter
import android.graphics.Matrix
import android.graphics.PixelFormat
import android.os.Build
import android.os.CountDownTimer
import android.os.IBinder
import android.view.*
import android.widget.Button
import android.widget.ImageView
import android.widget.TextView

class FloatingOverlayService : Service() {

    private lateinit var windowManager: WindowManager
    private lateinit var overlayView: View
    private lateinit var params: WindowManager.LayoutParams

    private lateinit var ivPose: ImageView
    private lateinit var tvCountdown: TextView
    private lateinit var tvBadge: TextView
    private lateinit var tvPoseCounter: TextView
    private lateinit var btnPlayPause: Button

    private var initialX = 0
    private var initialY = 0
    private var initialTouchX = 0f
    private var initialTouchY = 0f

    // Session State
    private var isPaused = true
    private var durationSeconds = 120
    private var timeRemainingSeconds = 120
    private var timer: CountDownTimer? = null
    private var isFlipped = false
    private var isGrayscale = false

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
            800,
            1000,
            layoutFlag,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = 100
            y = 150
        }

        val inflater = getSystemService(Context.LAYOUT_INFLATER_SERVICE) as LayoutInflater
        overlayView = inflater.inflate(R.layout.floating_overlay, null)

        initViews()
        setupDragAndResize()
        setupTouchAndStylus()
        setupControls()

        windowManager.addView(overlayView, params)
        startForegroundNotification()
    }

    private fun initViews() {
        ivPose = overlayView.findViewById(R.id.iv_pose)
        tvCountdown = overlayView.findViewById(R.id.tv_countdown)
        tvBadge = overlayView.findViewById(R.id.tv_badge)
        tvPoseCounter = overlayView.findViewById(R.id.tv_pose_counter)
        btnPlayPause = overlayView.findViewById(R.id.btn_play_pause)
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

        // Corner Resize Handle
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
                    if (newW > 400 && newH > 400) {
                        params.width = newW
                        params.height = newH
                        windowManager.updateViewLayout(overlayView, params)
                    }
                    true
                }
                else -> false
            }
        }
    }

    private fun setupTouchAndStylus() {
        val scaleDetector = ScaleGestureDetector(this, object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
            override fun onScale(detector: ScaleGestureDetector): Boolean {
                val scale = detector.scaleFactor
                ivPose.scaleX = (ivPose.scaleX * scale).coerceIn(0.5f, 5.0f)
                ivPose.scaleY = (ivPose.scaleY * scale).coerceIn(0.5f, 5.0f)
                return true
            }
        })

        val canvas = overlayView.findViewById<View>(R.id.canvas_container)
        canvas.setOnTouchListener { _, event ->
            scaleDetector.onTouchEvent(event)

            // S-Pen stylus button check
            val isStylus = event.getToolType(0) == MotionEvent.TOOL_TYPE_STYLUS
            if (isStylus && (event.buttonState and MotionEvent.BUTTON_STYLUS_PRIMARY != 0)) {
                // S-Pen button tap toggles pause/play
                togglePause()
                return@setOnTouchListener true
            }
            true
        }
    }

    private fun setupControls() {
        overlayView.findViewById<View>(R.id.btn_close).setOnClickListener {
            stopSelf()
        }

        btnPlayPause.setOnClickListener {
            togglePause()
        }

        overlayView.findViewById<View>(R.id.btn_flip).setOnClickListener {
            isFlipped = !isFlipped
            ivPose.scaleX = if (isFlipped) -Math.abs(ivPose.scaleX) else Math.abs(ivPose.scaleX)
        }

        overlayView.findViewById<View>(R.id.btn_grayscale).setOnClickListener {
            isGrayscale = !isGrayscale
            if (isGrayscale) {
                val matrix = ColorMatrix().apply { setSaturation(0f) }
                ivPose.colorFilter = ColorMatrixColorFilter(matrix)
            } else {
                ivPose.clearColorFilter()
            }
        }
    }

    private fun togglePause() {
        isPaused = !isPaused
        if (isPaused) {
            timer?.cancel()
            btnPlayPause.text = "▶ Play"
        } else {
            startTimer(timeRemainingSeconds)
            btnPlayPause.text = "⏸ Pause"
        }
    }

    private fun startTimer(seconds: Int) {
        timer?.cancel()
        timer = object : CountDownTimer((seconds * 1000).toLong(), 1000) {
            override fun onTick(millisUntilFinished: Long) {
                timeRemainingSeconds = (millisUntilFinished / 1000).toInt()
                val mins = timeRemainingSeconds / 60
                val secs = timeRemainingSeconds % 60
                tvCountdown.text = String.format("%d:%02d", mins, secs)
            }

            override fun onFinish() {
                // Pose complete -> Next pose
                timeRemainingSeconds = durationSeconds
                startTimer(durationSeconds)
            }
        }.start()
    }

    private fun startForegroundNotification() {
        val channelId = "refpad_floating"
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                channelId,
                "RefPad Floating Service",
                NotificationManager.IMPORTANCE_LOW
            )
            val manager = getSystemService(NotificationManager::class.java)
            manager?.createNotificationChannel(channel)
        }

        val notification = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, channelId)
                .setContentTitle("RefPad Floating Active")
                .setContentText("Hovering over drawing app")
                .setSmallIcon(android.R.drawable.ic_menu_gallery)
                .build()
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
                .setContentTitle("RefPad Floating Active")
                .setContentText("Hovering over drawing app")
                .setSmallIcon(android.R.drawable.ic_menu_gallery)
                .build()
        }

        startForeground(1001, notification)
    }

    override fun onDestroy() {
        super.onDestroy()
        timer?.cancel()
        if (::overlayView.isInitialized) {
            windowManager.removeView(overlayView)
        }
    }
}
