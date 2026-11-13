package com.refpad.app

import android.content.Context
import android.content.Intent
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.provider.OpenableColumns
import android.util.Log
import android.widget.Toast
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedOutputStream
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.io.OutputStream
import java.util.zip.Deflater
import java.util.zip.ZipEntry
import java.util.zip.ZipFile
import java.util.zip.ZipOutputStream
import kotlin.math.max

/**
 * Boards as files: keep one board per project (for example one per manga chapter) in a .refpad file
 * and switch between them. The file holds the pictures too, and uses the same format as RefPad for
 * Windows, so a board saved on the PC opens on the tablet and the other way round.
 *
 * The file itself is chosen with Android's own file screen; RefPad keeps permission to it so it can
 * save it again later and list it under "Recent boards".
 */
object BoardFiles {
    private const val TAG = "RefPad"
    const val EXT = ".refpad"
    const val MIME = "application/octet-stream"
    private const val FORMAT = 1
    private const val PREFS = "refpad"
    private const val KEY_RECENT = "recent_boards"
    private const val MAX_RECENT = 10

    private val main = Handler(Looper.getMainLooper())

    /** Runs after an untitled board has been saved with "Save as" (for example: then open the next board). */
    var afterSaveAs: (() -> Unit)? = null

    class Recent(val uri: String, val name: String)

    // ---------------------------------------------------------------- Recent boards

