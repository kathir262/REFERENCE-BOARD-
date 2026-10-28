package com.refpad.app

import android.graphics.Bitmap

object DataManager {
    val referenceImages = mutableListOf<Bitmap>()
    val practiceImages = mutableListOf<Bitmap>()

    var copiedBitmap: Bitmap? = null

    var onNewReferenceAdded: ((Bitmap) -> Unit)? = null
    var onPracticeImagesUpdated: (() -> Unit)? = null

    fun addReference(bitmap: Bitmap) {
        referenceImages.add(bitmap)
        onNewReferenceAdded?.invoke(bitmap)
    }

    fun addPracticeImages(bitmaps: List<Bitmap>) {
        practiceImages.addAll(bitmaps)
        onPracticeImagesUpdated?.invoke()
    }

    fun clearPractice() {
        practiceImages.clear()
        onPracticeImagesUpdated?.invoke()
    }
}
