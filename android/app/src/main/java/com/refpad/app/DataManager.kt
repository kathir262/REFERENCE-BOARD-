package com.refpad.app

import android.graphics.Bitmap

object DataManager {
    val referenceImages = mutableListOf<Bitmap>()
    val practiceImages = mutableListOf<Bitmap>()

    var copiedBitmap: Bitmap? = null

    private val referenceListeners = mutableListOf<(Bitmap) -> Unit>()
    private val practiceListeners = mutableListOf<() -> Unit>()

    @Synchronized
    fun addReferenceListener(listener: (Bitmap) -> Unit) {
        if (!referenceListeners.contains(listener)) {
            referenceListeners.add(listener)
        }
    }

    @Synchronized
    fun removeReferenceListener(listener: (Bitmap) -> Unit) {
        referenceListeners.remove(listener)
    }

    @Synchronized
    fun addPracticeListener(listener: () -> Unit) {
        if (!practiceListeners.contains(listener)) {
            practiceListeners.add(listener)
        }
    }

    @Synchronized
    fun removePracticeListener(listener: () -> Unit) {
        practiceListeners.remove(listener)
    }

    @Synchronized
    fun addReference(bitmap: Bitmap) {
        referenceImages.add(bitmap)
        for (l in referenceListeners.toList()) {
            try {
                l.invoke(bitmap)
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }
    }

    @Synchronized
    fun addPracticeImages(bitmaps: List<Bitmap>) {
        practiceImages.addAll(bitmaps)
        for (l in practiceListeners.toList()) {
            try {
                l.invoke()
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }
    }

    @Synchronized
    fun clearPractice() {
        practiceImages.clear()
        for (l in practiceListeners.toList()) {
            try {
                l.invoke()
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }
    }
}
