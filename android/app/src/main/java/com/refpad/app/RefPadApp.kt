package com.refpad.app

import android.app.Application
import android.content.ComponentCallbacks2

class RefPadApp : Application() {
    override fun onCreate() {
        super.onCreate()
        // Start reading the saved board straight away, before any screen asks for it.
        DataManager.init(this)
    }

    @Suppress("DEPRECATION")
    override fun onTrimMemory(level: Int) {
        super.onTrimMemory(level)
        when {
            level >= ComponentCallbacks2.TRIM_MEMORY_BACKGROUND -> PdfPages.trim(all = true)
            level >= ComponentCallbacks2.TRIM_MEMORY_RUNNING_LOW && level != ComponentCallbacks2.TRIM_MEMORY_UI_HIDDEN ->
                PdfPages.trim(all = false)
        }
    }
}
