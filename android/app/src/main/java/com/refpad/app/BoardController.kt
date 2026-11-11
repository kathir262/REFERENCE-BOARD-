package com.refpad.app

import android.os.Handler
import android.os.Looper
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.ImageButton
import android.widget.ImageView
import android.widget.ProgressBar
import android.widget.TextView
import com.refpad.app.MenuCard.Header
import com.refpad.app.MenuCard.Item
import com.refpad.app.MenuCard.Row

/**
 * All the board/practice UI behaviour, shared by the full-screen app and the floating window.
 * Each screen only supplies what is different (how files are picked, extra menu entries).
 */
class BoardController(
    private val root: View,
    menuHost: FrameLayout,
    private val compact: Boolean,
    private val host: Host
) : DataManager.Listener {

    interface Host {
        fun pickImages(target: Importer.Target)
        fun pickPdf(target: Importer.Target)
        val canPickFolder: Boolean get() = false
        fun pickFolder(target: Importer.Target) {}
        /** Paste an image from the system clipboard. Returns true if one is being imported. */
        fun pasteFromSystem(): Boolean = false
        /** Screen-specific entries added near the end of the "more" menu. */
        fun extraMenuItems(): List<Item> = emptyList()
        fun toast(text: String)
    }

    val canvas: RefCanvasView = root.findViewById(R.id.ref_canvas)
    val menu = MenuCard(menuHost, compact)
    private val menuHostView: View = menuHost
    private val main = Handler(Looper.getMainLooper())

    private val segBoard: TextView = root.findViewById(R.id.seg_board)
    private val segPractice: TextView = root.findViewById(R.id.seg_practice)
    private val segPdf: TextView = root.findViewById(R.id.seg_pdf)
    private val boardTools: View = root.findViewById(R.id.board_tools)
    private val practiceTools: View = root.findViewById(R.id.practice_tools)
    private val pdfTools: View = root.findViewById(R.id.pdf_tools)
    val viewer: PdfViewerView = root.findViewById(R.id.pdf_viewer)
    private val tvPdfPage: TextView = root.findViewById(R.id.tv_pdf_page)
    private val hud: View = root.findViewById(R.id.hud_card)
    private val tvCountdown: TextView = root.findViewById(R.id.tv_countdown)
    private val tvPose: TextView = root.findViewById(R.id.tv_pose_counter)
    private val pbTimer: ProgressBar = root.findViewById(R.id.pb_timer)
    private val statusChip: View = root.findViewById(R.id.status_chip)
    private val statusSpinner: View = root.findViewById(R.id.status_spinner)
    private val tvStatus: TextView = root.findViewById(R.id.tv_status)
    private val btnUndo: View = root.findViewById(R.id.btn_undo)
    private val btnPlay: ImageButton = root.findViewById(R.id.btn_play)
    private val btnInterval: TextView = root.findViewById(R.id.btn_interval)
    private val selectionTools: List<View> = listOf(R.id.btn_flip, R.id.btn_bw, R.id.btn_rotate, R.id.btn_copy, R.id.btn_delete)
        .map { root.findViewById(it) }
    private val btnPaste: View = root.findViewById(R.id.btn_paste)
    private val btnArrange: View = root.findViewById(R.id.btn_arrange)
    private val btnFit: View = root.findViewById(R.id.btn_fit)

    // Full-screen empty state (absent in the floating window)
    private val emptyCard: View? = root.findViewById(R.id.empty_card)
    private val emptyIcon: ImageView? = root.findViewById(R.id.empty_icon)
    private val emptyTitle: TextView? = root.findViewById(R.id.empty_title)
    private val emptyBody: TextView? = root.findViewById(R.id.empty_body)
    private val emptyPrimary: TextView? = root.findViewById(R.id.empty_primary)
    private val emptySecondary: TextView? = root.findViewById(R.id.empty_secondary)
    private val emptyTertiary: TextView? = root.findViewById(R.id.empty_tertiary)
    private val emptyLink: TextView? = root.findViewById(R.id.empty_link)
    // Floating-window empty hint
    private val emptyHint: TextView? = root.findViewById(R.id.empty_hint)

    private val timerListener: () -> Unit = { updateTimer() }

    /** Full-screen app on a phone-sized screen (the floating window has its own compact layout). */
    private val narrowPhone = !compact && root.resources.configuration.smallestScreenWidthDp < 600

    // Undo for the last deleted image
    private var undoItem: RefBoardItem? = null
    private var undoIndex = 0
    private val hideUndo = Runnable { undoItem = null; updateStatus() }

    init {
        wireToolbar()
        wireCanvas()
    }

    // ---------------------------------------------------------------- Adaptive toolbars

    private val toolbars = ArrayList<AdaptiveToolbar>()

    /** The "More" button used to open the overflow; menus opened from hidden tools anchor here. */
    private var overflowAnchor: View? = null

    private val toolIcons = mapOf(
        R.id.btn_arrange to R.drawable.ic_arrange, R.id.btn_copy to R.drawable.ic_copy,
        R.id.btn_paste to R.drawable.ic_paste, R.id.btn_fit to R.drawable.ic_fit,
        R.id.btn_rotate to R.drawable.ic_rotate, R.id.btn_bw to R.drawable.ic_bw,
        R.id.btn_flip to R.drawable.ic_flip, R.id.btn_delete to R.drawable.ic_delete,
        R.id.btn_p_add to R.drawable.ic_add, R.id.btn_p_bw to R.drawable.ic_bw,
        R.id.btn_p_flip to R.drawable.ic_flip, R.id.btn_interval to R.drawable.ic_timer,
        R.id.btn_pdf_practice to R.drawable.ic_timer, R.id.btn_pdf_to_board to R.drawable.ic_image,
        R.id.btn_pdf_recent to R.drawable.ic_history, R.id.btn_pdf_fit to R.drawable.ic_fit,
        R.id.btn_pdf_open to R.drawable.ic_pdf
    )

    init {
        setupAdaptiveToolbars() // after the fields above are ready
    }

    private fun setupAdaptiveToolbars() {
        fun views(vararg ids: Int) = ids.map { root.findViewById<View>(it) }
        // Least important first: these are the first to move into "More" when space runs out.
        toolbars += AdaptiveToolbar(
            boardTools as android.widget.HorizontalScrollView, root.findViewById(R.id.btn_board_more),
            views(R.id.btn_arrange, R.id.btn_copy, R.id.btn_paste, R.id.btn_fit, R.id.btn_rotate,
                R.id.btn_bw, R.id.btn_flip, R.id.btn_delete),
            ::toolbarWidth, ::showOverflow
        )
        toolbars += AdaptiveToolbar(
            practiceTools as android.widget.HorizontalScrollView, root.findViewById(R.id.btn_practice_more),
            views(R.id.btn_p_add, R.id.btn_p_bw, R.id.btn_p_flip, R.id.btn_interval),
            ::toolbarWidth, ::showOverflow
        )
        toolbars += AdaptiveToolbar(
            pdfTools as android.widget.HorizontalScrollView, root.findViewById(R.id.btn_pdf_more),
            views(R.id.btn_pdf_practice, R.id.btn_pdf_to_board, R.id.btn_pdf_recent, R.id.btn_pdf_fit, R.id.btn_pdf_open),
            ::toolbarWidth, ::showOverflow
        )
        // Re-fit whenever the screen or window changes width (rotation, split screen, resizing).
        root.addOnLayoutChangeListener { _, l, _, r, _, ol, _, or_, _ ->
            if (r - l != or_ - ol) root.post { toolbars.forEach { it.update() } }
        }
        root.post { toolbars.forEach { it.update(force = true) } }
    }

    /** Width a toolbar row may use. */
    private fun toolbarWidth(): Int {
        val bar = boardTools.parent as View
        return if (compact) {
            // Floating window: toolbars span the window.
            bar.width - bar.paddingLeft - bar.paddingRight
        } else {
            // Full screen: the toolbar pill is centred, so use the screen width minus its margins.
            val lp = bar.layoutParams as ViewGroup.MarginLayoutParams
            root.width - lp.leftMargin - lp.rightMargin - bar.paddingLeft - bar.paddingRight
        }
    }

    private fun showOverflow(anchor: View, hidden: List<View>) {
        overflowAnchor = anchor
        val (x, y) = anchorBelow(anchor)
        val rows = hidden.map { v ->
            val label = ((v as? TextView)?.text ?: v.contentDescription ?: "").toString()
            MenuCard.Item(
                label, toolIcons[v.id] ?: R.drawable.ic_more,
                danger = v.id == R.id.btn_delete, enabled = v.isEnabled
            ) { v.performClick() }
        }
        menu.show(x, y, rows)
    }

    fun attach() {
        DataManager.addListener(this)
        PracticeTimer.addListener(timerListener)
        refreshAll()
    }

    fun detach() {
        DataManager.removeListener(this)
        PracticeTimer.removeListener(timerListener)
        menu.dismiss()
    }

    // ---------------------------------------------------------------- Wiring

    private fun click(id: Int, action: (View) -> Unit) {
        root.findViewById<View>(id)?.setOnClickListener { action(it) }
    }

    private fun wireToolbar() {
        segBoard.setOnClickListener { DataManager.setMode(DataManager.MODE_BOARD) }
        segPractice.setOnClickListener { DataManager.setMode(DataManager.MODE_PRACTICE) }
        segPdf.setOnClickListener { DataManager.setMode(DataManager.MODE_PDF) }

        // PDF reader
        click(R.id.btn_pdf_open) { host.pickPdf(Importer.Target.VIEWER) }
        click(R.id.btn_pdf_recent) { showRecentMenu(it) }
        click(R.id.btn_pdf_prev) { viewer.prevPage() }
        click(R.id.btn_pdf_next) { viewer.nextPage() }
        click(R.id.btn_pdf_fit) { viewer.toggleFit() }
        click(R.id.btn_pdf_to_board) { pageToBoard(viewer.currentPage) }
        click(R.id.btn_pdf_practice) { practiseFrom(viewer.currentPage) }
        click(R.id.btn_add) { showAddMenu(it) }
        click(R.id.btn_more) { showMoreMenu(it) }

        // Board
        click(R.id.btn_add_image) { host.pickImages(Importer.Target.BOARD) }
        click(R.id.btn_add_pdf) { host.pickPdf(Importer.Target.BOARD) }
        click(R.id.btn_flip) { editSelected { it.flipped = !it.flipped } }
        click(R.id.btn_bw) { editSelected { it.grayscale = !it.grayscale } }
        click(R.id.btn_rotate) { editSelected { it.rotateCW() } }
        click(R.id.btn_copy) { copySelected() }
        click(R.id.btn_paste) { paste(null, null) }
        click(R.id.btn_delete) { canvas.selectedItem?.let { deleteItem(it) } }
        click(R.id.btn_arrange) { DataManager.autoArrange() }
        click(R.id.btn_fit) { canvas.fitAll() }
        btnUndo.setOnClickListener { undoDelete() }

        // Practice
        btnInterval.setOnClickListener { PracticeTimer.cycleInterval() }
        click(R.id.btn_prev) { DataManager.prevPose(); PracticeTimer.restartPose() }
        click(R.id.btn_next) { DataManager.nextPose(); PracticeTimer.restartPose() }
        btnPlay.setOnClickListener {
            if (DataManager.practice.isEmpty()) host.toast("Add a PDF or images to practice with first")
            else PracticeTimer.toggle()
        }
        click(R.id.btn_p_flip) { DataManager.togglePracticeFlip() }
        click(R.id.btn_p_bw) { DataManager.togglePracticeGrayscale() }
        click(R.id.btn_p_add) { showAddMenu(it, practiceOnly = true) }

        emptyHint?.setOnClickListener { showAddMenu(it, practiceOnly = DataManager.mode == DataManager.MODE_PRACTICE) }
    }

    private fun wireCanvas() {
        canvas.onTouchStarted = { if (menu.isShowing) menu.dismiss() }
        canvas.onSelectionChanged = { updateSelectionTools() }
        canvas.onItemLongPressed = { item, x, y -> showItemMenu(item, x, y) }
        canvas.onCanvasLongPressed = { x, y ->
            if (DataManager.mode == DataManager.MODE_BOARD) showBoardMenu(x, y, pasteAt = canvas.boardPointAt(x, y))
            else showPracticeMenu(x, y)
        }
        viewer.onTouchStarted = { if (menu.isShowing) menu.dismiss() }
        viewer.onPageChanged = { page, count -> tvPdfPage.setTextIfChanged("${page + 1} / $count") }
        viewer.onLongPressed = { x, y, page -> showPdfMenu(x, y, page) }
    }

    // ---------------------------------------------------------------- DataManager.Listener

    override fun onBoardChanged() {
        updateEmptyState()
        updateSegments()
        updateSelectionTools()
    }

    override fun onPracticeChanged() {
        updateEmptyState()
        updateSegments()
        updateTimer()
    }

    override fun onModeChanged() {
        menu.dismiss()
        updateMode()
        updateEmptyState()
        updateTimer()
    }

    override fun onStatusChanged() = updateStatus()

    override fun onDocsChanged() {
        updateEmptyState()
        if (DataManager.docs.isEmpty()) tvPdfPage.text = "-" else viewer.reportPage()
    }

    // ---------------------------------------------------------------- UI updates

    private fun refreshAll() {
        updateMode()
        updateSegments()
        updateEmptyState()
        updateSelectionTools()
        updateTimer()
        updateStatus()
    }

    private fun updateMode() {
        val mode = DataManager.mode
        segBoard.isSelected = mode == DataManager.MODE_BOARD
        segPractice.isSelected = mode == DataManager.MODE_PRACTICE
        segPdf.isSelected = mode == DataManager.MODE_PDF
        boardTools.visibility = if (mode == DataManager.MODE_BOARD) View.VISIBLE else View.GONE
        practiceTools.visibility = if (mode == DataManager.MODE_PRACTICE) View.VISIBLE else View.GONE
        pdfTools.visibility = if (mode == DataManager.MODE_PDF) View.VISIBLE else View.GONE
        canvas.visibility = if (mode == DataManager.MODE_PDF) View.GONE else View.VISIBLE
        viewer.visibility = if (mode == DataManager.MODE_PDF) View.VISIBLE else View.GONE
        if (mode == DataManager.MODE_PDF) viewer.reportPage()
    }

    private fun updateSegments() {
        if (compact || narrowPhone) return // no room for counts on small screens
        val b = DataManager.items.size
        val p = DataManager.practice.size
        segBoard.setTextIfChanged(if (b > 0) "Board  $b" else "Board")
        segPractice.setTextIfChanged(if (p > 0) "Practice  $p" else "Practice")
    }

    private fun updateSelectionTools() {
        val hasSelection = canvas.selectedItem != null
        for (v in selectionTools) v.isEnabled = hasSelection
        btnPaste.isEnabled = DataManager.clipboard != null || !compact
        val hasItems = DataManager.items.isNotEmpty()
        btnArrange.isEnabled = hasItems
        btnFit.isEnabled = hasItems
    }

    private fun updateTimer() {
        val practice = DataManager.mode == DataManager.MODE_PRACTICE
        val n = DataManager.practice.size
        val showHud = if (practice && n > 0) View.VISIBLE else View.GONE
        if (hud.visibility != showHud) hud.visibility = showHud
        if (pbTimer.visibility != showHud) pbTimer.visibility = showHud
        btnInterval.setTextIfChanged(PracticeTimer.label)
        val playIcon = if (PracticeTimer.running) R.drawable.ic_pause else R.drawable.ic_play
        if (btnPlay.tag != playIcon) {
            btnPlay.tag = playIcon
            btnPlay.setImageResource(playIcon)
        }
        if (n == 0) return
        tvCountdown.setTextIfChanged(PracticeTimer.text)
        val i = DataManager.practiceIndex + 1
        tvPose.setTextIfChanged(if (compact) "$i/$n" else "Pose $i of $n")
        pbTimer.progress = PracticeTimer.progress
        tvCountdown.alpha = if (PracticeTimer.running) 1f else 0.55f
    }

    private fun updateStatus() {
        val status = DataManager.status
        when {
            status != null -> {
                statusChip.visibility = View.VISIBLE
                statusSpinner.visibility = View.VISIBLE
                btnUndo.visibility = View.GONE
                tvStatus.setTextIfChanged(status)
            }
            undoItem != null -> {
                statusChip.visibility = View.VISIBLE
                statusSpinner.visibility = View.GONE
                btnUndo.visibility = View.VISIBLE
                tvStatus.setTextIfChanged("Image deleted")
            }
            else -> statusChip.visibility = View.GONE
        }
    }

    private fun updateEmptyState() {
        val restored = DataManager.restored
        val mode = DataManager.mode
        val practice = mode == DataManager.MODE_PRACTICE
        val pdf = mode == DataManager.MODE_PDF
        val empty = restored && when (mode) {
            DataManager.MODE_PRACTICE -> DataManager.practice.isEmpty()
            DataManager.MODE_PDF -> DataManager.docs.isEmpty()
            else -> DataManager.items.isEmpty()
        }

        emptyHint?.let {
            it.visibility = if (empty) View.VISIBLE else View.GONE
            it.text = when {
                pdf -> "Tap to open a PDF to read"
                practice -> "Add a PDF or images\nto practise with"
                else -> "Tap to add images or a PDF\nor long-press for more"
            }
        }

        val card = emptyCard ?: return
        card.visibility = if (empty) View.VISIBLE else View.GONE
        if (!empty) return
        if (pdf) {
            emptyIcon?.setImageResource(R.drawable.ic_pdf)
            emptyTitle?.text = "Read a PDF"
            emptyBody?.text = "Open art books, tutorials and comics. Pages load as you scroll, so even very large books stay light and smooth."
            emptyPrimary?.text = "Open a PDF"
            emptyPrimary?.setOnClickListener { host.pickPdf(Importer.Target.VIEWER) }
            emptySecondary?.text = "Back to board"
            emptySecondary?.setOnClickListener { DataManager.setMode(DataManager.MODE_BOARD) }
            emptyTertiary?.visibility = View.GONE
            emptyLink?.text = "Practise with a PDF instead"
            emptyLink?.setOnClickListener { host.pickPdf(Importer.Target.PRACTICE) }
        } else if (practice) {
            emptyIcon?.setImageResource(R.drawable.ic_timer)
            emptyTitle?.text = "Nothing to practise yet"
            emptyBody?.text = "Open a PDF art book or pick images. Each pose stays up for the time you choose, then moves on by itself."
            emptyPrimary?.text = "Open a PDF art book"
            emptyPrimary?.setOnClickListener { host.pickPdf(Importer.Target.PRACTICE) }
            emptySecondary?.text = "Add images"
            emptySecondary?.setOnClickListener { host.pickImages(Importer.Target.PRACTICE) }
            emptyTertiary?.visibility = View.VISIBLE
            emptyTertiary?.text = "Use board images"
            emptyTertiary?.isEnabled = DataManager.items.isNotEmpty()
            emptyTertiary?.alpha = if (DataManager.items.isNotEmpty()) 1f else 0.4f
            emptyTertiary?.setOnClickListener { DataManager.practiceWithBoardImages() }
            emptyLink?.text = "Back to the board"
            emptyLink?.setOnClickListener { DataManager.setMode(DataManager.MODE_BOARD) }
        } else {
            emptyIcon?.setImageResource(R.drawable.ic_image)
            emptyTitle?.text = "Your board is empty"
            emptyBody?.text = "Add images or a PDF art book, then float the board over your drawing app."
            emptyPrimary?.text = "Add images"
            emptyPrimary?.setOnClickListener { host.pickImages(Importer.Target.BOARD) }
            emptySecondary?.text = "Open PDF"
            emptySecondary?.setOnClickListener { host.pickPdf(Importer.Target.BOARD) }
            emptyTertiary?.visibility = if (host.canPickFolder) View.VISIBLE else View.GONE
            emptyTertiary?.text = "Import folder"
            emptyTertiary?.isEnabled = true
            emptyTertiary?.alpha = 1f
            emptyTertiary?.setOnClickListener { host.pickFolder(Importer.Target.BOARD) }
            emptyLink?.text = "Try sample poses"
            emptyLink?.setOnClickListener { Importer.loadSamples() }
        }
    }

    // ---------------------------------------------------------------- Actions

    private fun editSelected(change: (RefBoardItem) -> Unit) {
        val item = canvas.selectedItem
        if (item == null) {
            host.toast("Tap an image first")
            return
        }
        change(item)
        DataManager.boardChanged()
    }

    private fun copySelected() {
        val item = canvas.selectedItem ?: return host.toast("Tap an image first")
        DataManager.clipboard = item.image
        updateSelectionTools()
        host.toast("Image copied")
    }

    /** Pastes our own copied image, or falls back to an image on the system clipboard. */
    private fun paste(boardX: Float?, boardY: Float?) {
        val clip = DataManager.clipboard
        if (clip != null) {
            val (cx, cy) = if (boardX != null && boardY != null) boardX to boardY else canvas.boardCenter()
            val item = DataManager.addToBoard(clip, cx + if (boardX == null) 30f else 0f, cy + if (boardY == null) 30f else 0f)
            canvas.select(item)
            return
        }
        if (!host.pasteFromSystem()) host.toast("Nothing to paste – copy an image first")
    }

    private fun deleteItem(item: RefBoardItem) {
        undoIndex = DataManager.items.indexOf(item)
        undoItem = item
        DataManager.removeItem(item)
        main.removeCallbacks(hideUndo)
        main.postDelayed(hideUndo, 6000)
        updateStatus()
    }

    private fun undoDelete() {
        val item = undoItem ?: return
        undoItem = null
        main.removeCallbacks(hideUndo)
        DataManager.items.add(undoIndex.coerceIn(0, DataManager.items.size), item)
        DataManager.boardChanged()
        canvas.select(item)
        updateStatus()
    }

    private fun sendToPractice(item: RefBoardItem) {
        DataManager.addPoses(listOf(Pose.Image(item.image)), jumpToFirst = true)
        DataManager.setMode(DataManager.MODE_PRACTICE)
    }

    // ---------------------------------------------------------------- Menus

    /** Position of [v]'s bottom-left corner inside the menu host. */
    private fun anchorBelow(view: View): Pair<Float, Float> {
        // A tool hidden in the "More" menu has no position of its own; anchor to the More button instead.
        val v = if (view.isShown) view else overflowAnchor ?: view
        val a = IntArray(2)
        val h = IntArray(2)
        v.getLocationInWindow(a)
        menuHostView.getLocationInWindow(h)
        return (a[0] - h[0]).toFloat() + v.width / 2f to (a[1] - h[1]).toFloat() + v.height
    }

    private fun showAddMenu(anchor: View, practiceOnly: Boolean = false) {
        val (x, y) = anchorBelow(anchor)
        val rows = ArrayList<Row>()
        if (!practiceOnly) {
            rows += Header("Add to board")
            rows += Item("Images", R.drawable.ic_image) { host.pickImages(Importer.Target.BOARD) }
            rows += Item("PDF pages (first ${Importer.BOARD_PDF_MAX_PAGES})", R.drawable.ic_pdf) { host.pickPdf(Importer.Target.BOARD) }
            if (host.canPickFolder) rows += Item("Folder of images", R.drawable.ic_folder) { host.pickFolder(Importer.Target.BOARD) }
            rows += Item("Sample poses", R.drawable.ic_sparkle) { Importer.loadSamples() }
        }
        rows += Header("Add to practice")
        rows += Item("PDF art book (every page)", R.drawable.ic_pdf) { host.pickPdf(Importer.Target.PRACTICE) }
        rows += Item("Images", R.drawable.ic_image) { host.pickImages(Importer.Target.PRACTICE) }
        rows += Item("Use board images", R.drawable.ic_arrange, enabled = DataManager.items.isNotEmpty()) {
            DataManager.practiceWithBoardImages()
            DataManager.setMode(DataManager.MODE_PRACTICE)
        }
        if (!practiceOnly) {
            rows += Header("Read")
            rows += Item("Open a PDF to read", R.drawable.ic_pdf) { host.pickPdf(Importer.Target.VIEWER) }
        }
        menu.show(x, y, rows)
    }

    private fun showMoreMenu(anchor: View) {
        val (x, y) = anchorBelow(anchor)
        when (DataManager.mode) {
            DataManager.MODE_BOARD -> showBoardMenu(x, y, pasteAt = null)
            DataManager.MODE_PRACTICE -> showPracticeMenu(x, y)
            else -> showPdfMenu(x, y, viewer.currentPage)
        }
    }

    private fun pageToBoard(page: Int) {
        val doc = DataManager.currentDoc ?: return host.toast("Open a PDF first")
        Importer.pageToBoard(root.context, doc, page)
    }

    private fun practiseFrom(page: Int) {
        val doc = DataManager.currentDoc ?: return host.toast("Open a PDF first")
        DataManager.practiceDoc(doc, page)
    }

    private fun showPdfMenu(x: Float, y: Float, page: Int) {
        val doc = DataManager.currentDoc
        val rows = ArrayList<Row>()
        rows += Header(doc?.title ?: "PDF")
        rows += Item("Open another PDF", R.drawable.ic_pdf) { host.pickPdf(Importer.Target.VIEWER) }
        if (doc != null) {
            rows += Item("Add page ${page + 1} to the board", R.drawable.ic_image) { pageToBoard(page) }
            rows += Item("Practise from page ${page + 1}", R.drawable.ic_timer) { practiseFrom(page) }
            rows += Item("Fit width / whole page", R.drawable.ic_fit) { viewer.toggleFit() }
            rows += Item("Go to first page", R.drawable.ic_page_up) { viewer.goToPage(0) }
            rows += Item("Go to last page", R.drawable.ic_page_down) { viewer.goToPage(doc.pageCount - 1) }
        }
        val others = DataManager.docs.drop(1)
        if (others.isNotEmpty()) {
            rows += Header("Recent")
            for (d in others.take(6)) rows += Item(d.title, R.drawable.ic_history) { DataManager.openDoc(d) }
        }
        rows += host.extraMenuItems()
        if (doc != null) {
            rows += Item("Remove from recent", R.drawable.ic_delete, danger = true, confirm = "Tap again to remove") {
                DataManager.removeDoc(doc)
            }
        }
        menu.show(x, y, rows)
    }

    private fun showRecentMenu(anchor: View) {
        val (x, y) = anchorBelow(anchor)
        val rows = ArrayList<Row>()
        rows += Header("Recent PDFs")
        if (DataManager.docs.isEmpty()) {
            rows += Item("Nothing opened yet", R.drawable.ic_history, enabled = false) {}
        }
        for ((i, d) in DataManager.docs.withIndex()) {
            val label = if (i == 0) "${d.title}  (open)" else d.title
            rows += Item(label, R.drawable.ic_pdf, enabled = i != 0) { DataManager.openDoc(d) }
        }
        rows += Item("Open a PDF…", R.drawable.ic_add) { host.pickPdf(Importer.Target.VIEWER) }
        menu.show(x, y, rows)
    }

    private fun showItemMenu(item: RefBoardItem, x: Float, y: Float) {
        menu.show(
            x, y, listOf(
                Header("Image"),
                Item("Copy", R.drawable.ic_copy) { copySelected() },
                Item("Flip horizontally", R.drawable.ic_flip) { editSelected { it.flipped = !it.flipped } },
                Item("Rotate right", R.drawable.ic_rotate) { editSelected { it.rotateCW() } },
                Item("Rotate left", R.drawable.ic_rotate_left) { editSelected { it.rotateCCW() } },
                Item(if (item.grayscale) "Show in colour" else "Black & white", R.drawable.ic_bw) { editSelected { it.grayscale = !it.grayscale } },
                Item("Zoom to this image", R.drawable.ic_zoom) { canvas.fitItem(item) },
                Item("Send to practice", R.drawable.ic_timer) { sendToPractice(item) },
                Item("Reset size and rotation", R.drawable.ic_reset) { editSelected { it.resetTransforms() } },
                Item("Delete", R.drawable.ic_delete, danger = true) { deleteItem(item) }
            )
        )
    }

    private fun showBoardMenu(x: Float, y: Float, pasteAt: Pair<Float, Float>?) {
        val hasItems = DataManager.items.isNotEmpty()
        val rows = ArrayList<Row>()
        rows += Header("Board")
        rows += Item("Paste", R.drawable.ic_paste, enabled = DataManager.clipboard != null || !compact) {
            paste(pasteAt?.first, pasteAt?.second)
        }
        rows += Item("Add images", R.drawable.ic_image) { host.pickImages(Importer.Target.BOARD) }
        rows += Item("Add PDF pages", R.drawable.ic_pdf) { host.pickPdf(Importer.Target.BOARD) }
        if (host.canPickFolder) rows += Item("Import folder", R.drawable.ic_folder) { host.pickFolder(Importer.Target.BOARD) }
        rows += Item("Fit everything", R.drawable.ic_fit, enabled = hasItems) { canvas.fitAll() }
        rows += Item("Arrange in rows", R.drawable.ic_arrange, enabled = hasItems) { DataManager.autoArrange() }
        rows += Item("Practise with these images", R.drawable.ic_timer, enabled = hasItems) {
            DataManager.practiceWithBoardImages()
            DataManager.setMode(DataManager.MODE_PRACTICE)
        }
        rows += host.extraMenuItems()
        rows += Item("Clear board", R.drawable.ic_delete, danger = true, enabled = hasItems, confirm = "Tap again to clear the board") {
            DataManager.clearBoard()
        }
        menu.show(x, y, rows)
    }

    private fun showPracticeMenu(x: Float, y: Float) {
        val hasPoses = DataManager.practice.isNotEmpty()
        val rows = ArrayList<Row>()
        rows += Header("Practice")
        rows += Item("Open PDF art book", R.drawable.ic_pdf) { host.pickPdf(Importer.Target.PRACTICE) }
        rows += Item("Add images", R.drawable.ic_image) { host.pickImages(Importer.Target.PRACTICE) }
        rows += Item("Use board images", R.drawable.ic_arrange, enabled = DataManager.items.isNotEmpty()) {
            DataManager.practiceWithBoardImages()
        }
        rows += Item("Reset zoom", R.drawable.ic_fit, enabled = hasPoses) { canvas.resetPoseZoom() }
        rows += Item("Back to board", R.drawable.ic_image) { DataManager.setMode(DataManager.MODE_BOARD) }
        rows += host.extraMenuItems()
        rows += Item("Clear practice list", R.drawable.ic_delete, danger = true, enabled = hasPoses, confirm = "Tap again to clear practice") {
            DataManager.clearPractice()
        }
        menu.show(x, y, rows)
    }

    /** Asks where shared files should go (board or practice). */
    fun chooseDestination(what: String, isPdf: Boolean, onChosen: (Importer.Target) -> Unit) {
        val w = menuHostView.width.toFloat()
        val h = menuHostView.height.toFloat()
        val rows = ArrayList<Row>()
        rows += Header("Add $what to")
        if (isPdf) rows += Item("PDF reader", R.drawable.ic_pdf) { onChosen(Importer.Target.VIEWER) }
        rows += Item("Board", R.drawable.ic_image) { onChosen(Importer.Target.BOARD) }
        rows += Item("Practice", R.drawable.ic_timer) { onChosen(Importer.Target.PRACTICE) }
        menu.show(w / 2f - 130f * root.resources.displayMetrics.density, h / 3f, rows)
    }
}

/** Changing a label's text makes Android re-measure the screen; skip it when nothing changed. */
private fun TextView.setTextIfChanged(value: CharSequence) {
    if (!android.text.TextUtils.equals(text, value)) text = value
}
