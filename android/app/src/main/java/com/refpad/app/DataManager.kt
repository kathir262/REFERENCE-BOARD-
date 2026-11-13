package com.refpad.app

import android.content.Context
import android.graphics.PointF
import android.graphics.RectF
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import kotlin.math.max
import kotlin.math.sqrt

/**
 * The one shared copy of the board and the practice session.
 * The full-screen app and the floating window both draw from here, so they always agree,
 * and the state is saved to disk so it survives the app being closed by Android.
 *
 * Only use this from the main thread.
 */
object DataManager {
    const val MODE_BOARD = 0
    const val MODE_PRACTICE = 1
    const val MODE_PDF = 2
    private const val MAX_RECENT_DOCS = 10

    interface Listener {
        fun onBoardChanged() {}
        fun onPracticeChanged() {}
        fun onModeChanged() {}
        fun onStatusChanged() {}
        fun onFitRequested() {}
        fun onDocsChanged() {}
        fun onBoardFileChanged() {}
        /** A PDF was added for the board: let the user choose its pages in the reader. */
        fun onChoosePages(doc: ViewerDoc) {}
    }

    private val main = Handler(Looper.getMainLooper())
    private val listeners = ArrayList<Listener>()
    private var initialized = false

    val items = ArrayList<RefBoardItem>()
    val practice = ArrayList<Pose>()

    /** PDFs opened in the viewer, most recent first. The first one is the one on screen. */
    val docs = ArrayList<ViewerDoc>()
    val currentDoc: ViewerDoc? get() = docs.firstOrNull()

    var practiceIndex = 0
        private set
    var practiceFlipped = false
        private set
    var practiceGrayscale = false
        private set
    var mode = MODE_BOARD
        private set

    /** Internal copy/paste clipboard: a copy of the item (it shares the picture, not a copy of the pixels). */
    var clipboard: RefBoardItem? = null

    // ---------------------------------------------------------------- Board background
    const val BG_DARK = 0
    const val BG_GREY = 1
    const val BG_LIGHT = 2
    /** Board (and practice) background: dark, neutral grey or light. */
    var background = BG_DARK
        private set

    fun setBackground(bg: Int) {
        if (bg == background) return
        background = bg
        appContext?.getSharedPreferences("refpad", Context.MODE_PRIVATE)?.edit()?.putInt("board_bg", bg)?.apply()
        each { it.onBoardChanged() }
        each { it.onPracticeChanged() }
    }

    /** Short progress text such as "Importing image 3 of 10", or null when idle. */
    var status: String? = null
        private set
    /** Stops the job the status describes (shown as a STOP button), or null. */
    var statusStop: (() -> Unit)? = null
        private set

    /** False until the saved board has been read back from disk. */
    var restored = false
        private set

    // ---------------------------------------------------------------- Board file
    /** The .refpad file this board belongs to (a content:// address), or null for an untitled board. */
    var boardUri: String? = null
        private set
    var boardName: String = ""
        private set
    /** Changed since it was last saved to its file. */
    var boardDirty = false
        private set
    /** Goes up with every change, so a save that started before a change doesn't count as saving it. */
    var boardVersion = 0
        private set
    val boardTitle: String get() = boardName.ifEmpty { "Untitled board" }
    /** Goes up whenever a different board is shown, so imports into the old one stop. */
    var boardEpoch = 0
        private set
    private var appContext: Context? = null
    private val autoSave = Runnable { appContext?.let { BoardFiles.saveCurrent(it, quiet = true) } }

    fun init(context: Context) {
        if (initialized) return
        initialized = true
        appContext = context.applicationContext
        background = context.getSharedPreferences("refpad", Context.MODE_PRIVATE).getInt("board_bg", BG_DARK)
            .coerceIn(BG_DARK, BG_LIGHT)
        Storage.init(context.applicationContext)
        PracticeTimer.init(context.applicationContext)
        PracticeHistory.init(context.applicationContext)
        Storage.loadAsync { state ->
            if (state != null) {
                val hadPractice = practice.isNotEmpty()
                items.addAll(0, state.items)
                practice.addAll(0, state.practice)
                practiceIndex = if (hadPractice) practiceIndex + state.practice.size
                else state.practiceIndex.coerceIn(0, max(0, practice.size - 1))
                for (d in state.docs) if (docs.none { it.docId == d.docId }) docs.add(d)
                boardUri = state.boardUri
                boardName = state.boardName
                boardDirty = state.boardDirty
                // Reopen the mode you were in, if it still has something to show.
                if (mode == MODE_BOARD && state.mode != MODE_BOARD &&
                    (state.mode != MODE_PDF || docs.isNotEmpty()) && (state.mode != MODE_PRACTICE || practice.isNotEmpty())
                ) mode = state.mode
            }
            restored = true
            forgetHistory()
            each { it.onBoardChanged() }
            each { it.onPracticeChanged() }
            each { it.onDocsChanged() }
            each { it.onModeChanged() }
            each { it.onStatusChanged() }
            each { it.onBoardFileChanged() }
            requestFit()
            // Anything imported while we were still loading needs saving now.
            if (state == null || items.size != state.items.size || practice.size != state.practice.size) scheduleSave()
        }
    }

