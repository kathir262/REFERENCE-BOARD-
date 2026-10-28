package com.refpad.app

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.CountDownTimer
import android.provider.DocumentsContract
import android.provider.Settings
import android.view.View
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import java.io.InputStream

class MainActivity : Activity() {

    private val OVERLAY_PERMISSION_REQ_CODE = 1234
    private val PICK_IMAGES_REQ_CODE = 2345
    private val PICK_PDF_REQ_CODE = 3456
    private val PICK_FOLDER_REQ_CODE = 4567

    private lateinit var refCanvas: RefCanvasView
    private lateinit var emptyStateView: View
    private lateinit var hudCard: View
    private lateinit var tvCountdown: TextView
    private lateinit var tvBadge: TextView
    private lateinit var tvPoseCounter: TextView

    private lateinit var btnModeToggle: Button
    private lateinit var dockRefControls: View
    private lateinit var dockPracticeControls: View
    private lateinit var dockRefScroll: View
    private lateinit var dockPracticeScroll: View
    private lateinit var btnDockPlayPause: Button
    private lateinit var btnDockInterval: Button

    private var pendingTargetMode = 0 // 0: Reference Board, 1: Practice Mode

    // Practice Countdown State
    private val intervals = intArrayOf(30, 60, 120, 300)
    private val intervalLabels = arrayOf("30s", "1m", "2m", "5m")
    private var currentIntervalIndex = 2 // default 120s (2m)
    private var durationSeconds = 120
    private var timeRemainingSeconds = 120
    private var isPlaying = false
    private var timer: CountDownTimer? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        initViews()
        setupListeners()
        setupPracticeHUD()
        setupLongPressMenus()
        syncWithDataManager()

