package com.refpad.app

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.os.Process
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.UUID
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

/**
 * Saves the board to the app's private storage and restores it on the next launch.
 *
 * Layout inside filesDir/board:
 *   state.json   positions, sizes and practice list
 *   img/         one compact copy of each imported image (max 1600 px)
 *   pdf/         PDFs used in practice mode (pages are rendered on demand)
 */
object Storage {
    private const val TAG = "RefPad"

    class State(
        val items: List<RefBoardItem>,
        val practice: List<Pose>,
        val practiceIndex: Int,
        val docs: List<ViewerDoc>,
        val mode: Int,
        val boardUri: String?,
        val boardName: String,
        val boardDirty: Boolean
    )

    private val main = Handler(Looper.getMainLooper())

    /**
     * One low-priority worker thread for all disk and decode work.
     * Imports run one at a time so they never fight the UI or each other for the CPU.
     */
    val io: ExecutorService = Executors.newSingleThreadExecutor { r ->
        Thread({
            Process.setThreadPriority(Process.THREAD_PRIORITY_BACKGROUND)
            r.run()
        }, "refpad-io")
    }

    private lateinit var root: File
    private lateinit var tmpDir: File
    lateinit var imgDir: File
        private set
    lateinit var pdfDir: File
        private set
    private lateinit var stateFile: File

    fun init(context: Context) {
        root = File(context.filesDir, "board")
        imgDir = File(root, "img").apply { mkdirs() }
        pdfDir = File(root, "pdf").apply { mkdirs() }
        tmpDir = File(context.cacheDir, "import")
        stateFile = File(root, "state.json")
    }

    fun newId(): String = UUID.randomUUID().toString().replace("-", "").substring(0, 20)

    fun pdfFile(docId: String) = File(pdfDir, "$docId.pdf")

    fun tempFile(): File {
        tmpDir.mkdirs()
        return File(tmpDir, newId())
    }

    // ---------------------------------------------------------------- Save

    /** Deletes a stored PDF that is no longer needed (only ever called for a copy nothing points at). */
    fun deletePdfLater(docId: String) {
        io.execute { pdfFile(docId).delete() }
    }

    fun encode(
        items: List<RefBoardItem>, practice: List<Pose>, practiceIndex: Int, docs: List<ViewerDoc>, mode: Int,
        boardUri: String?, boardName: String, boardDirty: Boolean
    ): String {
        val itemsJson = JSONArray()
        for (it in items) {
            val j = JSONObject()
                .put("x", it.x.toDouble())
                .put("y", it.y.toDouble())
                .put("s", it.scale.toDouble())
                .put("r", it.rotation)
                .put("fl", it.flipped)
                .put("g", it.grayscale)
            val img = it.image
            if (img != null) j.put("f", img.fileName)
            else j.put("n", it.note).put("nw", it.noteW.toDouble()).put("nh", it.noteH.toDouble())
            it.crop?.let { c -> j.put("c", JSONArray().put(c.left.toDouble()).put(c.top.toDouble()).put(c.right.toDouble()).put(c.bottom.toDouble())) }
            if (it.opacity < 1f) j.put("o", it.opacity.toDouble())
            if (it.locked) j.put("lk", true)
            if (it.grid > 0) j.put("gd", it.grid)
            if (it.values > 0) j.put("vs", it.values)
            if (it.blur) j.put("bl", true)
            itemsJson.put(j)
        }
        val practiceJson = JSONArray()
        for (p in practice) {
            when (p) {
                is Pose.Image -> practiceJson.put(JSONObject().put("t", "i").put("f", p.image.fileName))
                is Pose.PdfPage -> practiceJson.put(JSONObject().put("t", "p").put("d", p.docId).put("p", p.page))
            }
        }
        val docsJson = JSONArray()
        for (d in docs) {
            val aspects = JSONArray()
            for (a in d.aspectList()) aspects.put((a * 10000).toInt() / 10000.0)
            val j = JSONObject()
                .put("d", d.docId)
                .put("t", d.title)
                .put("a", aspects)
                .put("p", d.position.toDouble())
            if (d.spread) j.put("sp", true)
            if (d.bookmarks.isNotEmpty()) j.put("bm", JSONArray().apply { for (b in d.bookmarks) put(b) })
            docsJson.put(j)
        }
        return JSONObject()
            .put("v", 2)
            .put("items", itemsJson)
            .put("practice", practiceJson)
            .put("pi", practiceIndex)
            .put("docs", docsJson)
            .put("m", mode)
            .put("bu", boardUri ?: "")
            .put("bn", boardName)
            .put("bd", boardDirty)
            .toString()
    }

    fun saveAsync(json: String) {
        io.execute {
            try {
                root.mkdirs()
                val tmp = File(root, "state.json.tmp")
                tmp.writeText(json)
                if (!tmp.renameTo(stateFile)) {
                    stateFile.delete()
                    tmp.renameTo(stateFile)
                }
            } catch (e: Exception) {
                Log.w(TAG, "Saving board failed", e)
            }
        }
    }

    // ---------------------------------------------------------------- Load

    fun loadAsync(done: (State?) -> Unit) {
        main.post { DataManager.setStatus("Restoring your board…") }
        io.execute {
            val state = try {
                load()
            } catch (t: Throwable) {
                Log.w(TAG, "Restoring board failed", t)
                null
            }
            main.post {
                DataManager.setStatus(null)
                done(state)
            }
        }
    }