    fun addListener(l: Listener) {
        if (!listeners.contains(l)) listeners.add(l)
    }

    fun removeListener(l: Listener) {
        listeners.remove(l)
    }

    private inline fun each(f: (Listener) -> Unit) {
        for (l in listeners.toTypedArray()) f(l)
    }

    // ---------------------------------------------------------------- Board

    fun addToBoard(image: RefImage, centerX: Float? = null, centerY: Float? = null): RefBoardItem =
        addItem(RefBoardItem(image), centerX, centerY)

    /** Adds a picture or note: with its middle at (centerX, centerY), or in the first free spot. */
    fun addItem(item: RefBoardItem, centerX: Float? = null, centerY: Float? = null): RefBoardItem {
        if (centerX != null && centerY != null) {
            item.x = centerX - item.width / 2f
            item.y = centerY - item.height / 2f
        } else {
            placeAfterLast(item)
        }
        items.add(item)
        // Pictures arriving one after another from the same import are one undo step.
        boardChanged(merge = "add")
        return item
    }

    /** Puts a new image in the first free spot, filling rows left to right, so nothing overlaps. */
    private fun placeAfterLast(item: RefBoardItem) {
        if (items.isEmpty()) {
            item.moveBoundsTo(0f, 0f)
            return
        }
        val gap = 40f
        val w = item.effectiveWidth
        val h = item.effectiveHeight
        val rects = items.map { RectF().also { r -> it.boundsInto(r) } }
        val minLeft = rects.minOf { it.left }
        val maxBottom = rects.maxOf { it.bottom }
        // Rows grow with the board so many images form a wide grid that suits a landscape tablet.
        val area = rects.sumOf { (it.width() * it.height()).toDouble() } + w * h
        val rowLimit = max(max(1200f, w), rowWidthFor(area))
        val candidates = ArrayList<PointF>(rects.size * 2)
        for (r in rects) {
            candidates.add(PointF(r.right + gap, r.top))
            candidates.add(PointF(r.left, r.bottom + gap))
        }
        candidates.sortWith(compareBy<PointF>({ it.y }, { it.x }))
        val test = RectF()
        for (c in candidates) {
            if (c.x + w > minLeft + rowLimit) continue
            test.set(c.x - gap / 2f, c.y - gap / 2f, c.x + w + gap / 2f, c.y + h + gap / 2f)
            if (rects.none { RectF.intersects(it, test) }) {
                item.moveBoundsTo(c.x, c.y)
                return
            }
        }
        item.moveBoundsTo(minLeft, maxBottom + gap)
    }

    fun removeItem(item: RefBoardItem) {
        if (items.remove(item)) boardChanged()
    }

    fun clearBoard() {
        items.clear()
        boardChanged()
    }

    /** Draw this item on top of the others (touching a picture does this; it is not an undo step of its own). */
    fun bringToFront(item: RefBoardItem) {
        if (items.lastOrNull() === item) return
        if (items.remove(item)) {
            items.add(item)
            shot = take()
            each { it.onBoardChanged() }
            markDirty()
            scheduleSave()
        }
    }

    /** Call while an item is being dragged/resized: redraws everywhere without writing to disk. */
    fun itemsMoved() = each { it.onBoardChanged() }

    /**
     * Call after any finished change to the board: it becomes an undo step, then redraws and saves.
     * Changes with the same [merge] key less than 2 seconds apart are one undo step.
     */
    fun boardChanged(merge: String? = null) {
        record(merge)
        each { it.onBoardChanged() }
        markDirty()
        scheduleSave()
    }

    // ---------------------------------------------------------------- Undo / redo

    private const val MAX_UNDO = 40
    private val undoStack = ArrayList<List<RefBoardItem>>()
    private val redoStack = ArrayList<List<RefBoardItem>>()
    /** The board as it was after the last change (what undo goes back to). */
    private var shot: List<RefBoardItem> = emptyList()
    private var lastMerge: String? = null
    private var lastMergeAt = 0L

    val canUndo: Boolean get() = undoStack.isNotEmpty()
    val canRedo: Boolean get() = redoStack.isNotEmpty()