        handleIncomingIntent(intent)
    }

    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        intent?.let { handleIncomingIntent(it) }
    }

    private fun initViews() {
        refCanvas = findViewById(R.id.ref_canvas)
        emptyStateView = findViewById(R.id.empty_state_view)
        hudCard = findViewById(R.id.hud_card)
        tvCountdown = findViewById(R.id.tv_countdown)
        tvBadge = findViewById(R.id.tv_badge)
        tvPoseCounter = findViewById(R.id.tv_pose_counter)

        btnModeToggle = findViewById(R.id.btn_mode_toggle)
        dockRefControls = findViewById(R.id.dock_ref_controls)
        dockPracticeControls = findViewById(R.id.dock_practice_controls)
        dockRefScroll = findViewById(R.id.dock_ref_scroll)
        dockPracticeScroll = findViewById(R.id.dock_practice_scroll)
        btnDockPlayPause = findViewById(R.id.btn_dock_play_pause)
        btnDockInterval = findViewById(R.id.btn_dock_interval)

        refCanvas.onItemsCountChanged = { count ->
            emptyStateView.visibility = if (count == 0 && refCanvas.practiceItems.isEmpty()) View.VISIBLE else View.GONE
        }
    }

    private fun setupListeners() {
        // Top Bar
        findViewById<Button>(R.id.btn_top_pdf).setOnClickListener {
            promptDestinationDialog { targetMode ->
                openPdfPicker(targetMode)
            }
        }

        findViewById<Button>(R.id.btn_float_overlay).setOnClickListener {
            checkOverlayPermissionAndLaunch()
        }

        findViewById<Button>(R.id.btn_top_menu).setOnClickListener {
            showMainMenu()
        }

        btnModeToggle.setOnClickListener {
            if (refCanvas.currentMode == RefCanvasView.MODE_REFERENCE) {
                switchToPracticeMode()
            } else {
                switchToReferenceMode()
            }
        }

        // Empty State Buttons
        findViewById<Button>(R.id.btn_empty_sample).setOnClickListener {
            loadSampleReferences()
        }

        findViewById<Button>(R.id.btn_empty_pdf).setOnClickListener {
            promptDestinationDialog { targetMode ->
                openPdfPicker(targetMode)
            }
        }

        findViewById<Button>(R.id.btn_empty_images).setOnClickListener {
            openImagePicker(0)
        }

        findViewById<Button>(R.id.btn_empty_folder).setOnClickListener {
            openFolderPicker(0)
        }

        // Bottom Dock - Reference Mode
        findViewById<Button>(R.id.btn_dock_menu).setOnClickListener {
            showMainMenu()
        }

        findViewById<Button>(R.id.btn_dock_pdf).setOnClickListener {
            promptDestinationDialog { targetMode ->
                openPdfPicker(targetMode)
            }
        }

        findViewById<Button>(R.id.btn_dock_add).setOnClickListener {
            promptDestinationDialog { targetMode ->
                openImagePicker(targetMode)
            }
        }

        findViewById<Button>(R.id.btn_dock_flip).setOnClickListener {
            refCanvas.flipSelected()
        }

        findViewById<Button>(R.id.btn_dock_bw).setOnClickListener {
            refCanvas.toggleGrayscaleSelected()
        }

        findViewById<Button>(R.id.btn_dock_reset).setOnClickListener {
            refCanvas.resetCanvasTransform()
        }

        findViewById<Button>(R.id.btn_dock_del).setOnClickListener {
            refCanvas.deleteSelected()
        }

        findViewById<Button>(R.id.btn_dock_to_practice).setOnClickListener {
            switchToPracticeMode()
        }

        // Bottom Dock - Practice Mode
        btnDockInterval.setOnClickListener {
            currentIntervalIndex = (currentIntervalIndex + 1) % intervals.size
            durationSeconds = intervals[currentIntervalIndex]
            timeRemainingSeconds = durationSeconds
            btnDockInterval.text = intervalLabels[currentIntervalIndex]
            tvBadge.text = "${intervalLabels[currentIntervalIndex].uppercase()} POSE"
            updateTimerDisplay()
            if (isPlaying) startTimer(durationSeconds)
        }

        findViewById<Button>(R.id.btn_dock_practice_pdf).setOnClickListener {
            // Load PDF directly into Practice Mode
            openPdfPicker(1)
        }

        btnDockPlayPause.setOnClickListener {
            togglePlayPause()
        }

        findViewById<Button>(R.id.btn_dock_next).setOnClickListener {
            refCanvas.nextPracticePose()
            if (isPlaying) startTimer(durationSeconds)
        }

        findViewById<Button>(R.id.btn_dock_prev).setOnClickListener {
            refCanvas.prevPracticePose()
            if (isPlaying) startTimer(durationSeconds)
        }

        findViewById<Button>(R.id.btn_dock_flip_p).setOnClickListener {
            refCanvas.flipPracticePose()
        }

        findViewById<Button>(R.id.btn_dock_bw_p).setOnClickListener {
            refCanvas.toggleGrayscalePracticePose()
        }

        findViewById<Button>(R.id.btn_dock_to_ref).setOnClickListener {
            switchToReferenceMode()
        }
    }

    private fun setupLongPressMenus() {
        refCanvas.onItemLongPressed = { item, _, _, _, _ ->
            showItemContextMenu(item)
        }

        refCanvas.onCanvasLongPressed = { _, _, _, _ ->
            showCanvasContextMenu()
        }
    }

    private fun showItemContextMenu(item: RefBoardItem) {
        val options = arrayOf(
            "Copy Reference",
            "Flip Horizontal",
            "Rotate 90 CW",
            "Rotate 90 CCW",
            "Toggle Grayscale (B&W)",
            "Send to Practice Mode",
            "Reset Transforms",
            "Delete Reference"
        )
        AlertDialog.Builder(this)
            .setTitle("Reference Image Operations")
            .setItems(options) { _, which ->
                when (which) {
                    0 -> {
                        DataManager.copiedBitmap = item.bitmap
                        Toast.makeText(this, "Reference copied to clipboard", Toast.LENGTH_SHORT).show()
                    }
                    1 -> refCanvas.flipSelected()
                    2 -> refCanvas.rotateSelectedCW()
                    3 -> refCanvas.rotateSelectedCCW()
                    4 -> refCanvas.toggleGrayscaleSelected()
                    5 -> {
                        refCanvas.practiceItems.add(item.bitmap)
                        DataManager.addPracticeImages(listOf(item.bitmap))
                        switchToPracticeMode()
                        Toast.makeText(this, "Added to Practice Mode", Toast.LENGTH_SHORT).show()
                    }
                    6 -> refCanvas.resetSelectedTransforms()
                    7 -> refCanvas.deleteSelected()
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun showCanvasContextMenu() {
        val pasteLabel = if (DataManager.copiedBitmap != null) "Paste Reference" else "Paste (No Image Copied)"
        val options = arrayOf(
            pasteLabel,
            "Import PDF Reference",
            "Import Images",
            "Import Folder",
            "Load Sample References",
            "Auto Arrange References",
            "Switch to Practice Mode",
            "Float Over Drawing App",
            "Clear Canvas"
        )
        AlertDialog.Builder(this)
            .setTitle("Reference Board Menu")
            .setItems(options) { _, which ->
                when (which) {
                    0 -> {
                        if (DataManager.copiedBitmap != null) {
                            refCanvas.addReferenceItem(DataManager.copiedBitmap!!)
                            DataManager.referenceImages.add(DataManager.copiedBitmap!!)
                            Toast.makeText(this, "Reference pasted", Toast.LENGTH_SHORT).show()
                        } else {
                            Toast.makeText(this, "Clipboard is empty - copy an image first", Toast.LENGTH_SHORT).show()
                        }
                    }
                    1 -> promptDestinationDialog { openPdfPicker(it) }
                    2 -> promptDestinationDialog { openImagePicker(it) }
                    3 -> promptDestinationDialog { openFolderPicker(it) }
                    4 -> loadSampleReferences()
                    5 -> refCanvas.autoArrange()
                    6 -> switchToPracticeMode()
                    7 -> checkOverlayPermissionAndLaunch()
                    8 -> {
                        refCanvas.clearAll()
                        DataManager.referenceImages.clear()
                        Toast.makeText(this, "Canvas cleared", Toast.LENGTH_SHORT).show()
                    }
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun setupPracticeHUD() {
        refCanvas.onPoseChanged = { current, total ->
            tvPoseCounter.text = "Pose $current/$total"
        }
    }

    private val refAddedListener: (Bitmap) -> Unit = { bmp ->
        refCanvas.post {
            refCanvas.addReferenceItem(bmp)
            emptyStateView.visibility = View.GONE
        }
    }

    private val practiceUpdatedListener: () -> Unit = {
        refCanvas.post {
            refCanvas.setPracticeList(DataManager.practiceImages)
            emptyStateView.visibility = View.GONE
        }
    }

    private fun syncWithDataManager() {
        if (DataManager.referenceImages.isNotEmpty()) {
            for (bmp in DataManager.referenceImages) {
                refCanvas.addReferenceItem(bmp)
            }
            emptyStateView.visibility = View.GONE
        }
        if (DataManager.practiceImages.isNotEmpty()) {
            refCanvas.setPracticeList(DataManager.practiceImages)
            emptyStateView.visibility = View.GONE
        }

        DataManager.addReferenceListener(refAddedListener)
        DataManager.addPracticeListener(practiceUpdatedListener)
    }

    private fun loadSampleReferences() {
        val samples = SampleGenerator.createSamplePoses()
        for (bmp in samples) {
            refCanvas.addReferenceItem(bmp)
            DataManager.addReference(bmp)
        }
        refCanvas.setPracticeList(samples)
        DataManager.addPracticeImages(samples)
        refCanvas.autoArrange()
        emptyStateView.visibility = View.GONE
        Toast.makeText(this, "Sample references loaded", Toast.LENGTH_SHORT).show()
    }

    private fun switchToReferenceMode() {
        refCanvas.currentMode = RefCanvasView.MODE_REFERENCE
        btnModeToggle.text = "Ref Board"
        dockRefScroll.visibility = View.VISIBLE
        dockPracticeScroll.visibility = View.GONE
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
        dockRefScroll.visibility = View.GONE
        dockPracticeScroll.visibility = View.VISIBLE
        hudCard.visibility = View.VISIBLE
        updateTimerDisplay()
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
        btnDockPlayPause.text = "Pause"
        startTimer(timeRemainingSeconds)
    }

    private fun pauseTimer() {
        isPlaying = false
        timer?.cancel()
        btnDockPlayPause.text = "Play"
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

    private fun showMainMenu() {
        showCanvasContextMenu()
    }

    private fun promptDestinationDialog(onChosen: (Int) -> Unit) {
        val options = arrayOf("Reference Board", "Practice Mode")
        AlertDialog.Builder(this)
            .setTitle("Import Destination")
            .setItems(options) { _, which ->
                onChosen(which)
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun openImagePicker(targetMode: Int) {
        pendingTargetMode = targetMode
        val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "image/*"
            putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)
        }
        try {
            startActivityForResult(intent, PICK_IMAGES_REQ_CODE)
        } catch (e: Exception) {
            val fallback = Intent(Intent.ACTION_GET_CONTENT).apply {
                type = "image/*"
                putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
                addCategory(Intent.CATEGORY_OPENABLE)
            }
            startActivityForResult(fallback, PICK_IMAGES_REQ_CODE)
        }
    }

    private fun openPdfPicker(targetMode: Int) {
        pendingTargetMode = targetMode
        val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "application/pdf"
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)
        }
        try {
            startActivityForResult(intent, PICK_PDF_REQ_CODE)
        } catch (e: Exception) {
            val fallback = Intent(Intent.ACTION_GET_CONTENT).apply {
                type = "application/pdf"
                addCategory(Intent.CATEGORY_OPENABLE)
            }
            startActivityForResult(fallback, PICK_PDF_REQ_CODE)
        }
    }

    private fun openFolderPicker(targetMode: Int) {
        pendingTargetMode = targetMode
        val intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE)
        startActivityForResult(intent, PICK_FOLDER_REQ_CODE)
    }

    private fun handleIncomingIntent(intent: Intent) {
        when (intent.getStringExtra("action")) {
            "pick_image" -> openImagePicker(0)
            "pick_pdf_ref" -> openPdfPicker(0)
            "pick_pdf_practice" -> openPdfPicker(1)
        }
    }

    private fun checkOverlayPermissionAndLaunch() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            if (!Settings.canDrawOverlays(this)) {
                val intent = Intent(
                    Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    Uri.parse("package:$packageName")
                )
                startActivityForResult(intent, OVERLAY_PERMISSION_REQ_CODE)
                Toast.makeText(this, "Grant 'Appear on top' permission to float over your drawing canvas", Toast.LENGTH_LONG).show()
                return
            }
        }
        startFloatingService()
    }

    private fun startFloatingService() {
        val intent = Intent(this, FloatingOverlayService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent)
        } else {
            startService(intent)
        }
        finish()
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)

        if (requestCode == OVERLAY_PERMISSION_REQ_CODE) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && Settings.canDrawOverlays(this)) {
                startFloatingService()
            } else {
                Toast.makeText(this, "Overlay permission is required to float over drawing apps", Toast.LENGTH_SHORT).show()
            }
            return
        }

        if (resultCode != RESULT_OK || data == null) return

        when (requestCode) {
            PICK_IMAGES_REQ_CODE -> {
                val uris = mutableListOf<Uri>()
                val clipData = data.clipData
                if (clipData != null) {
                    for (i in 0 until clipData.itemCount) {
                        uris.add(clipData.getItemAt(i).uri)
                    }
                } else {
                    data.data?.let { uris.add(it) }
                }

                val loadedBitmaps = mutableListOf<Bitmap>()
                for (uri in uris) {
                    loadBitmapFromUri(uri)?.let { loadedBitmaps.add(it) }
                }

                dispatchBitmaps(loadedBitmaps)
            }

            PICK_PDF_REQ_CODE -> {
                data.data?.let { uri ->
                    val pages = PdfHelper.renderPdfPages(this, uri)
                    if (pages.isNotEmpty()) {
                        dispatchBitmaps(pages)
                        Toast.makeText(this, "Loaded ${pages.size} PDF pages", Toast.LENGTH_SHORT).show()
                    } else {
                        Toast.makeText(this, "Unable to load PDF pages", Toast.LENGTH_SHORT).show()
                    }
                }
            }

            PICK_FOLDER_REQ_CODE -> {
                data.data?.let { treeUri ->
                    loadFolderImages(treeUri)
                }
            }
        }
    }

    private fun loadFolderImages(treeUri: Uri) {
        val loadedBitmaps = mutableListOf<Bitmap>()
        try {
            val childrenUri = DocumentsContract.buildChildDocumentsUriUsingTree(
                treeUri,
                DocumentsContract.getTreeDocumentId(treeUri)
            )

            val projection = arrayOf(
                DocumentsContract.Document.COLUMN_DOCUMENT_ID,
                DocumentsContract.Document.COLUMN_MIME_TYPE
            )

            contentResolver.query(childrenUri, projection, null, null, null)?.use { cursor ->
                val idIndex = cursor.getColumnIndexOrThrow(DocumentsContract.Document.COLUMN_DOCUMENT_ID)
                val mimeIndex = cursor.getColumnIndexOrThrow(DocumentsContract.Document.COLUMN_MIME_TYPE)

                var count = 0
                while (cursor.moveToNext() && count < 50) {
                    val docId = cursor.getString(idIndex)
                    val mime = cursor.getString(mimeIndex)
                    if (mime.startsWith("image/")) {
                        val fileUri = DocumentsContract.buildDocumentUriUsingTree(treeUri, docId)
                        loadBitmapFromUri(fileUri)?.let {
                            loadedBitmaps.add(it)
                            count++
                        }
                    }
                }
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }

        if (loadedBitmaps.isNotEmpty()) {
            dispatchBitmaps(loadedBitmaps)
            Toast.makeText(this, "Loaded ${loadedBitmaps.size} folder images", Toast.LENGTH_SHORT).show()
        }
    }

    private fun dispatchBitmaps(bitmaps: List<Bitmap>) {
        if (pendingTargetMode == 0) {
            for (bmp in bitmaps) {
                DataManager.addReference(bmp)
            }
            refCanvas.autoArrange()
            Toast.makeText(this, "Added to Reference Board", Toast.LENGTH_SHORT).show()
        } else {
            refCanvas.setPracticeList(bitmaps)
            DataManager.addPracticeImages(bitmaps)
            switchToPracticeMode()
            Toast.makeText(this, "Added ${bitmaps.size} poses to Practice Mode", Toast.LENGTH_SHORT).show()
        }
        emptyStateView.visibility = View.GONE
    }

    private fun loadBitmapFromUri(uri: Uri): Bitmap? {
        val bytes = try {
            contentResolver.openInputStream(uri)?.use { it.readBytes() }
        } catch (e: Exception) {
            try {
                contentResolver.openFileDescriptor(uri, "r")?.use { pfd ->
                    java.io.FileInputStream(pfd.fileDescriptor).use { it.readBytes() }
                }
            } catch (e2: Exception) {
                e2.printStackTrace()
                null
            }
        } ?: return null

        if (bytes.isEmpty()) return null

        try {
            val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options)

            val maxDimension = 1600
            var inSampleSize = 1
            if (options.outHeight > maxDimension || options.outWidth > maxDimension) {
                val halfHeight = options.outHeight / 2
                val halfWidth = options.outWidth / 2
                while (halfHeight / inSampleSize >= maxDimension || halfWidth / inSampleSize >= maxDimension) {
                    inSampleSize *= 2
                }
            }

            val loadOptions = BitmapFactory.Options().apply {
                this.inSampleSize = inSampleSize
                inPreferredConfig = Bitmap.Config.ARGB_8888
            }
            return BitmapFactory.decodeByteArray(bytes, 0, bytes.size, loadOptions)
        } catch (oom: OutOfMemoryError) {
            oom.printStackTrace()
            val fallbackOptions = BitmapFactory.Options().apply {
                inSampleSize = 4
                inPreferredConfig = Bitmap.Config.RGB_565
            }
            return try {
                BitmapFactory.decodeByteArray(bytes, 0, bytes.size, fallbackOptions)
            } catch (e: Throwable) {
                null
            }
        } catch (e: Exception) {
            e.printStackTrace()
            return null
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        timer?.cancel()
        DataManager.removeReferenceListener(refAddedListener)
        DataManager.removePracticeListener(practiceUpdatedListener)
    }
}
