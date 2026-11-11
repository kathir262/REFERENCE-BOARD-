package com.refpad.app

import android.app.Activity
import android.os.Build
import android.os.Bundle
import android.text.Html
import android.widget.TextView

/** Shows the privacy policy (the same text as the public web page used for Google Play). */
class PrivacyActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_privacy)
        findViewById<android.view.View>(R.id.btn_back).setOnClickListener { finish() }

        val html = resources.openRawResource(R.raw.privacy_policy).bufferedReader().use { it.readText() }
        findViewById<TextView>(R.id.tv_policy).text =
            if (Build.VERSION.SDK_INT >= 24) Html.fromHtml(html, Html.FROM_HTML_MODE_COMPACT)
            else @Suppress("DEPRECATION") Html.fromHtml(html)

        val version = try {
            @Suppress("DEPRECATION")
            packageManager.getPackageInfo(packageName, 0).versionName
        } catch (e: Exception) {
            null
        }
        findViewById<TextView>(R.id.tv_version).text = "RefPad ${version ?: ""} · free, no ads, no tracking"
    }
}
