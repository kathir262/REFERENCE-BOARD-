package com.refpad.app

import android.app.Activity
import android.content.ClipboardManager
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.util.Log
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowInsets
import android.widget.FrameLayout
import android.widget.Toast
import android.window.OnBackInvokedCallback
import android.window.OnBackInvokedDispatcher

class MainActivity : Activity(), BoardController.Host {

    companion object {
        private const val REQ_OVERLAY = 1
        private const val REQ_IMAGES = 2
        private const val REQ_PDF = 3
        private const val REQ_FOLDER = 4
    }

    private lateinit var controller: BoardController
    private var pendingTarget = Importer.Target.BOARD

    /** Phone-sized screen: the top bar gets a slimmer layout. */
    private val isPhone get() = resources.configuration.smallestScreenWidthDp < 600

    /**
     * A phone's top bar has room for the three mode buttons and two icons only:
     * the wordmark and the + button go (adding is in the bottom toolbar and the menus),
     * and the practice timer moves to its own pill just under the bar.
     */
    private fun adaptForPhone(root: FrameLayout) {
        findViewById<View>(R.id.tv_app_title).visibility = View.GONE
        findViewById<View>(R.id.btn_add).visibility = View.GONE
        val hud = findViewById<View>(R.id.hud_card)
        (hud.parent as ViewGroup).removeView(hud)
        val d = resources.displayMetrics.density
        hud.background = getDrawable(R.drawable.bg_hud)
        hud.setPadding((16 * d).toInt(), (6 * d).toInt(), (16 * d).toInt(), (8 * d).toInt())
        hud.elevation = 7 * d
        root.addView(hud, FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT,
            Gravity.TOP or Gravity.CENTER_HORIZONTAL
        ))
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        DataManager.init(this)

        savedInstanceState?.getString("target")?.let { pendingTarget = Importer.Target.valueOf(it) }
        val root = findViewById<FrameLayout>(R.id.main_root)
        if (isPhone) adaptForPhone(root)
        controller = BoardController(root, root, compact = false, host = this)
        findViewById<View>(R.id.btn_float).setOnClickListener { startFloating() }
        setupEdgeToEdge(root)
        controller.menu.onShowingChanged = { showing -> updateBackHandling(showing) }
        // The board and the PDF reader paint the whole screen themselves; skipping the window
        // background saves one full-screen fill on every frame.
        root.post { window.setBackgroundDrawable(null) }