    fun recent(context: Context): List<Recent> {
        val json = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY_RECENT, "[]") ?: "[]"
        val granted = try {
            context.contentResolver.persistedUriPermissions.map { it.uri.toString() }.toSet()
        } catch (e: Exception) {
            emptySet()
        }
        val out = ArrayList<Recent>()
        try {
            val a = JSONArray(json)
            for (i in 0 until a.length()) {
                val o = a.optJSONObject(i) ?: continue
                val uri = o.optString("u")
                if (uri.isNotEmpty() && uri in granted) out.add(Recent(uri, o.optString("n", "Board")))
            }
        } catch (e: Exception) {
            Log.w(TAG, "Recent boards unreadable", e)
        }
        return out
    }

    private fun remember(context: Context, uri: String, name: String) {
        val list = recent(context).filter { it.uri != uri }.toMutableList()
        list.add(0, Recent(uri, name))
        // Let go of files that drop off the list, so Android's limit on kept permissions is never reached.
        for (old in list.drop(MAX_RECENT)) releasePermission(context, old.uri)
        save(context, list.take(MAX_RECENT))
    }

    fun forget(context: Context, uri: String) {
        save(context, recent(context).filter { it.uri != uri })
        releasePermission(context, uri)
    }

    private fun save(context: Context, list: List<Recent>) {
        val a = JSONArray()
        for (r in list) a.put(JSONObject().put("u", r.uri).put("n", r.name))
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putString(KEY_RECENT, a.toString()).apply()
    }

    private fun keepPermission(context: Context, uri: Uri) {
        val rw = Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION
        try {
            context.contentResolver.takePersistableUriPermission(uri, rw)
        } catch (e: Exception) {
            try {
                context.contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
            } catch (e2: Exception) {
                Log.w(TAG, "Could not keep permission for $uri", e2)
            }
        }
    }

    private fun releasePermission(context: Context, uri: String) {
        if (uri == DataManager.boardUri) return
        try {
            context.contentResolver.releasePersistableUriPermission(
                Uri.parse(uri), Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION
            )
        } catch (e: Exception) {
            // already gone
        }
    }

    /** True if RefPad has lasting permission to write to [uri]. */
    private fun canWrite(context: Context, uri: Uri): Boolean = try {
        context.contentResolver.persistedUriPermissions.any { it.uri == uri && it.isWritePermission }
    } catch (e: Exception) {
        false
    }

    fun displayName(context: Context, uri: Uri): String {
        val name = try {
            context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
                if (c.moveToFirst()) c.getString(0) else null
            }
        } catch (e: Exception) {
            null
        }
        val n = (name ?: uri.lastPathSegment ?: "Board").substringAfterLast('/')
        return (if (n.endsWith(EXT, ignoreCase = true)) n.dropLast(EXT.length) else n).trim().ifEmpty { "Board" }
    }

    // ---------------------------------------------------------------- Saving

    /** What is on the board right now, in the shared file format (taken on the main thread). */
    private class Snapshot(val json: String, val files: List<String>, val version: Int)

    private fun snapshot(): Snapshot {
        val items = JSONArray()
        val files = LinkedHashSet<String>()
        for (it in DataManager.items) {
            val q = (it.rotation / 90) % 4
            // Android flips the picture first and then turns it; the file (and RefPad for Windows) turns
            // first and then flips on screen. Flipped pictures therefore turn the other way round.
            val rot = if (it.flipped) (4 - q) % 4 else q
            val img = it.image
            val j = JSONObject()
            if (img != null) {
                j.put("img", "images/${img.fileName}").put("w", img.width).put("h", img.height)
                files.add(img.fileName)
            } else {
                j.put("w", Math.round(it.noteW)).put("h", Math.round(it.noteH)).put("note", it.note)
            }
            j.put("cx", it.centerX.toDouble())
                .put("cy", it.centerY.toDouble())
                .put("s", it.scale.toDouble())
                .put("rot", rot)
                .put("flip", it.flipped)
                .put("gray", it.grayscale)
            // The crop is [x, y, width, height] in picture pixels, as RefPad for Windows writes it.
            it.crop?.let { c ->
                j.put("crop", JSONArray().put(r1(c.left)).put(r1(c.top)).put(r1(c.width())).put(r1(c.height())))
            }
            if (it.opacity < 1f) j.put("opacity", Math.round(it.opacity * 100) / 100.0)
            if (it.locked) j.put("locked", true)
            if (it.grid > 0) j.put("grid", it.grid)
            if (it.values > 0) j.put("values", it.values)
            if (it.blur) j.put("blur", true)
            items.put(j)
        }
        val json = JSONObject().put("app", "RefPad").put("format", FORMAT).put("view", JSONObject.NULL).put("items", items)
        return Snapshot(json.toString(1), files.toList(), DataManager.boardVersion)
    }

    private fun r1(v: Float) = Math.round(v * 10) / 10.0

    /** Saves the board to its own file (in the background). [done] gets an error message, or null. */
    fun saveCurrent(context: Context, quiet: Boolean = false, done: ((String?) -> Unit)? = null) {
        val uri = DataManager.boardUri
        if (uri == null) {
            done?.invoke("This board has no file yet")
            return
        }
        write(context.applicationContext, Uri.parse(uri), quiet, adopt = false, done = done)
    }

    /** After "Save as": keep access to the new file, write the board into it, and remember it. */
    fun created(context: Context, uri: Uri) {
        val app = context.applicationContext
        keepPermission(app, uri)
        val then = afterSaveAs
        afterSaveAs = null
        write(app, uri, quiet = false, adopt = true) { error -> if (error == null) then?.invoke() }
    }

    /** Saves a board that has a file when you leave the app (nothing happens if it is already saved). */
    fun saveIfNeeded(context: Context) {
        if (DataManager.boardUri != null && DataManager.boardDirty && DataManager.items.isNotEmpty()) {
            saveCurrent(context, quiet = true)
        }
    }

    private fun write(app: Context, uri: Uri, quiet: Boolean, adopt: Boolean, done: ((String?) -> Unit)?) {
        val snap = snapshot()
        if (!quiet) DataManager.setStatus("Saving board…")
        Storage.io.execute {
            val error = try {
                openForWriting(app, uri).use { out -> writeZip(out, snap) }
                null
            } catch (e: Exception) {
                Log.w(TAG, "Saving board failed", e)
                "Couldn't save the board. Is the file still there?"
            }
            val name = displayName(app, uri)
            main.post {
                if (!quiet) DataManager.setStatus(null)
                if (error == null) {
                    DataManager.boardSaved(uri.toString(), name, snap.version, adopt)
                    remember(app, uri.toString(), name)
                    if (!quiet) toast(app, "Saved “$name”")
                } else if (!quiet) {
                    toast(app, error)
                }
                done?.invoke(error)
            }
        }
    }

    private fun openForWriting(context: Context, uri: Uri): OutputStream {
        for (mode in arrayOf("wt", "rwt", "w")) {
            try {
                context.contentResolver.openOutputStream(uri, mode)?.let { return it }
            } catch (e: Exception) {
                // try the next mode; some providers only support some of them
            }
        }
        throw IOException("Can't write to $uri")
    }

    private fun writeZip(out: OutputStream, snap: Snapshot) {
        ZipOutputStream(BufferedOutputStream(out, 256 * 1024)).use { z ->
            z.setLevel(Deflater.DEFAULT_COMPRESSION)
            z.putNextEntry(ZipEntry("board.json"))
            z.write(snap.json.toByteArray(Charsets.UTF_8))
            z.closeEntry()
            z.setLevel(Deflater.NO_COMPRESSION) // pictures are already compressed
            for (name in snap.files) {
                val f = File(Storage.imgDir, name)
                if (!f.exists()) continue
                z.putNextEntry(ZipEntry("images/$name"))
                f.inputStream().use { it.copyTo(z, 256 * 1024) }
                z.closeEntry()
            }
        }
    }

    // ---------------------------------------------------------------- Opening

    class Loaded(val items: List<RefBoardItem>, val missing: Int)

    /**
     * Opens a board file (in the background) and shows it in place of the current board.
     * A file from another app that RefPad may not write to opens as a copy (Save as keeps it).
     */
    fun load(context: Context, uri: Uri, fromOtherApp: Boolean = false) {
        val app = context.applicationContext
        keepPermission(app, uri)
        val linked = !fromOtherApp || canWrite(app, uri)
        // Pictures already in memory (for example when reopening the same board) are shared, not loaded twice.
        val inMemory = HashMap<String, RefImage>()
        for (it in DataManager.items) it.image?.let { img -> inMemory[img.fileName] = img }
        val name = displayName(app, uri)
        DataManager.setStatus("Opening “$name”…")
        Storage.io.execute {
            val result = try {
                read(app, uri, inMemory)
            } catch (e: BoardError) {
                e
            } catch (e: Exception) {
                Log.w(TAG, "Opening board failed", e)
                BoardError("Couldn't open this board. The file may be damaged or no longer there.")
            }
            main.post {
                DataManager.setStatus(null)
                if (result is Loaded) {
                    val n = result.items.size
                    var msg = "Opened “$name” · $n item${if (n == 1) "" else "s"}"
                    if (result.missing > 0) msg += " · ${result.missing} couldn't be read"
                    if (linked) {
                        DataManager.replaceBoard(result.items, uri.toString(), name)
                        remember(app, uri.toString(), name)
                    } else {
                        // RefPad can't save into this file: keep the name, and Save asks where to save a copy.
                        DataManager.replaceBoard(result.items, null, name, dirty = true)
                        msg += " · use Save to keep a copy"
                    }
                    DataManager.setMode(DataManager.MODE_BOARD)
                    toast(app, msg)
                } else {
                    val error = result as BoardError
                    if (error.fileGone) forget(app, uri.toString())
                    toast(app, error.message ?: "Couldn't open this board")
                }
            }
        }
    }

    class BoardError(message: String, val fileGone: Boolean = false) : Exception(message)

    private fun read(context: Context, uri: Uri, inMemory: Map<String, RefImage>): Loaded {
        // A zip needs to be read in any order, so first copy it to a private file.
        val tmp = Storage.tempFile()
        try {
            val input = try {
                context.contentResolver.openInputStream(uri)
            } catch (e: Exception) {
                null
            } ?: throw BoardError("That board file can't be found. It may have been moved or deleted.", fileGone = true)
            input.use { inp -> FileOutputStream(tmp).use { inp.copyTo(it, 256 * 1024) } }
            val zip = try {
                ZipFile(tmp)
            } catch (e: Exception) {
                throw BoardError("This file isn't a RefPad board.")
            }
            zip.use { z ->
                val boardEntry = z.getEntry("board.json") ?: throw BoardError("This file isn't a RefPad board.")
                val board = JSONObject(z.getInputStream(boardEntry).bufferedReader().readText())
                if (board.optString("app") != "RefPad") throw BoardError("This file isn't a RefPad board.")
                if (board.optInt("format", 1) > FORMAT) throw BoardError("This board was saved by a newer RefPad. Please update RefPad.")
                val itemsJson = board.optJSONArray("items") ?: JSONArray()
                val images = HashMap<String, RefImage?>()
                val items = ArrayList<RefBoardItem>()
                var missing = 0
                for (i in 0 until itemsJson.length()) {
                    val j = itemsJson.optJSONObject(i) ?: continue
                    val arc = j.optString("img")
                    if (arc.isEmpty() && j.has("note")) {
                        items.add(noteItem(j))
                        continue
                    }
                    val img = images.getOrPut(arc) { extract(z, arc, inMemory) }
                    if (img == null) {
                        missing++
                        continue
                    }
                    items.add(item(j, img))
                }
                return Loaded(items, missing)
            }
        } finally {
            tmp.delete()
        }
    }

    /** One picture from the board file, as a picture RefPad can draw (shrunk to 1600 px if bigger). */
    private fun extract(z: ZipFile, arc: String, inMemory: Map<String, RefImage>): RefImage? {
        val entry = z.getEntry(arc) ?: return null
        val base = arc.substringAfterLast('/')
        val ext = base.substringAfterLast('.', "").lowercase()
        if (ext !in setOf("jpg", "jpeg", "png", "webp")) return null
        // Same picture as one already on screen (reopening the same board): share it.
        inMemory[base]?.let { img ->
            if (File(Storage.imgDir, base).length() == entry.size) return img
        }
        var name = base
        var file = File(Storage.imgDir, name)
        if (file.exists() && file.length() != entry.size) {
            name = "${Storage.newId()}.$ext"
            file = File(Storage.imgDir, name)
        }
        if (!file.exists()) {
            Storage.imgDir.mkdirs()
            z.getInputStream(entry).use { inp -> FileOutputStream(file).use { inp.copyTo(it, 256 * 1024) } }
        }
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(file.path, bounds)
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) {
            file.delete()
            return null
        }
        if (max(bounds.outWidth, bounds.outHeight) > ImageLoader.MAX_IMAGE_SIDE) {
            // A big picture (for example from RefPad for Windows): keep a 1600 px copy instead.
            val bmp = ImageLoader.decodeFile(file) ?: return null
            file.delete()
            return ImageLoader.store(bmp)
        }
        val bmp = ImageLoader.loadSaved(file) ?: return null
        return RefImage(name, ImageLoader.toDisplay(bmp), ImageLoader.loadSavedPreview(file)?.let { ImageLoader.toDisplay(it) })
    }

    private fun item(j: JSONObject, img: RefImage): RefBoardItem {
        // The file stores the picture's size at save time; the copy here may be smaller, so keep the same size on the board.
        val wFile = j.optDouble("w", img.width.toDouble()).toFloat().coerceAtLeast(1f)
        val scale = (j.optDouble("s", 1.0).toFloat() * wFile / img.width.coerceAtLeast(1))
            .coerceIn(RefBoardItem.MIN_SCALE, RefBoardItem.MAX_SCALE)
        val flip = j.optBoolean("flip", false)
        val q = ((j.optInt("rot", 0) % 4) + 4) % 4
        val rotation = (if (flip) (4 - q) % 4 else q) * 90
        val cx = j.optDouble("cx", 0.0).toFloat()
        val cy = j.optDouble("cy", 0.0).toFloat()
        // The crop is in the file's picture pixels; this copy may be smaller.
        val k = img.width / wFile
        val crop = j.optJSONArray("crop")?.takeIf { it.length() == 4 }?.let { a ->
            val x0 = a.optDouble(0).toFloat() * k
            val y0 = a.optDouble(1).toFloat() * k
            android.graphics.RectF(x0, y0, x0 + a.optDouble(2).toFloat() * k, y0 + a.optDouble(3).toFloat() * k).apply {
                intersect(0f, 0f, img.width.toFloat(), img.height.toFloat())
            }.takeIf { it.width() >= 1f && it.height() >= 1f }
        }
        val item = RefBoardItem(
            image = img,
            scale = scale,
            rotation = rotation,
            flipped = flip,
            grayscale = j.optBoolean("gray", false),
            crop = crop
        )
        looks(item, j)
        item.x = cx - item.width / 2f
        item.y = cy - item.height / 2f
        return item
    }

    /** A text note from the file. Its height is fitted again to the text as Android shows it. */
    private fun noteItem(j: JSONObject): RefBoardItem {
        val item = RefBoardItem(
            image = null,
            scale = j.optDouble("s", 1.0).toFloat().coerceIn(RefBoardItem.MIN_SCALE, RefBoardItem.MAX_SCALE),
            note = j.optString("note"),
            noteW = j.optDouble("w", RefBoardItem.NOTE_WIDTH.toDouble()).toFloat().coerceAtLeast(40f),
            noteH = j.optDouble("h", 100.0).toFloat().coerceAtLeast(20f)
        )
        looks(item, j)
        item.sizeNote()
        item.x = j.optDouble("cx", 0.0).toFloat() - item.width / 2f
        item.y = j.optDouble("cy", 0.0).toFloat() - item.height / 2f
        return item
    }

    private fun looks(item: RefBoardItem, j: JSONObject) {
        item.opacity = j.optDouble("opacity", 1.0).toFloat().coerceIn(0.1f, 1f)
        item.locked = j.optBoolean("locked", false)
        item.grid = j.optInt("grid", 0).coerceIn(0, 12)
        item.values = j.optInt("values", 0).takeIf { it in 2..5 } ?: 0
        item.blur = j.optBoolean("blur", false)
    }

    private fun toast(context: Context, text: String) =
        Toast.makeText(context, text, if (text.length > 60) Toast.LENGTH_LONG else Toast.LENGTH_SHORT).show()
}