    private fun take(): List<RefBoardItem> = items.map { it.snapshot() }

    private fun record(merge: String?) {
        val now = SystemClock.uptimeMillis()
        val same = merge != null && merge == lastMerge && now - lastMergeAt < 2000
        if (!same) {
            undoStack.add(shot)
            if (undoStack.size > MAX_UNDO) undoStack.removeAt(0)
        }
        lastMerge = merge
        lastMergeAt = now
        redoStack.clear()
        shot = take()
    }

    private fun forgetHistory() {
        undoStack.clear()
        redoStack.clear()
        lastMerge = null
        shot = take()
    }

    fun undo(): Boolean {
        if (undoStack.isEmpty()) return false
        redoStack.add(take())
        restore(undoStack.removeAt(undoStack.size - 1))
        return true
    }

    fun redo(): Boolean {
        if (redoStack.isEmpty()) return false
        undoStack.add(take())
        restore(redoStack.removeAt(redoStack.size - 1))
        return true
    }

    private fun restore(snap: List<RefBoardItem>) {
        items.clear()
        items.addAll(snap.map { it.snapshot() })
        shot = take()
        lastMerge = null
        each { it.onBoardChanged() }
        markDirty()
        scheduleSave()
    }

    private fun markDirty() {
        boardVersion++
        if (!boardDirty) {
            boardDirty = true
            each { it.onBoardFileChanged() }
        }
        // A board with a file saves itself a few seconds after the last change
        // (Android may close the app in the background at any time).
        if (boardUri != null) {
            main.removeCallbacks(autoSave)
            main.postDelayed(autoSave, 4000)
        }
    }

    /**
     * The board was written to [uri]; it counts as saved unless it changed while being written.
     * With [adopt] ("Save as") the board now belongs to that file.
     */
    fun boardSaved(uri: String, name: String, version: Int, adopt: Boolean) {
        if (!adopt && boardUri != uri) return
        boardUri = uri
        boardName = name
        boardDirty = version != boardVersion
        each { it.onBoardFileChanged() }
        scheduleSave()
    }

    /** Shows another board: one opened from a file, or a new empty one ([dirty]: not saved anywhere yet). */
    fun replaceBoard(newItems: List<RefBoardItem>, uri: String?, name: String, dirty: Boolean = false) {
        main.removeCallbacks(autoSave)
        boardEpoch++
        items.clear()
        items.addAll(newItems)
        forgetHistory()
        boardUri = uri
        boardName = name
        boardDirty = dirty
        boardVersion++
        each { it.onBoardChanged() }
        each { it.onBoardFileChanged() }
        requestFit()
        scheduleSave()
    }

    /** Opens [doc] in the reader so its pages can be chosen for the board. */
    fun choosePages(doc: ViewerDoc) {
        openDoc(doc)
        each { it.onChoosePages(doc) }
    }

    /** Lays every image out in tidy rows. */
    fun autoArrange() {
        if (items.isEmpty()) return
        val gap = 40f
        var area = 0.0
        var widest = 0f
        for (it in items) {
            area += (it.effectiveWidth * it.effectiveHeight).toDouble()
            widest = max(widest, it.effectiveWidth)
        }
        val rowLimit = max(widest, rowWidthFor(area))
        var x = 0f
        var y = 0f
        var rowHeight = 0f
        for (it in items) {
            val w = it.effectiveWidth
            if (x > 0f && x + w > rowLimit) {
                x = 0f
                y += rowHeight + gap
                rowHeight = 0f
            }
            it.moveBoundsTo(x, y)
            x += w + gap
            rowHeight = max(rowHeight, it.effectiveHeight)
        }
        boardChanged()
        requestFit()
    }

    fun requestFit() = each { it.onFitRequested() }

    /** Width/height of the board on screen (set by the canvas), so layouts suit portrait phones and landscape tablets. */
    var screenAspect = 1.6f

    /** How wide a row of images may grow so the whole board fills the screen's shape. */
    private fun rowWidthFor(area: Double): Float = (sqrt(area * screenAspect) * 1.15).toFloat()

    // ---------------------------------------------------------------- Practice

    fun currentPose(): Pose? = practice.getOrNull(practiceIndex)

    /** Adds poses to the session. With [jumpToFirst] the first new pose is shown straight away. */
    fun addPoses(poses: List<Pose>, jumpToFirst: Boolean) {
        if (poses.isEmpty()) return
        val firstNew = practice.size
        practice.addAll(poses)
        if (jumpToFirst || firstNew == 0) {
            setIndex(firstNew)
        } else {
            each { it.onPracticeChanged() }
            scheduleSave()
        }
    }