        // Don't import a share twice when Android recreates the screen.
        if (savedInstanceState == null) root.post { handleShare(intent) }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleShare(intent)
    }

    override fun onStart() {
        super.onStart()
        controller.attach()
        PracticeTimer.hostShown()
    }

    override fun onStop() {
        controller.detach()
        PracticeTimer.hostHidden()
        DataManager.saveNow()
        super.onStop()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        outState.putString("target", pendingTarget.name)
    }

    // ---------------------------------------------------------------- Back gesture

    private var backCallback: OnBackInvokedCallback? = null

    /** Android 13+: while a menu is open, Back closes the menu instead of leaving the app. */
    private fun updateBackHandling(menuShowing: Boolean) {
        if (Build.VERSION.SDK_INT < 33) return
        if (menuShowing && backCallback == null) {
            val cb = OnBackInvokedCallback { controller.menu.dismiss() }
            onBackInvokedDispatcher.registerOnBackInvokedCallback(OnBackInvokedDispatcher.PRIORITY_DEFAULT, cb)
            backCallback = cb
        } else if (!menuShowing) {
            backCallback?.let { onBackInvokedDispatcher.unregisterOnBackInvokedCallback(it) }
            backCallback = null
        }
    }

    @Deprecated("Used on Android 12 and older only; newer versions use the callback above")
    override fun onBackPressed() {
        if (controller.menu.isShowing) controller.menu.dismiss() else super.onBackPressed()
    }

    // ---------------------------------------------------------------- Edge to edge

    /**
     * Android 15+ always draws apps behind the status and navigation bars.
     * The board fills the whole screen; the bars and buttons are pushed clear of the system bars.
     */
    private fun setupEdgeToEdge(root: View) {
        if (Build.VERSION.SDK_INT >= 30) {
            window.setDecorFitsSystemWindows(false)
        } else {
            @Suppress("DEPRECATION")
            root.systemUiVisibility = View.SYSTEM_UI_FLAG_LAYOUT_STABLE or
                View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN or View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
        }
        if (Build.VERSION.SDK_INT < 35) {
            @Suppress("DEPRECATION")
            window.statusBarColor = Color.TRANSPARENT
            @Suppress("DEPRECATION")
            window.navigationBarColor = Color.TRANSPARENT
        }
        val d = resources.displayMetrics.density
        fun dp(v: Int) = (v * d).toInt()
        val topBar = findViewById<View>(R.id.top_bar)
        val toolbar = findViewById<View>(R.id.toolbar)
        val chip = findViewById<View>(R.id.status_chip)
        val canvas = findViewById<View>(R.id.ref_canvas)
        val viewer = findViewById<View>(R.id.pdf_viewer)
        val scrim = findViewById<View>(R.id.status_scrim)

        root.setOnApplyWindowInsetsListener { _, insets ->
            val (l, t, r, b) = if (Build.VERSION.SDK_INT >= 30) {
                val i = insets.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout())
                listOf(i.left, i.top, i.right, i.bottom)
            } else {
                @Suppress("DEPRECATION")
                listOf(insets.systemWindowInsetLeft, insets.systemWindowInsetTop, insets.systemWindowInsetRight, insets.systemWindowInsetBottom)
            }
            (topBar.layoutParams as FrameLayout.LayoutParams).apply {
                topMargin = dp(10) + t; leftMargin = dp(12) + l; rightMargin = dp(12) + r
            }
            (toolbar.layoutParams as FrameLayout.LayoutParams).apply {
                bottomMargin = dp(16) + b; leftMargin = dp(12) + l; rightMargin = dp(12) + r
            }
            (chip.layoutParams as FrameLayout.LayoutParams).bottomMargin = dp(104) + b
            scrim.layoutParams.height = t
            scrim.requestLayout()
            // On phones the timer pill sits under the bar, so poses are fitted below it.
            val hudSpace = if (isPhone) dp(56) else 0
            if (isPhone) {
                val hud = findViewById<View>(R.id.hud_card)
                (hud.layoutParams as FrameLayout.LayoutParams).topMargin = dp(78) + t
                hud.requestLayout()
            }
            canvas.setPadding(l, dp(80) + t + hudSpace, r, dp(100) + b)
            viewer.setPadding(l, dp(80) + t, r, dp(100) + b)
            topBar.requestLayout()
            toolbar.requestLayout()
            chip.requestLayout()
            insets
        }
        root.requestApplyInsets()
    }

    // ---------------------------------------------------------------- BoardController.Host

    override fun pickImages(target: Importer.Target) {
        pendingTarget = target
        Pickers.launch(this, Pickers.images(), Pickers.imagesFallback(), REQ_IMAGES)
    }

    override fun pickPdf(target: Importer.Target) {
        pendingTarget = target
        Pickers.launch(this, Pickers.pdf(), Pickers.pdfFallback(), REQ_PDF)
    }

    override val canPickFolder = true

    override fun pickFolder(target: Importer.Target) {
        pendingTarget = target
        Pickers.launch(this, Pickers.folder(), null, REQ_FOLDER)
    }

    override fun pasteFromSystem(): Boolean {
        val clip = try {
            getSystemService(ClipboardManager::class.java)?.primaryClip
        } catch (e: Exception) {
            null
        } ?: return false
        val uris = (0 until clip.itemCount).mapNotNull { clip.getItemAt(it).uri }
        if (uris.isEmpty()) return false
        Importer.importImages(this, uris, Importer.Target.BOARD)
        return true
    }

    override fun extraMenuItems() = listOf(
        MenuCard.Item("Float over other apps", R.drawable.ic_float) { startFloating() },
        MenuCard.Item("Privacy policy", R.drawable.ic_info) {
            startActivity(Intent(this, PrivacyActivity::class.java))
        }
    )

    override fun toast(text: String) = Toast.makeText(this, text, Toast.LENGTH_SHORT).show()

    // ---------------------------------------------------------------- Results

    @Deprecated("Plain Activity result API; this app uses no AndroidX libraries")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQ_OVERLAY) {
            if (canDrawOverlays()) startFloatingService()
            else toast("Allow \"Appear on top\" to use the floating window")
            return
        }
        if (resultCode != RESULT_OK) return
        when (requestCode) {
            REQ_IMAGES -> Importer.importImages(this, Importer.urisFrom(data), pendingTarget)
            REQ_PDF -> Importer.importPdfs(this, Importer.urisFrom(data), pendingTarget)
            REQ_FOLDER -> data?.data?.let { Importer.importFolder(this, it, pendingTarget) }
        }
    }

    /** Images or a PDF shared from another app (Gallery, browser, Files…). */
    private fun handleShare(intent: Intent?) {
        if (intent == null) return
        val uris: List<Uri> = when (intent.action) {
            Intent.ACTION_SEND -> listOfNotNull(streamExtra(intent))
            Intent.ACTION_SEND_MULTIPLE -> streamListExtra(intent)
            else -> return
        }
        if (uris.isEmpty()) return
        val isPdf = intent.type == "application/pdf"
        controller.chooseDestination(if (isPdf) "this PDF" else if (uris.size == 1) "this image" else "${uris.size} images", isPdf) { target ->
            if (isPdf) Importer.importPdfs(this, uris, target) else Importer.importImages(this, uris, target)
        }
    }

    @Suppress("DEPRECATION")
    private fun streamExtra(intent: Intent): Uri? =
        if (Build.VERSION.SDK_INT >= 33) intent.getParcelableExtra(Intent.EXTRA_STREAM, Uri::class.java)
        else intent.getParcelableExtra(Intent.EXTRA_STREAM)

    @Suppress("DEPRECATION")
    private fun streamListExtra(intent: Intent): List<Uri> =
        (if (Build.VERSION.SDK_INT >= 33) intent.getParcelableArrayListExtra(Intent.EXTRA_STREAM, Uri::class.java)
        else intent.getParcelableArrayListExtra<Uri>(Intent.EXTRA_STREAM)) ?: emptyList()

    // ---------------------------------------------------------------- Floating window

    private fun canDrawOverlays() = Build.VERSION.SDK_INT < 23 || Settings.canDrawOverlays(this)

    private fun startFloating() {
        if (!canDrawOverlays()) {
            toast("Allow \"Appear on top\" for RefPad, then come back")
            try {
                startActivityForResult(
                    Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")),
                    REQ_OVERLAY
                )
            } catch (e: Exception) {
                toast("Open Settings › Apps › RefPad › Appear on top")
            }
            return
        }
        startFloatingService()
    }

    private fun startFloatingService() {
        val intent = Intent(this, FloatingOverlayService::class.java)
        try {
            if (Build.VERSION.SDK_INT >= 26) startForegroundService(intent) else startService(intent)
            DataManager.saveNow()
            finish() // get out of the way of the drawing app
        } catch (e: Exception) {
            Log.e("RefPad", "Could not start floating window", e)
            toast("Could not start the floating window")
        }
    }
}
