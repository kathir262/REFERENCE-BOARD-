package com.refpad.app

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.widget.Button
import android.widget.Toast

class MainActivity : Activity() {

    private val OVERLAY_PERMISSION_REQ_CODE = 1234
    private val FOLDER_PICKER_REQ_CODE = 5678
    private val PDF_PICKER_REQ_CODE = 9012

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        findViewById<Button>(R.id.btn_launch_overlay).setOnClickListener {
            checkOverlayPermissionAndLaunch()
        }

        findViewById<Button>(R.id.btn_pick_folder).setOnClickListener {
            val intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE)
            startActivityForResult(intent, FOLDER_PICKER_REQ_CODE)
        }

        findViewById<Button>(R.id.btn_pick_pdf).setOnClickListener {
            val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                addCategory(Intent.CATEGORY_OPENABLE)
                type = "application/pdf"
            }
            startActivityForResult(intent, PDF_PICKER_REQ_CODE)
        }
    }

    private fun checkOverlayPermissionAndLaunch() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            if (!Settings.canDrawOverlays(this)) {
                val intent = Intent(
                    Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    Uri.parse("package:$packageName")
                )
                startActivityForResult(intent, OVERLAY_PERMISSION_REQ_CODE)
                Toast.makeText(this, "Please grant 'Draw over other apps' to float over your drawing canvas", Toast.LENGTH_LONG).show()
                return
            }
        }
        startFloatingService()
    }

    private fun startFloatingService() {
        val intent = Intent(this, FloatingOverlayService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent)
        } else {
            startService(intent)
        }
        // Move app to background so artist immediately sees their drawing app
        moveTaskToBack(true)
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == OVERLAY_PERMISSION_REQ_CODE) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && Settings.canDrawOverlays(this)) {
                startFloatingService()
            } else {
                Toast.makeText(this, "Overlay permission is required to float over drawing apps", Toast.LENGTH_SHORT).show()
            }
        }
    }
}
