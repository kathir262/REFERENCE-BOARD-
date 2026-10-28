package com.refpad.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.graphics.BitmapFactory
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
import android.widget.Toast

class FloatingOverlayService : Service() {

    private lateinit var windowManager: WindowManager
    private lateinit var overlayView: View
    private lateinit var params: WindowManager.LayoutParams

    private lateinit var windowContainer: View
    private lateinit var minimizedBubble: View
    private lateinit var refCanvas: RefCanvasView
    private lateinit var contentArea: View
    private lateinit var hudCard: View
    private lateinit var tvCountdown: TextView
    private lateinit var tvBadge: TextView
    private lateinit var tvPoseCounter: TextView

    private lateinit var btnModeToggle: Button
    private lateinit var btnPlayPause: Button
    private lateinit var btnInterval: Button
    private lateinit var dockRefScroll: View
    private lateinit var dockPracticeScroll: View
    private lateinit var btnCopyRef: Button
    private lateinit var btnPasteRef: Button

    // In-Window Compact Menu Views
    private lateinit var menuCard: View
    private lateinit var tvMenuTitle: TextView
    private lateinit var btnMenuClose: View
    private lateinit var btnMenuCopy: Button
    private lateinit var btnMenuPaste: Button
    private lateinit var btnMenuPdf: Button
    private lateinit var btnMenuImg: Button
    private lateinit var btnMenuFlip: Button
    private lateinit var btnMenuRotate: Button
    private lateinit var btnMenuBw: Button
    private lateinit var btnMenuPractice: Button
    private lateinit var btnMenuArrange: Button
    private lateinit var btnMenuReset: Button
    private lateinit var btnMenuDel: Button
    private lateinit var btnMenuClear: Button

    private var lastTouchCanvasX: Float? = null
    private var lastTouchCanvasY: Float? = null

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
        contentArea = overlayView.findViewById(R.id.content_area)
        refCanvas = overlayView.findViewById(R.id.ref_canvas)
        hudCard = overlayView.findViewById(R.id.hud_card)
        tvCountdown = overlayView.findViewById(R.id.tv_countdown)
        tvBadge = overlayView.findViewById(R.id.tv_badge)
        tvPoseCounter = overlayView.findViewById(R.id.tv_pose_counter)

        btnModeToggle = overlayView.findViewById(R.id.btn_mode_toggle)
        btnPlayPause = overlayView.findViewById(R.id.btn_play_pause)
        btnInterval = overlayView.findViewById(R.id.btn_interval)
        dockRefScroll = overlayView.findViewById(R.id.dock_ref_scroll)
        dockPracticeScroll = overlayView.findViewById(R.id.dock_practice_scroll)
        btnCopyRef = overlayView.findViewById(R.id.btn_copy_ref)
        btnPasteRef = overlayView.findViewById(R.id.btn_paste_ref)

        // In-Window Menu Views
        menuCard = overlayView.findViewById(R.id.menu_card)
        tvMenuTitle = overlayView.findViewById(R.id.tv_menu_title)
        btnMenuClose = overlayView.findViewById(R.id.btn_menu_close)
        btnMenuCopy = overlayView.findViewById(R.id.btn_menu_copy)
        btnMenuPaste = overlayView.findViewById(R.id.btn_menu_paste)
        btnMenuPdf = overlayView.findViewById(R.id.btn_menu_pdf)
        btnMenuImg = overlayView.findViewById(R.id.btn_menu_img)
        btnMenuFlip = overlayView.findViewById(R.id.btn_menu_flip)
        btnMenuRotate = overlayView.findViewById(R.id.btn_menu_rotate)
        btnMenuBw = overlayView.findViewById(R.id.btn_menu_bw)
        btnMenuPractice = overlayView.findViewById(R.id.btn_menu_practice)
        btnMenuArrange = overlayView.findViewById(R.id.btn_menu_arrange)
        btnMenuReset = overlayView.findViewById(R.id.btn_menu_reset)
        btnMenuDel = overlayView.findViewById(R.id.btn_menu_del)
        btnMenuClear = overlayView.findViewById(R.id.btn_menu_clear)

        refCanvas.onPoseChanged = { current, total ->
            tvPoseCounter.text = "Pose $current/$total"
        }