    /** Replaces the practice session with the images that are on the board. */
    fun practiceWithBoardImages(): Boolean {
        val pictures = items.mapNotNull { it.image }
        if (pictures.isEmpty()) return false
        practice.clear()
        pictures.mapTo(practice) { Pose.Image(it) }
        setIndex(0)
        return true
    }

    fun clearPractice() {
        practice.clear()
        practiceIndex = 0
        PracticeTimer.listChanged()
        each { it.onPracticeChanged() }
        scheduleSave()
    }

    /** Memory mode hid or showed the pose. */
    fun poseCoverChanged() = each { it.onPracticeChanged() }

    /** A short message at the bottom of the screen (works from the floating window too). */
    fun toast(text: String) {
        val ctx = appContext ?: return
        android.widget.Toast.makeText(ctx, text, if (text.length > 60) android.widget.Toast.LENGTH_LONG else android.widget.Toast.LENGTH_SHORT).show()
    }

    /** The picture the floating window should zoom to when it opens ("Float this picture"), or 0. */
    var floatFocusId = 0L

    fun nextPose() {
        if (practice.isNotEmpty()) setIndex((practiceIndex + 1) % practice.size)
    }

    fun prevPose() {
        if (practice.isNotEmpty()) setIndex((practiceIndex - 1 + practice.size) % practice.size)
    }

    private fun setIndex(i: Int) {
        practiceIndex = i
        practiceFlipped = false
        each { it.onPracticeChanged() }
        scheduleSave()
    }

    fun togglePracticeFlip() {
        practiceFlipped = !practiceFlipped
        each { it.onPracticeChanged() }
    }

    fun togglePracticeGrayscale() {
        practiceGrayscale = !practiceGrayscale
        each { it.onPracticeChanged() }
    }

    /** Practise with the pages of a viewer PDF, starting at [startPage]. Reuses pages already in the list. */
    fun practiceDoc(doc: ViewerDoc, startPage: Int) {
        val existing = practice.indexOfFirst { it is Pose.PdfPage && it.docId == doc.docId && it.page == startPage }
        if (existing >= 0) {
            setIndex(existing)
        } else {
            val firstNew = practice.size
            practice.addAll((0 until doc.pageCount).map { Pose.PdfPage(doc.docId, it) })
            setIndex(firstNew + startPage.coerceIn(0, doc.pageCount - 1))
        }
        setMode(MODE_PRACTICE)
    }

    // ---------------------------------------------------------------- PDF viewer

    /** Shows [doc] in the viewer. A PDF that is already in the list is reused instead of stored twice. */
    fun openDoc(doc: ViewerDoc) {
        val same = docs.firstOrNull { it.docId == doc.docId || (it.title == doc.title && it.pageCount == doc.pageCount) }
        if (same != null) {
            if (same.docId != doc.docId) Storage.deletePdfLater(doc.docId) // duplicate copy, not needed
            docs.remove(same)
            docs.add(0, same)
        } else {
            docs.add(0, doc)
            while (docs.size > MAX_RECENT_DOCS) docs.removeAt(docs.size - 1)
        }
        each { it.onDocsChanged() }
        setMode(MODE_PDF)
        scheduleSave()
    }

    fun removeDoc(doc: ViewerDoc) {
        if (!docs.remove(doc)) return
        each { it.onDocsChanged() }
        scheduleSave()
    }

    /** The reading position changed; save it a moment later. */
    fun docPositionChanged() = scheduleSave()

    // ---------------------------------------------------------------- Mode & status

    fun setMode(newMode: Int) {
        if (newMode == MODE_PRACTICE && practice.isEmpty()) practiceWithBoardImages()
        if (mode == newMode) return
        mode = newMode
        if (newMode != MODE_PRACTICE) PracticeTimer.pause()
        if (newMode == MODE_BOARD) PdfPages.trim(all = true) // PDF pages are not needed on the board
        each { it.onModeChanged() }
        scheduleSave()
    }

    fun setStatus(text: String?, stop: (() -> Unit)? = null) {
        if (status == text && statusStop === stop) return
        status = text
        statusStop = if (text == null) null else stop
        each { it.onStatusChanged() }
    }

    // ---------------------------------------------------------------- Saving

    private val saveRunnable = Runnable { saveNow() }

    /** Saves a moment later, so a burst of changes is written once. */
    fun scheduleSave() {
        main.removeCallbacks(saveRunnable)
        main.postDelayed(saveRunnable, 800)
    }

    fun saveNow() {
        main.removeCallbacks(saveRunnable)
        if (!restored) return // never overwrite the saved board before it has been read back
        Storage.saveAsync(Storage.encode(items, practice, practiceIndex, docs, mode, boardUri, boardName, boardDirty))
    }
}
