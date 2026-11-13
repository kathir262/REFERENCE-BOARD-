package com.refpad.app

import android.net.Uri
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
import kotlin.math.abs

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
        /** Lets the user pick a .refpad board file; the screen then calls [openBoard]. */
        fun openBoardFile()
        /** Lets the user choose where to save the board ("Save as"); the screen then calls BoardFiles.created. */
        fun createBoardFile(suggestedName: String)
        /** Asks for a line of text (for example page numbers), or several lines with [multiLine]. */
        fun askText(title: String, hint: String, initial: String, multiLine: Boolean = false, onOk: (String) -> Unit)
        /** Lets the user choose where to save the board as a PNG picture; the screen then calls BoardExport.export. */
        fun createExportFile(suggestedName: String)
        /** Shows the practice history (poses, minutes, streak). */
        fun showHistory()
        /** Full screen only: open the floating window zoomed to this picture. */
        val canFloat: Boolean get() = false
        fun floatItem(item: RefBoardItem) {}
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
    private val pdfChooseTools: View = root.findViewById(R.id.pdf_choose_tools)
    private val tvChooseCount: TextView = root.findViewById(R.id.tv_choose_count)
    /** Board name in the top bar (full screen only). */
    private val tvTitle: TextView? = root.findViewById(R.id.tv_app_title)
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
    /** Work on any selected item (picture or note). */
    private val selectionTools: List<View> = listOf(R.id.btn_copy, R.id.btn_delete).map { root.findViewById(it) }
    /** Work on a selected picture only. */
    private val pictureTools: List<View> = listOf(R.id.btn_flip, R.id.btn_bw, R.id.btn_rotate).map { root.findViewById(it) }
    private val btnBoardUndo: View = root.findViewById(R.id.btn_b_undo)
    private val btnBoardRedo: View = root.findViewById(R.id.btn_b_redo)
    private val btnCrop: View = root.findViewById(R.id.btn_crop)
    private val btnPicker: View = root.findViewById(R.id.btn_picker)
    private val btnClass: View = root.findViewById(R.id.btn_class)
    private val btnMemory: View = root.findViewById(R.id.btn_memory)
    private val btnSpread: View = root.findViewById(R.id.btn_pdf_spread)
    private val btnPages: View = root.findViewById(R.id.btn_pdf_pages)
    private val btnSearch: View = root.findViewById(R.id.btn_pdf_search)
    private val btnSnip: View = root.findViewById(R.id.btn_pdf_snip)
    private val btnBookmark: View = root.findViewById(R.id.btn_pdf_bookmark)
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

    // "Picture deleted · UNDO" message after a delete or clearing the board
    private var undoText: String? = null
    private var undoVersion = -1
    private val hideUndo = Runnable { undoText = null; updateStatus() }

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
        R.id.btn_pdf_open to R.drawable.ic_pdf,
        R.id.btn_choose_all to R.drawable.ic_arrange, R.id.btn_choose_none to R.drawable.ic_reset,
        R.id.btn_choose_pages to R.drawable.ic_pdf,
        R.id.btn_b_undo to R.drawable.ic_undo, R.id.btn_b_redo to R.drawable.ic_redo,
        R.id.btn_crop to R.drawable.ic_crop, R.id.btn_note to R.drawable.ic_note,
        R.id.btn_picker to R.drawable.ic_picker, R.id.btn_class to R.drawable.ic_class,
        R.id.btn_memory to R.drawable.ic_memory,
        R.id.btn_pdf_spread to R.drawable.ic_spread, R.id.btn_pdf_pages to R.drawable.ic_pages,
        R.id.btn_pdf_search to R.drawable.ic_search, R.id.btn_pdf_snip to R.drawable.ic_snip,
        R.id.btn_pdf_bookmark to R.drawable.ic_bookmark
    )

    init {
        setupAdaptiveToolbars() // after the fields above are ready
    }

    private fun setupAdaptiveToolbars() {
        // Not offered on this Android version: take it off the toolbar so fitting it never shows it again.
        if (!PdfSearch.supported) (btnSearch.parent as? ViewGroup)?.removeView(btnSearch)
        fun views(vararg ids: Int) = ids.toList().mapNotNull { root.findViewById<View>(it) }
        // Least important first: these are the first to move into "More" when space runs out.
        toolbars += AdaptiveToolbar(
            boardTools as android.widget.HorizontalScrollView, root.findViewById(R.id.btn_board_more),
            views(R.id.btn_arrange, R.id.btn_b_redo, R.id.btn_copy, R.id.btn_paste, R.id.btn_note, R.id.btn_picker,
                R.id.btn_fit, R.id.btn_rotate, R.id.btn_bw, R.id.btn_crop, R.id.btn_flip, R.id.btn_b_undo, R.id.btn_delete),
            ::toolbarWidth, ::showOverflow
        )
        toolbars += AdaptiveToolbar(
            practiceTools as android.widget.HorizontalScrollView, root.findViewById(R.id.btn_practice_more),
            views(R.id.btn_p_add, R.id.btn_memory, R.id.btn_p_bw, R.id.btn_p_flip, R.id.btn_class, R.id.btn_interval),
            ::toolbarWidth, ::showOverflow
        )
        toolbars += AdaptiveToolbar(
            pdfTools as android.widget.HorizontalScrollView, root.findViewById(R.id.btn_pdf_more),
            views(R.id.btn_pdf_practice, R.id.btn_pdf_to_board, R.id.btn_pdf_spread, R.id.btn_pdf_bookmark, R.id.btn_pdf_pages,
                R.id.btn_pdf_recent, R.id.btn_pdf_search, R.id.btn_pdf_snip, R.id.btn_pdf_fit, R.id.btn_pdf_open),
            ::toolbarWidth, ::showOverflow
        )
        toolbars += AdaptiveToolbar(
            pdfChooseTools as android.widget.HorizontalScrollView, root.findViewById(R.id.btn_choose_more),
            views(R.id.btn_choose_none, R.id.btn_choose_pages, R.id.btn_choose_all),
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
                if (v.isSelected) "$label  ✓" else label, toolIcons[v.id] ?: R.drawable.ic_more,
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
        click(R.id.btn_pdf_to_board) { showToBoardMenu(it) }
        click(R.id.btn_pdf_practice) { practiseFrom(viewer.currentPage) }
        click(R.id.btn_pdf_spread) { viewer.setSpread(!viewer.spread) }
        click(R.id.btn_pdf_pages) { viewer.setStripShown(!viewer.stripShown) }
        click(R.id.btn_pdf_search) { openSearch() }
        click(R.id.btn_pdf_snip) { toggleSnip() }
        click(R.id.btn_pdf_bookmark) { toggleBookmark(viewer.currentPage) }
        // Android's PDF engine can search text from Android 15 on; older versions don't show the button.
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
        click(R.id.btn_b_undo) { undo() }
        click(R.id.btn_b_redo) { redo() }
        click(R.id.btn_crop) { toggleCrop() }
        click(R.id.btn_note) { addNote(null) }
        click(R.id.btn_picker) { togglePicker() }
        btnUndo.setOnClickListener {
            val stop = DataManager.statusStop
            if (DataManager.status != null && stop != null) stop() else undoFromMessage()
        }

        // Choosing PDF pages for the board
        click(R.id.btn_choose_cancel) { stopChoosing() }
        click(R.id.btn_choose_all) { viewer.chooseAll(true) }
        click(R.id.btn_choose_none) { viewer.chooseAll(false) }
        click(R.id.btn_choose_pages) { askPageNumbers() }
        click(R.id.btn_choose_add) { addChosenPages() }

        // Board files
        tvTitle?.setOnClickListener { showBoardFileMenu(it) }

        // Practice
        btnInterval.setOnClickListener { if (PracticeTimer.plan != null) showClassMenu(it) else PracticeTimer.cycleInterval() }
        click(R.id.btn_prev) { PracticeTimer.previous() }
        click(R.id.btn_next) { PracticeTimer.next() }
        click(R.id.btn_class) { showClassMenu(it) }
        click(R.id.btn_memory) { toggleMemory() }
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
        canvas.onItemLongPressed = { item, x, y -> if (item.isNote) showNoteMenu(item, x, y) else showItemMenu(item, x, y) }
        canvas.onNoteDoubleTapped = { editNote(it) }
        canvas.onToolChanged = { updateSelectionTools() }
        canvas.onColorPicked = { colorPicked(it) }
        canvas.onCanvasLongPressed = { x, y ->
            if (DataManager.mode == DataManager.MODE_BOARD) showBoardMenu(x, y, pasteAt = canvas.boardPointAt(x, y))
            else showPracticeMenu(x, y)
        }
        viewer.onTouchStarted = { if (menu.isShowing) menu.dismiss() }
        viewer.onPageChanged = { page, count ->
            tvPdfPage.setTextIfChanged("${viewer.pageLabel(page)} / $count")
            updatePdfTools()
        }
        viewer.onToolsChanged = { updatePdfTools() }
        viewer.onSnipped = { page, frac ->
            DataManager.currentDoc?.let { Importer.regionToBoard(root.context, it, page, frac) }
        }
        viewer.onLongPressed = { x, y, page -> showPdfMenu(x, y, page) }
        viewer.onChosenChanged = { n -> updateChooseCount(n) }
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
        if (DataManager.mode != DataManager.MODE_PDF) closeSearch()
        updateMode()
        updateEmptyState()
        updateTimer()
    }

    override fun onStatusChanged() = updateStatus()

    override fun onBoardFileChanged() = updateTitle()

    override fun onChoosePages(doc: ViewerDoc) {
        viewer.startChoosing(all = true)
        updateMode()
        host.toast("Tap pages to choose them, then tap Add")
    }

    override fun onDocsChanged() {
        if (searchDoc != null && searchDoc !== DataManager.currentDoc) closeSearch()
        updatePdfTools()
        updateEmptyState()
        if (DataManager.docs.isEmpty()) tvPdfPage.text = "-" else viewer.reportPage()
    }

    // ---------------------------------------------------------------- UI updates

    private fun refreshAll() {
        updatePdfTools()
        updateTitle()
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
        if (mode != DataManager.MODE_PDF) viewer.stopChoosing()
        val choosing = mode == DataManager.MODE_PDF && viewer.choosing
        pdfTools.visibility = if (mode == DataManager.MODE_PDF && !choosing) View.VISIBLE else View.GONE
        pdfChooseTools.visibility = if (choosing) View.VISIBLE else View.GONE
        if (choosing) toolbars.forEach { it.update(force = true) }
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
        val sel = canvas.selectedItem
        for (v in selectionTools) v.isEnabled = sel != null
        val picture = sel != null && !sel.isNote
        for (v in pictureTools) v.isEnabled = picture
        btnPaste.isEnabled = DataManager.clipboard != null || !compact
        val hasItems = DataManager.items.isNotEmpty()
        btnArrange.isEnabled = hasItems
        btnFit.isEnabled = hasItems
        btnBoardUndo.isEnabled = DataManager.canUndo
        btnBoardRedo.isEnabled = DataManager.canRedo
        val cropping = canvas.cropItem != null
        btnCrop.isEnabled = picture || cropping
        btnCrop.isSelected = cropping
        btnPicker.isEnabled = hasItems || canvas.picking
        btnPicker.isSelected = canvas.picking
    }

    private fun updateTimer() {
        val practice = DataManager.mode == DataManager.MODE_PRACTICE
        val n = DataManager.practice.size
        val showHud = if (practice && n > 0) View.VISIBLE else View.GONE
        if (hud.visibility != showHud) hud.visibility = showHud
        if (pbTimer.visibility != showHud) pbTimer.visibility = showHud
        btnInterval.setTextIfChanged(PracticeTimer.label)
        btnClass.isSelected = PracticeTimer.plan != null
        btnMemory.isSelected = PracticeTimer.memory
        val playIcon = if (PracticeTimer.running) R.drawable.ic_pause else R.drawable.ic_play
        if (btnPlay.tag != playIcon) {
            btnPlay.tag = playIcon
            btnPlay.setImageResource(playIcon)
        }
        if (n == 0) return
        tvCountdown.setTextIfChanged(PracticeTimer.text)
        val i = DataManager.practiceIndex + 1
        val plan = PracticeTimer.plan
        tvPose.setTextIfChanged(
            when {
                plan != null -> if (compact) "${PracticeTimer.planPos + 1}/${plan.size}" else "Class ${PracticeTimer.planPos + 1} of ${plan.size}"
                PracticeTimer.covered -> if (compact) "Memory" else "Draw from memory"
                compact -> "$i/$n"
                else -> "Pose $i of $n"
            }
        )
        pbTimer.progress = PracticeTimer.progress
        tvCountdown.alpha = if (PracticeTimer.running) 1f else 0.55f
    }

    private fun updateStatus() {
        val status = DataManager.status
        when {
            status != null -> {
                statusChip.visibility = View.VISIBLE
                statusSpinner.visibility = View.VISIBLE
                val canStop = DataManager.statusStop != null
                btnUndo.visibility = if (canStop) View.VISIBLE else View.GONE
                if (canStop) (btnUndo as? TextView)?.setTextIfChanged("STOP")
                tvStatus.setTextIfChanged(status)
            }
            undoText != null -> {
                statusChip.visibility = View.VISIBLE
                statusSpinner.visibility = View.GONE
                btnUndo.visibility = View.VISIBLE
                (btnUndo as? TextView)?.setTextIfChanged(root.context.getString(R.string.undo))
                tvStatus.setTextIfChanged(undoText ?: "")
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
            emptyLink?.text = "Open a saved board"
            emptyLink?.setOnClickListener { host.openBoardFile() }
        }
    }

    // ---------------------------------------------------------------- Actions

    private fun editSelected(change: (RefBoardItem) -> Unit) {
        val item = canvas.selectedItem
        if (item == null) {
            host.toast("Tap a picture first")
            return
        }
        change(item)
        DataManager.boardChanged()
    }

    /** Changes [item] (looked up again, in case undo replaced it meanwhile). */
    private fun editItem(item: RefBoardItem, change: (RefBoardItem) -> Unit) {
        val it = DataManager.items.firstOrNull { i -> i.id == item.id } ?: return
        change(it)
        DataManager.boardChanged()
    }

    private fun undo() {
        canvas.finishCrop()
        if (!DataManager.undo()) host.toast("Nothing to undo")
    }

    private fun redo() {
        canvas.finishCrop()
        if (!DataManager.redo()) host.toast("Nothing to redo")
    }

    private fun copySelected() {
        val item = canvas.selectedItem ?: return host.toast("Tap a picture first")
        DataManager.clipboard = item.duplicate()
        updateSelectionTools()
        host.toast(if (item.isNote) "Note copied" else "Picture copied")
    }

    /** Pastes our own copied picture or note, or falls back to a picture on the system clipboard. */
    private fun paste(boardX: Float?, boardY: Float?) {
        val clip = DataManager.clipboard
        if (clip != null) {
            val (cx, cy) = if (boardX != null && boardY != null) boardX to boardY else canvas.boardCenter()
            val item = DataManager.addItem(clip.duplicate(), cx + if (boardX == null) 30f else 0f, cy + if (boardY == null) 30f else 0f)
            canvas.select(item)
            return
        }
        if (!host.pasteFromSystem()) host.toast("Nothing to paste – copy a picture first")
    }

    private fun deleteItem(item: RefBoardItem) {
        if (canvas.cropItem === item) canvas.finishCrop()
        DataManager.removeItem(item)
        showUndo(if (item.isNote) "Note deleted" else "Picture deleted")
    }

    /** Shows a message with UNDO for a few seconds. */
    private fun showUndo(text: String) {
        undoText = text
        undoVersion = DataManager.boardVersion
        main.removeCallbacks(hideUndo)
        main.postDelayed(hideUndo, 6000)
        updateStatus()
    }

    private fun undoFromMessage() {
        if (undoText == null) return
        undoText = null
        main.removeCallbacks(hideUndo)
        // Only if nothing else changed since (otherwise UNDO would take back something else).
        if (DataManager.boardVersion == undoVersion) DataManager.undo()
        updateStatus()
    }

    private fun sendToPractice(item: RefBoardItem) {
        val image = item.image ?: return
        DataManager.addPoses(listOf(Pose.Image(image)), jumpToFirst = true)
        DataManager.setMode(DataManager.MODE_PRACTICE)
    }

    // ---------------------------------------------------------------- Crop, colour picker, notes

    private fun toggleCrop() {
        if (canvas.cropItem != null) {
            canvas.finishCrop()
            return
        }
        val item = canvas.selectedItem
        if (item == null || item.isNote) return host.toast("Tap a picture first")
        startCrop(item)
    }

    private fun startCrop(item: RefBoardItem) {
        if (item.locked) editItem(item) { it.locked = false }
        val it = DataManager.items.firstOrNull { i -> i.id == item.id } ?: return
        canvas.startCrop(it)
        host.toast("Drag the edges to crop · tap outside or Crop to finish")
    }

    private fun togglePicker() {
        if (canvas.picking) {
            canvas.setPicking(false)
            return
        }
        if (DataManager.items.isEmpty()) return host.toast("Add a picture first")
        canvas.setPicking(true)
        host.toast("Touch a picture and slide to the colour, then lift your finger")
    }

    private fun colorPicked(color: Int) {
        val hex = Looks.hex(color)
        try {
            val cm = root.context.getSystemService(android.content.ClipboardManager::class.java)
            cm?.setPrimaryClip(android.content.ClipData.newPlainText("Colour", hex))
        } catch (e: Exception) {
            // the clipboard isn't essential
        }
        DataManager.toast(Looks.describe(color) + "  ·  copied")
    }

    /** A new note in the middle of the view (or at a long-pressed spot). */
    private fun addNote(at: Pair<Float, Float>?) {
        host.askText("New note", "Type your note", "", multiLine = true) { text ->
            if (text.isBlank()) return@askText
            val (cx, cy) = at ?: canvas.boardCenter()
            val note = RefBoardItem.newNote(text.trimEnd(), cx, cy)
            DataManager.addItem(note, cx, cy)
            canvas.select(note)
        }
    }

    private fun editNote(item: RefBoardItem) {
        host.askText("Edit note", "Type your note", item.note, multiLine = true) { text ->
            val it = DataManager.items.firstOrNull { i -> i.id == item.id } ?: return@askText
            if (text.isBlank()) {
                deleteItem(it)
                return@askText
            }
            val left = it.x
            val top = it.y
            it.note = text.trimEnd()
            it.sizeNote()
            it.x = left
            it.y = top
            DataManager.boardChanged()
        }
    }

    /** A small menu of choices; the current one is ticked. */
    private fun choose(x: Float, y: Float, title: String, options: List<Pair<String, Boolean>>, icon: Int, onChosen: (Int) -> Unit) {
        val rows = ArrayList<Row>()
        rows += Header(title)
        for ((i, o) in options.withIndex()) rows += Item(if (o.second) "${o.first}  ✓" else o.first, icon) { onChosen(i) }
        main.post { menu.show(x, y, rows) }
    }

    // ---------------------------------------------------------------- Practice: class, memory, history

    private fun showClassMenu(anchor: View) {
        val (x, y) = anchorBelow(anchor)
        showClassMenuAt(x, y)
    }

    private fun showClassMenuAt(x: Float, y: Float) {
        val rows = ArrayList<Row>()
        val plan = PracticeTimer.plan
        rows += Header(if (plan != null) "${PracticeTimer.planName} · pose ${PracticeTimer.planPos + 1} of ${plan.size}" else "Timed class")
        if (plan != null) rows += Item("Stop the class", R.drawable.ic_close) { PracticeTimer.stopClass() }
        for ((name, text) in PracticeTimer.CLASSES) {
            rows += Item(name, R.drawable.ic_class) { startClass(text, name) }
        }
        rows += Item("Your own class…", R.drawable.ic_class) {
            host.askText("Your own class", "e.g. 10x30s, 5x1m, 2x5m", PracticeTimer.lastCustomPlan.ifEmpty { "10x30s, 5x1m, 2x5m" }) { text ->
                if (PracticeTimer.parsePlan(text) == null) {
                    host.toast("Type poses like 10x30s, 5x1m, 2x5m")
                } else {
                    PracticeTimer.lastCustomPlan = text.trim()
                    startClass(text, "Your class")
                }
            }
        }
        rows += Item(if (PracticeTimer.memory) "Memory mode  ✓" else "Memory mode", R.drawable.ic_memory) { toggleMemory() }
        rows += Item("Practice history", R.drawable.ic_chart) { host.showHistory() }
        menu.show(x, y, rows)
    }

    private fun startClass(planText: String, name: String) {
        val plan = PracticeTimer.parsePlan(planText) ?: return
        if (DataManager.practice.isEmpty() && !DataManager.practiceWithBoardImages()) {
            host.toast("Add a PDF or pictures to practise with first")
            return
        }
        DataManager.setMode(DataManager.MODE_PRACTICE)
        PracticeTimer.startClass(plan, name)
        host.toast("$name · ${plan.size} poses · ${PracticeTimer.planText(plan)}")
    }

    private fun toggleMemory() {
        val on = !PracticeTimer.memory
        PracticeTimer.setMemory(on)
        host.toast(if (on) "Memory mode: each pose hides when its time is up – draw it from memory" else "Memory mode off")
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
            rows += Item("PDF pages", R.drawable.ic_pdf) { host.pickPdf(Importer.Target.BOARD) }
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
            rows += Item("Add pages to the board…", R.drawable.ic_image) { startChoosing(listOf(page)) }
            rows += Item("Practise from page ${page + 1}", R.drawable.ic_timer) { practiseFrom(page) }
            rows += Item("Fit width / whole page", R.drawable.ic_fit) { viewer.toggleFit() }
            rows += Item(if (viewer.spread) "Two pages side by side  ✓" else "Two pages side by side", R.drawable.ic_spread) {
                viewer.setSpread(!viewer.spread)
            }
            rows += Item(if (viewer.stripShown) "Page list  ✓" else "Page list", R.drawable.ic_pages) { viewer.setStripShown(!viewer.stripShown) }
            if (PdfSearch.supported) rows += Item("Find text…", R.drawable.ic_search) { openSearch() }
            rows += Item("Snip part of a page to the board", R.drawable.ic_snip) { toggleSnip() }
            rows += Item(if (viewer.isBookmarked(page)) "Remove bookmark (page ${page + 1})" else "Bookmark page ${page + 1}", R.drawable.ic_bookmark) {
                toggleBookmark(page)
            }
            if (doc.bookmarks.isNotEmpty()) {
                rows += Header("Bookmarks")
                for (b in doc.bookmarks.take(12)) rows += Item("Page ${b + 1}", R.drawable.ic_bookmark) { viewer.goToPage(b) }
            }
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
        val rows = ArrayList<Row>()
        rows += Header("Picture")
        rows += Item("Copy", R.drawable.ic_copy) { copySelected() }
        rows += Item("Flip horizontally", R.drawable.ic_flip) { editItem(item) { it.flipped = !it.flipped } }
        rows += Item("Rotate right", R.drawable.ic_rotate) { editItem(item) { it.rotateCW() } }
        rows += Item("Rotate left", R.drawable.ic_rotate_left) { editItem(item) { it.rotateCCW() } }
        rows += Item("Crop", R.drawable.ic_crop) { startCrop(item) }
        if (item.crop != null) rows += Item("Show the whole picture", R.drawable.ic_fit) { editItem(item) { it.applyCrop(null) } }
        rows += Header("Study")
        rows += Item(if (item.grayscale) "Show in colour" else "Black & white", R.drawable.ic_bw) { editItem(item) { it.grayscale = !it.grayscale } }
        rows += Item(if (item.values > 0) "Value steps (${item.values})…" else "Value steps…", R.drawable.ic_values) {
            val opts = listOf(0, 2, 3, 4, 5)
            choose(x, y, "Value steps", opts.map { (if (it == 0) "Off" else "$it greys") to (it == item.values) }, R.drawable.ic_values) { i ->
                editItem(item) { it.values = opts[i] }
            }
        }
        rows += Item(if (item.blur) "Squint (blur)  ✓" else "Squint (blur)", R.drawable.ic_squint) { editItem(item) { it.blur = !it.blur } }
        rows += Item(if (item.grid > 0) "Grid (${item.grid}×${item.grid})…" else "Grid…", R.drawable.ic_grid) {
            val opts = listOf(0, 2, 3, 4, 6, 8)
            choose(x, y, "Grid over the picture", opts.map { (if (it == 0) "Off" else "$it × $it") to (it == item.grid) }, R.drawable.ic_grid) { i ->
                editItem(item) { it.grid = opts[i] }
            }
        }
        rows += Item("Opacity (${Math.round(item.opacity * 100)}%)…", R.drawable.ic_opacity) { chooseOpacity(item, x, y) }
        rows += Header("Board")
        rows += Item(if (item.locked) "Unlock" else "Lock in place", R.drawable.ic_lock) { editItem(item) { it.locked = !it.locked } }
        if (host.canFloat) rows += Item("Float this picture over other apps", R.drawable.ic_pin) { host.floatItem(item) }
        rows += Item("Zoom to this picture", R.drawable.ic_zoom) { canvas.fitItem(item) }
        rows += Item("Send to practice", R.drawable.ic_timer) { sendToPractice(item) }
        rows += Item("Reset size, rotation and looks", R.drawable.ic_reset) { editItem(item) { it.resetTransforms() } }
        rows += Item("Delete", R.drawable.ic_delete, danger = true) { deleteItem(item) }
        menu.show(x, y, rows)
    }

    private fun showNoteMenu(item: RefBoardItem, x: Float, y: Float) {
        menu.show(
            x, y, listOf(
                Header("Note"),
                Item("Edit note", R.drawable.ic_note) { editNote(item) },
                Item("Copy", R.drawable.ic_copy) { copySelected() },
                Item("Opacity (${Math.round(item.opacity * 100)}%)…", R.drawable.ic_opacity) { chooseOpacity(item, x, y) },
                Item(if (item.locked) "Unlock" else "Lock in place", R.drawable.ic_lock) { editItem(item) { it.locked = !it.locked } },
                Item("Zoom to this note", R.drawable.ic_zoom) { canvas.fitItem(item) },
                Item("Delete", R.drawable.ic_delete, danger = true) { deleteItem(item) }
            )
        )
    }

    private fun chooseOpacity(item: RefBoardItem, x: Float, y: Float) {
        val opts = listOf(1f, 0.75f, 0.5f, 0.25f)
        choose(x, y, "Opacity", opts.map { "${Math.round(it * 100)}%" to (abs(it - item.opacity) < 0.01f) }, R.drawable.ic_opacity) { i ->
            editItem(item) { it.opacity = opts[i] }
        }
    }

    private fun showBoardMenu(x: Float, y: Float, pasteAt: Pair<Float, Float>?) {
        val hasItems = DataManager.items.isNotEmpty()
        val rows = ArrayList<Row>()
        rows += boardFileRows()
        rows += Header("Board")
        rows += Item("Paste", R.drawable.ic_paste, enabled = DataManager.clipboard != null || !compact) {
            paste(pasteAt?.first, pasteAt?.second)
        }
        rows += Item("Add images", R.drawable.ic_image) { host.pickImages(Importer.Target.BOARD) }
        rows += Item("Add PDF pages", R.drawable.ic_pdf) { host.pickPdf(Importer.Target.BOARD) }
        if (host.canPickFolder) rows += Item("Import folder", R.drawable.ic_folder) { host.pickFolder(Importer.Target.BOARD) }
        rows += Item("Add a note", R.drawable.ic_note) { addNote(pasteAt) }
        rows += Item("Undo", R.drawable.ic_undo, enabled = DataManager.canUndo) { undo() }
        rows += Item("Redo", R.drawable.ic_redo, enabled = DataManager.canRedo) { redo() }
        rows += Item("Fit everything", R.drawable.ic_fit, enabled = hasItems) { canvas.fitAll() }
        rows += Item("Arrange in rows", R.drawable.ic_arrange, enabled = hasItems) { DataManager.autoArrange() }
        rows += Item("Background…", R.drawable.ic_palette) {
            val names = listOf("Dark", "Neutral grey", "Light")
            choose(x, y, "Board background", names.mapIndexed { i, n -> n to (i == DataManager.background) }, R.drawable.ic_palette) { i ->
                DataManager.setBackground(i)
            }
        }
        rows += Item("Export board as a picture (PNG)", R.drawable.ic_export, enabled = hasItems) {
            canvas.finishCrop()
            host.createExportFile(DataManager.boardTitle)
        }
        rows += Item("Practise with these images", R.drawable.ic_timer, enabled = hasItems) {
            DataManager.practiceWithBoardImages()
            DataManager.setMode(DataManager.MODE_PRACTICE)
        }
        rows += host.extraMenuItems()
        rows += Item("Clear board", R.drawable.ic_delete, danger = true, enabled = hasItems, confirm = "Tap again to clear the board") {
            canvas.finishCrop()
            DataManager.clearBoard()
            showUndo("Board cleared")
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
        rows += Item(if (PracticeTimer.plan != null) "Class…  (running)" else "Timed class…", R.drawable.ic_class) {
            main.post { showClassMenuAt(x, y) }
        }
        rows += Item(if (PracticeTimer.memory) "Memory mode  ✓" else "Memory mode", R.drawable.ic_memory) { toggleMemory() }
        rows += Item("Practice history", R.drawable.ic_chart) { host.showHistory() }
        rows += Item("Back to board", R.drawable.ic_image) { DataManager.setMode(DataManager.MODE_BOARD) }
        rows += host.extraMenuItems()
        rows += Item("Clear practice list", R.drawable.ic_delete, danger = true, enabled = hasPoses, confirm = "Tap again to clear practice") {
            DataManager.clearPractice()
        }
        menu.show(x, y, rows)
    }

    // ---------------------------------------------------------------- PDF reader tools

    private fun updatePdfTools() {
        btnSpread.isSelected = viewer.spread
        btnPages.isSelected = viewer.stripShown
        btnSnip.isSelected = viewer.snipping
        btnBookmark.isSelected = viewer.isBookmarked(viewer.currentPage)
        val hasDoc = DataManager.currentDoc != null
        for (v in listOf(btnSpread, btnPages, btnSearch, btnSnip, btnBookmark)) v.isEnabled = hasDoc
    }

    private fun toggleSnip() {
        if (DataManager.currentDoc == null) return host.toast("Open a PDF first")
        val on = !viewer.snipping
        viewer.setSnipping(on)
        if (on) host.toast("Drag a box around the part you want on the board")
    }

    private fun toggleBookmark(page: Int) {
        if (DataManager.currentDoc == null) return host.toast("Open a PDF first")
        val on = viewer.toggleBookmark(page)
        updatePdfTools()
        host.toast(if (on) "Page ${page + 1} bookmarked" else "Bookmark removed")
    }

    // Search: a small bar at the top with the words, the match count, previous / next and close.
    private var searchBar: View? = null
    private var tvSearchQuery: TextView? = null
    private var tvSearchCount: TextView? = null
    private var searchQuery = ""
    private var searchDoc: ViewerDoc? = null
    private var searching = false

    private fun openSearch() {
        val doc = DataManager.currentDoc ?: return host.toast("Open a PDF first")
        if (!PdfSearch.supported) return host.toast("Finding text needs Android 15 or newer")
        host.askText("Find in “${doc.title}”", "Word or phrase", searchQuery) { q ->
            if (q.isNotBlank()) runSearch(doc, q.trim())
        }
    }

    private fun runSearch(doc: ViewerDoc, q: String) {
        searchQuery = q
        searchDoc = doc
        searching = true
        showSearchBar()
        tvSearchQuery?.text = "“$q”"
        viewer.clearHits()
        updateSearchCount()
        var first = true
        PdfSearch.search(doc.docId, q, onHits = { batch ->
            if (searchDoc === doc && DataManager.currentDoc === doc) {
                viewer.addHits(batch)
                if (first) {
                    first = false
                    viewer.showHit(0)
                }
                updateSearchCount()
            }
        }, onDone = { n ->
            if (searchDoc === doc) {
                searching = false
                if (n < 0) {
                    tvSearchCount?.text = "Can't search this PDF"
                } else {
                    updateSearchCount()
                }
            }
        })
    }

    private fun updateSearchCount() {
        val n = viewer.hitCount
        tvSearchCount?.text = when {
            n == 0 && searching -> "Searching…"
            n == 0 -> "Not found"
            else -> "${viewer.hitIndex + 1} of $n" + if (searching) "…" else ""
        }
    }

    private fun showSearchBar() {
        val bar = searchBar ?: buildSearchBar().also { searchBar = it }
        val d = root.resources.displayMetrics.density
        (bar.layoutParams as? FrameLayout.LayoutParams)?.let {
            it.topMargin = viewer.paddingTop + (6 * d).toInt()
            bar.layoutParams = it
        }
        bar.visibility = View.VISIBLE
    }

    private fun closeSearch() {
        if (searchDoc == null && searchBar?.visibility != View.VISIBLE) return
        PdfSearch.cancel()
        searching = false
        searchDoc = null
        viewer.clearHits()
        searchBar?.visibility = View.GONE
    }

    private fun buildSearchBar(): View {
        val ctx = root.context
        val d = ctx.resources.displayMetrics.density
        fun dp(v: Int) = (v * d).toInt()
        val bar = android.widget.LinearLayout(ctx).apply {
            orientation = android.widget.LinearLayout.HORIZONTAL
            gravity = android.view.Gravity.CENTER_VERTICAL
            setBackgroundResource(R.drawable.bg_chip)
            elevation = 8 * d
            setPadding(dp(10), dp(2), dp(4), dp(2))
            isClickable = true
        }
        val tint = android.content.res.ColorStateList.valueOf(ctx.getColor(R.color.text_primary))
        bar.addView(ImageView(ctx).apply {
            setImageResource(R.drawable.ic_search)
            imageTintList = android.content.res.ColorStateList.valueOf(ctx.getColor(R.color.accent))
        }, android.widget.LinearLayout.LayoutParams(dp(18), dp(18)))
        val query = TextView(ctx).apply {
            setTextColor(ctx.getColor(R.color.text_primary))
            textSize = 13f
            maxWidth = dp(if (compact) 90 else 220)
            isSingleLine = true
            ellipsize = android.text.TextUtils.TruncateAt.END
            setPadding(dp(8), dp(8), dp(8), dp(8))
            setOnClickListener { openSearch() }
        }
        bar.addView(query)
        val count = TextView(ctx).apply {
            setTextColor(ctx.getColor(R.color.text_muted))
            textSize = 12f
            setPadding(dp(2), 0, dp(6), 0)
        }
        bar.addView(count)
        fun button(icon: Int, desc: String, action: () -> Unit) = ImageButton(ctx).apply {
            setImageResource(icon)
            imageTintList = tint
            setBackgroundResource(R.drawable.bg_tool)
            contentDescription = desc
            setOnClickListener { action() }
        }
        val size = android.widget.LinearLayout.LayoutParams(dp(38), dp(38))
        bar.addView(button(R.drawable.ic_page_up, "Previous match") { viewer.showHit(viewer.hitIndex - 1); updateSearchCount() }, size)
        bar.addView(button(R.drawable.ic_page_down, "Next match") { viewer.showHit(viewer.hitIndex + 1); updateSearchCount() }, size)
        bar.addView(button(R.drawable.ic_close, "Close search") { closeSearch() }, size)
        tvSearchQuery = query
        tvSearchCount = count
        (menuHostView as FrameLayout).addView(bar, FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT,
            android.view.Gravity.TOP or android.view.Gravity.CENTER_HORIZONTAL
        ))
        return bar
    }

    // ---------------------------------------------------------------- Board files

    private fun updateTitle() {
        val t = tvTitle ?: return
        val unsaved = DataManager.boardDirty && DataManager.items.isNotEmpty()
        t.setTextIfChanged(DataManager.boardTitle + if (unsaved) "  •" else "")
    }

    /** New / Open / Save / Save as / Recent boards. */
    private fun boardFileRows(): List<Row> {
        val ctx = root.context
        val hasItems = DataManager.items.isNotEmpty()
        val rows = ArrayList<Row>()
        rows += Header(DataManager.boardTitle + if (DataManager.boardDirty && hasItems) "  •  not saved" else "")
        rows += Item("New board", R.drawable.ic_add) { newBoard() }
        rows += Item("Open board…", R.drawable.ic_folder) { host.openBoardFile() }
        rows += Item("Save board", R.drawable.ic_copy, enabled = hasItems) { saveBoard() }
        rows += Item("Save board as…", R.drawable.ic_copy, enabled = hasItems) { host.createBoardFile(DataManager.boardTitle) }
        val others = BoardFiles.recent(ctx).filter { it.uri != DataManager.boardUri }.take(6)
        if (others.isNotEmpty()) {
            rows += Header("Recent boards")
            for (r in others) rows += Item(r.name, R.drawable.ic_history) { openBoard(Uri.parse(r.uri)) }
        }
        return rows
    }

    private fun showBoardFileMenu(anchor: View) {
        val (x, y) = anchorBelow(anchor)
        menu.show(x, y, boardFileRows())
    }

    private fun saveBoard() {
        if (DataManager.boardUri == null) host.createBoardFile(DataManager.boardTitle)
        else BoardFiles.saveCurrent(root.context)
    }

    private fun newBoard() = beforeSwitch {
        DataManager.replaceBoard(emptyList(), null, "")
        DataManager.setMode(DataManager.MODE_BOARD)
        host.toast("New board")
    }

    /**
     * Opens a board file; called after the user picked one or tapped a recent board.
     * [fromOtherApp]: opened from Files, a chat or a drop, so RefPad may not be allowed to save into it.
     */
    fun openBoard(uri: Uri, fromOtherApp: Boolean = false) {
        val ctx = root.context
        if (fromOtherApp) {
            beforeSwitch { BoardFiles.load(ctx, uri, fromOtherApp = true) }
            return
        }
        if (uri.toString() == DataManager.boardUri) {
            // The board that is showing: bring back the saved version.
            val hasItems = DataManager.items.isNotEmpty()
            if (hasItems && !DataManager.boardDirty) {
                DataManager.setMode(DataManager.MODE_BOARD)
                host.toast("“${DataManager.boardTitle}” is already open")
            } else if (hasItems) {
                val (x, y) = centre()
                menu.show(x, y, listOf(
                    Header("Go back to the saved “${DataManager.boardTitle}”?"),
                    Item("Open the saved version", R.drawable.ic_history, confirm = "Tap again – your newest changes go") {
                        BoardFiles.load(ctx, uri)
                    }
                ))
            } else {
                BoardFiles.load(ctx, uri)
            }
            return
        }
        beforeSwitch { BoardFiles.load(ctx, uri) }
    }

    /** Makes sure the current board is safe before another one is shown, then runs [then]. */
    private fun beforeSwitch(then: () -> Unit) {
        if (DataManager.items.isEmpty() || !DataManager.boardDirty) return then()
        if (DataManager.boardUri != null) {
            // A board with a file saves itself first; if that fails, stay on it so nothing is lost.
            BoardFiles.saveCurrent(root.context, quiet = true) { error ->
                if (error == null) then() else host.toast("$error Your board is still here.")
            }
            return
        }
        val (x, y) = centre()
        menu.show(x, y, listOf(
            Header("Save “${DataManager.boardTitle}” first?"),
            Item("Save as…", R.drawable.ic_copy) {
                BoardFiles.afterSaveAs = then
                host.createBoardFile(DataManager.boardTitle)
            },
            Item("Don't save", R.drawable.ic_delete, danger = true, confirm = "Tap again – its pictures will be gone") { then() }
        ))
    }

    private fun centre(): Pair<Float, Float> {
        val d = root.resources.displayMetrics.density
        return menuHostView.width / 2f - 130f * d to menuHostView.height / 3f
    }

    // ---------------------------------------------------------------- Choosing PDF pages for the board

    private fun showToBoardMenu(anchor: View) {
        val doc = DataManager.currentDoc ?: return host.toast("Open a PDF first")
        val (x, y) = anchorBelow(anchor)
        val page = viewer.currentPage
        menu.show(x, y, listOf(
            Header("Add to the board"),
            Item("This page (${page + 1})", R.drawable.ic_image) { pageToBoard(page) },
            Item("All ${doc.pageCount} pages", R.drawable.ic_arrange) { startChoosing(null) },
            Item("Choose pages…", R.drawable.ic_pdf) { startChoosing(listOf(page)) }
        ))
    }

    /** Starts choosing pages in the reader: all of them ([pages] null) or just [pages]. */
    private fun startChoosing(pages: List<Int>?) {
        if (DataManager.currentDoc == null) return
        viewer.startChoosing(all = pages == null)
        if (pages != null) viewer.choose(pages)
        updateMode()
    }

    private fun stopChoosing() {
        viewer.stopChoosing()
        updateMode()
    }

    private fun updateChooseCount(n: Int) {
        val total = viewer.pageCount
        tvChooseCount.setTextIfChanged(if (compact) "$n/$total" else "$n of $total")
        root.findViewById<View>(R.id.btn_choose_add)?.isEnabled = n > 0
    }

    private fun askPageNumbers() {
        val total = viewer.pageCount
        host.askText("Pages to add", "e.g. 1-5, 8, 12-20", pagesText(viewer.chosenPages())) { text ->
            val pages = parsePages(text, total)
            if (pages == null) host.toast("Type page numbers between 1 and $total, like 1-5, 8, 12-20")
            else viewer.choose(pages)
        }
    }

    private fun addChosenPages() {
        val doc = DataManager.currentDoc ?: return
        val pages = viewer.chosenPages()
        if (pages.isEmpty()) return host.toast("Tap pages to choose them first")
        viewer.stopChoosing()
        updateMode()
        Importer.pagesToBoard(root.context, doc, pages)
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

/** "1-5, 8, 12-" -> 0-based page numbers; null if the text can't be understood. */
fun parsePages(text: String, count: Int): List<Int>? {
    val pages = sortedSetOf<Int>()
    for (part in text.split(',', ' ', ';').map { it.trim() }.filter { it.isNotEmpty() }) {
        val m = Regex("""^(\d*)\s*[-–]\s*(\d*)$""").find(part)
        var a: Int
        var b: Int
        if (m != null && (m.groupValues[1].isNotEmpty() || m.groupValues[2].isNotEmpty())) {
            a = m.groupValues[1].toIntOrNull() ?: 1
            b = m.groupValues[2].toIntOrNull() ?: count
            if (a > b) a = b.also { b = a }
        } else {
            a = part.toIntOrNull() ?: return null
            b = a
        }
        if (a < 1 || a > count) return null
        for (p in a..minOf(b, count)) pages.add(p - 1)
    }
    return pages.toList()
}

/** [0,1,2,3,7] -> "1-4, 8" */
fun pagesText(pages: List<Int>): String {
    val out = ArrayList<String>()
    var start = -1
    var prev = -2
    for (p in pages.sorted() + listOf(Int.MIN_VALUE)) {
        if (p == prev + 1) {
            prev = p
            continue
        }
        if (start >= 0) out += if (prev > start) "${start + 1}-${prev + 1}" else "${start + 1}"
        start = p
        prev = p
    }
    return out.joinToString(", ")
}