        refCanvas.onCanvasTapped = {
            hideMenu()
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
                    if (newW > 320 && newH > 320) {
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

        overlayView.findViewById<View>(R.id.btn_floating_menu).setOnClickListener {
            if (menuCard.visibility == View.VISIBLE) {
                hideMenu()
            } else {
                val sel = refCanvas.selectedItem
                if (sel != null) {
                    showOverlayItemMenu(sel, contentArea.width / 2f, contentArea.height / 2f, sel.x, sel.y)
                } else {
                    showOverlayCanvasMenu(contentArea.width / 2f, contentArea.height / 2f)
                }
            }
        }

        btnModeToggle.setOnClickListener {
            if (refCanvas.currentMode == RefCanvasView.MODE_REFERENCE) {
                switchToPracticeMode()
            } else {
                switchToReferenceMode()
            }
        }

        // Reference Mode Bottom Dock
        overlayView.findViewById<View>(R.id.btn_pdf_ref).setOnClickListener {
            launchPicker("pick_pdf_ref")
        }

        overlayView.findViewById<View>(R.id.btn_add_ref).setOnClickListener {
            launchPicker("pick_image")
        }

        btnCopyRef.setOnClickListener {
            copyAction()
        }

        btnPasteRef.setOnClickListener {
            pasteAction()
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
            launchPicker("pick_pdf_practice")
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

        // Menu Card Internal Buttons
        btnMenuClose.setOnClickListener {
            hideMenu()
        }

        btnMenuCopy.setOnClickListener {
            copyAction()
        }

        btnMenuPaste.setOnClickListener {
            pasteAction()
        }

        btnMenuPdf.setOnClickListener {
            hideMenu()
            launchPicker("pick_pdf_ref")
        }

        btnMenuImg.setOnClickListener {
            hideMenu()
            launchPicker("pick_image")
        }

        btnMenuFlip.setOnClickListener {
            hideMenu()
            refCanvas.flipSelected()
        }

        btnMenuRotate.setOnClickListener {
            hideMenu()
            refCanvas.rotateSelectedCW()
        }

        btnMenuBw.setOnClickListener {
            hideMenu()
            refCanvas.toggleGrayscaleSelected()
        }

        btnMenuPractice.setOnClickListener {
            hideMenu()
            refCanvas.selectedItem?.let { sel ->
                refCanvas.practiceItems.add(sel.bitmap)
                DataManager.addPracticeImages(listOf(sel.bitmap))
            }
            switchToPracticeMode()
        }

        btnMenuArrange.setOnClickListener {
            hideMenu()
            refCanvas.autoArrange()
        }

        btnMenuReset.setOnClickListener {
            hideMenu()
            if (refCanvas.selectedItem != null) {
                refCanvas.resetSelectedTransforms()
            } else {
                refCanvas.resetCanvasTransform()
            }
        }

        btnMenuDel.setOnClickListener {
            hideMenu()
            refCanvas.deleteSelected()
        }

        btnMenuClear.setOnClickListener {
            hideMenu()
            refCanvas.clearAll()
            DataManager.referenceImages.clear()
        }
    }

    private fun launchPicker(action: String) {
        val intent = Intent(this, PickerActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK
            putExtra("action", action)
        }
        startActivity(intent)
    }

    private fun copyAction() {
        hideMenu()
        val copied = refCanvas.copySelected()
        if (copied) {
            Toast.makeText(this, "Reference copied", Toast.LENGTH_SHORT).show()
        } else {
            Toast.makeText(this, "Select a reference first", Toast.LENGTH_SHORT).show()
        }
    }

    private fun pasteAction() {
        hideMenu()
        if (DataManager.copiedBitmap == null) {
            tryReadSystemClipboardImage()
        }

        val pasted = refCanvas.pasteCopied(lastTouchCanvasX, lastTouchCanvasY)
        if (pasted) {
            DataManager.copiedBitmap?.let { DataManager.referenceImages.add(it) }
            Toast.makeText(this, "Reference pasted", Toast.LENGTH_SHORT).show()
        } else {
            Toast.makeText(this, "Clipboard empty - copy an image first", Toast.LENGTH_SHORT).show()
        }
    }

    private fun tryReadSystemClipboardImage() {
        try {
            val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager
            if (clipboard != null && clipboard.hasPrimaryClip()) {
                val clip = clipboard.primaryClip
                if (clip != null && clip.itemCount > 0) {
                    val uri = clip.getItemAt(0).uri
                    if (uri != null) {
                        contentResolver.openInputStream(uri)?.use { stream ->
                            val bmp = BitmapFactory.decodeStream(stream)
                            if (bmp != null) {
                                DataManager.copiedBitmap = bmp
                            }
                        }
                    }
                }
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    private fun setupLongPressMenus() {
        refCanvas.onItemLongPressed = { item, touchX, touchY, canvasX, canvasY ->
            showOverlayItemMenu(item, touchX, touchY, canvasX, canvasY)
        }

        refCanvas.onCanvasLongPressed = { touchX, touchY, canvasX, canvasY ->
            showOverlayCanvasMenu(touchX, touchY, canvasX, canvasY)
        }
    }

    private fun showOverlayItemMenu(item: RefBoardItem, touchX: Float, touchY: Float, canvasX: Float, canvasY: Float) {
        lastTouchCanvasX = canvasX
        lastTouchCanvasY = canvasY

        tvMenuTitle.text = "REFERENCE"
        btnMenuCopy.visibility = View.VISIBLE
        btnMenuPaste.visibility = View.GONE
        btnMenuPdf.visibility = View.GONE
        btnMenuImg.visibility = View.GONE
        btnMenuFlip.visibility = View.VISIBLE
        btnMenuRotate.visibility = View.VISIBLE
        btnMenuBw.visibility = View.VISIBLE
        btnMenuPractice.visibility = View.VISIBLE
        btnMenuPractice.text = "Send to Practice"
        btnMenuArrange.visibility = View.GONE
        btnMenuReset.visibility = View.VISIBLE
        btnMenuReset.text = "Reset Transforms"
        btnMenuDel.visibility = View.VISIBLE
        btnMenuClear.visibility = View.GONE

        positionMenu(touchX, touchY)
        menuCard.visibility = View.VISIBLE
    }

    private fun showOverlayCanvasMenu(touchX: Float, touchY: Float, canvasX: Float? = null, canvasY: Float? = null) {
        lastTouchCanvasX = canvasX
        lastTouchCanvasY = canvasY

        tvMenuTitle.text = "REFERENCE BOARD"
        btnMenuCopy.visibility = View.GONE
        btnMenuPaste.visibility = View.VISIBLE
        if (DataManager.copiedBitmap != null) {
            btnMenuPaste.text = "Paste Reference"
            btnMenuPaste.alpha = 1.0f
        } else {
            btnMenuPaste.text = "Paste (Empty)"
            btnMenuPaste.alpha = 0.5f
        }
        btnMenuPdf.visibility = View.VISIBLE
        btnMenuImg.visibility = View.VISIBLE
        btnMenuFlip.visibility = View.GONE
        btnMenuRotate.visibility = View.GONE
        btnMenuBw.visibility = View.GONE
        btnMenuPractice.visibility = View.VISIBLE
        btnMenuPractice.text = "Switch to Practice"
        btnMenuArrange.visibility = View.VISIBLE
        btnMenuReset.visibility = View.VISIBLE
        btnMenuReset.text = "Reset Canvas"
        btnMenuDel.visibility = View.GONE
        btnMenuClear.visibility = View.VISIBLE

        positionMenu(touchX, touchY)
        menuCard.visibility = View.VISIBLE
    }

    private fun positionMenu(touchX: Float, touchY: Float) {
        menuCard.post {
            val parentW = contentArea.width
            val parentH = contentArea.height
            val density = resources.displayMetrics.density
            val menuW = menuCard.width.takeIf { it > 0 } ?: (165 * density).toInt()
            val menuH = menuCard.height.takeIf { it > 0 } ?: (200 * density).toInt()

            val maxX = (parentW - menuW - 10).toFloat().coerceAtLeast(10f)
            val maxY = (parentH - menuH - 10).toFloat().coerceAtLeast(10f)

            val targetX = (touchX - menuW / 2).coerceIn(10f, maxX)
            val targetY = (touchY - 20f).coerceIn(10f, maxY)

            menuCard.translationX = targetX
            menuCard.translationY = targetY
        }
    }

    private fun hideMenu() {
        if (::menuCard.isInitialized) {
            menuCard.visibility = View.GONE
        }
    }

    private fun switchToReferenceMode() {
        hideMenu()
        refCanvas.currentMode = RefCanvasView.MODE_REFERENCE
        btnModeToggle.text = "Ref Board"
        dockRefScroll.visibility = View.VISIBLE
        dockPracticeScroll.visibility = View.GONE
        hudCard.visibility = View.GONE
        pauseTimer()
    }

    private fun switchToPracticeMode() {
        hideMenu()
        if (refCanvas.practiceItems.isEmpty() && refCanvas.items.isNotEmpty()) {
            val bitmaps = refCanvas.items.map { it.bitmap }
            refCanvas.setPracticeList(bitmaps)
            DataManager.addPracticeImages(bitmaps)
        }
        refCanvas.currentMode = RefCanvasView.MODE_PRACTICE
        btnModeToggle.text = "Practice"
        dockRefScroll.visibility = View.GONE
        dockPracticeScroll.visibility = View.VISIBLE
        hudCard.visibility = View.VISIBLE
        updateTimerDisplay()
    }

    private fun minimizeWindow() {
        hideMenu()
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

    private val refAddedListener: (android.graphics.Bitmap) -> Unit = { bmp ->
        refCanvas.post {
            refCanvas.addReferenceItem(bmp)
        }
    }

    private val practiceUpdatedListener: () -> Unit = {
        refCanvas.post {
            refCanvas.setPracticeList(DataManager.practiceImages)
        }
    }

    private fun setupDataManagerSync() {
        for (bmp in DataManager.referenceImages) {
            refCanvas.addReferenceItem(bmp)
        }
        if (DataManager.practiceImages.isNotEmpty()) {
            refCanvas.setPracticeList(DataManager.practiceImages)
        }

        DataManager.addReferenceListener(refAddedListener)
        DataManager.addPracticeListener(practiceUpdatedListener)
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
        DataManager.removeReferenceListener(refAddedListener)
        DataManager.removePracticeListener(practiceUpdatedListener)
        if (::overlayView.isInitialized) {
            windowManager.removeView(overlayView)
        }
    }
}