    private fun load(): State? {
        tmpDir.deleteRecursively()
        if (!stateFile.exists()) {
            deleteUnused(emptySet(), emptySet())
            return null
        }
        val json = JSONObject(stateFile.readText())
        val images = HashMap<String, RefImage?>()
        fun image(name: String): RefImage? {
            if (images.containsKey(name)) return images[name]
            val file = File(imgDir, name)
            val bmp = ImageLoader.loadSaved(file)
            val img = bmp?.let { RefImage(name, it, ImageLoader.loadSavedPreview(file)) }
            images[name] = img
            return img
        }

        val items = ArrayList<RefBoardItem>()
        val itemsJson = json.optJSONArray("items") ?: JSONArray()
        for (i in 0 until itemsJson.length()) {
            val j = itemsJson.optJSONObject(i) ?: continue
            val isNote = !j.has("f") && j.has("n")
            val img = if (isNote) null else image(j.optString("f")) ?: continue
            val item = RefBoardItem(
                image = img,
                x = j.optDouble("x", 0.0).toFloat(),
                y = j.optDouble("y", 0.0).toFloat(),
                scale = j.optDouble("s", img?.let { RefBoardItem.defaultScaleFor(it).toDouble() } ?: 1.0).toFloat()
                    .coerceIn(RefBoardItem.MIN_SCALE, RefBoardItem.MAX_SCALE),
                rotation = if (isNote) 0 else ((j.optInt("r", 0) % 360 + 360) % 360 / 90) * 90,
                flipped = !isNote && j.optBoolean("fl", false),
                grayscale = j.optBoolean("g", false),
                crop = if (img == null) null else readCrop(j.optJSONArray("c"), img),
                opacity = j.optDouble("o", 1.0).toFloat().coerceIn(0.1f, 1f),
                locked = j.optBoolean("lk", false),
                grid = j.optInt("gd", 0).coerceIn(0, 12),
                values = j.optInt("vs", 0).takeIf { it in 2..5 } ?: 0,
                blur = j.optBoolean("bl", false),
                note = if (isNote) j.optString("n") else "",
                noteW = j.optDouble("nw", RefBoardItem.NOTE_WIDTH.toDouble()).toFloat().coerceAtLeast(40f),
                noteH = j.optDouble("nh", 100.0).toFloat().coerceAtLeast(20f)
            )
            items.add(item)
        }

        val poses = ArrayList<Pose>()
        val pdfExists = HashMap<String, Boolean>()
        val practiceJson = json.optJSONArray("practice") ?: JSONArray()
        for (i in 0 until practiceJson.length()) {
            val j = practiceJson.optJSONObject(i) ?: continue
            when (j.optString("t")) {
                "i" -> image(j.optString("f"))?.let { poses.add(Pose.Image(it)) }
                "p" -> {
                    val doc = j.optString("d")
                    if (pdfExists.getOrPut(doc) { pdfFile(doc).exists() }) poses.add(Pose.PdfPage(doc, j.optInt("p")))
                }
            }
        }

        val docs = ArrayList<ViewerDoc>()
        val docsJson = json.optJSONArray("docs") ?: JSONArray()
        for (i in 0 until docsJson.length()) {
            val j = docsJson.optJSONObject(i) ?: continue
            val id = j.optString("d")
            if (!pdfExists.getOrPut(id) { pdfFile(id).exists() }) continue
            val a = j.optJSONArray("a") ?: continue
            val aspects = FloatArray(a.length()) { a.optDouble(it, 1.414).toFloat() }
            if (aspects.isEmpty()) continue
            val marks = java.util.TreeSet<Int>()
            j.optJSONArray("bm")?.let { b -> for (k in 0 until b.length()) b.optInt(k, -1).takeIf { it in aspects.indices }?.let { marks.add(it) } }
            docs.add(ViewerDoc(id, j.optString("t", "PDF"), aspects, j.optDouble("p", 0.0).toFloat(), j.optBoolean("sp", false), marks))
        }

        deleteUnused(images.keys, pdfExists.filterValues { it }.keys)
        return State(
            items, poses, json.optInt("pi", 0), docs, json.optInt("m", DataManager.MODE_BOARD),
            json.optString("bu").ifEmpty { null }, json.optString("bn", ""), json.optBoolean("bd", false)
        )
    }

    /** A saved crop [left, top, right, bottom] in picture pixels, or null if missing or not usable. */
    private fun readCrop(a: JSONArray?, img: RefImage): android.graphics.RectF? {
        if (a == null || a.length() != 4) return null
        val r = android.graphics.RectF(
            a.optDouble(0).toFloat(), a.optDouble(1).toFloat(), a.optDouble(2).toFloat(), a.optDouble(3).toFloat()
        )
        r.intersect(0f, 0f, img.width.toFloat(), img.height.toFloat())
        return r.takeIf { it.width() >= 1f && it.height() >= 1f }
    }

    /** Removes saved files the board no longer uses (only done at startup, before any new import). */
    private fun deleteUnused(keepImages: Set<String>, keepPdfs: Set<String>) {
        imgDir.listFiles()?.forEach { if (it.name !in keepImages) it.delete() }
        pdfDir.listFiles()?.forEach { if (it.name.removeSuffix(".pdf") !in keepPdfs) it.delete() }
    }
}
