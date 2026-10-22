/*
 * Copyright (C) 2026 The LineageOS Project
 * SPDX-License-Identifier: Apache-2.0
 *
 * Settings entry for Dolby.
 *
 * This is deliberately thin. The actual Dolby UI, profiles and equalizer are
 * Redwood MiSound's, which is patched to talk to the software DAP. Re-
 * implementing that UI here would fork the feature and drift from the app; the
 * job of this activity is to be the entry point Settings can link to, to start
 * the effect owner, and to forward the user into MiSound.
 *
 * It never reports a Dolby state of its own: the summary comes from the
 * controller, which reads the engine.
 */

package org.lineageos.dolby;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ComponentName;
import android.content.Intent;
import android.os.Bundle;
import android.widget.Toast;

public final class DolbySettingsActivity extends Activity {
    /**
     * MiSound's audio settings screen. This is the public entry MiSound itself
     * declares (miui.intent.action.HEADSET_SETTINGS) and it contains the Dolby
     * switch, profile selector, graphic equalizer entry and the spatial audio
     * options.
     */
    private static final String MISOUND_PACKAGE = "com.miui.misound";
    private static final String MISOUND_ACTION = "miui.intent.action.HEADSET_SETTINGS";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        DolbyEffectService.start(this);
        // finish() is called from openMiSound() in both paths: after the
        // MiSound activity is launched, or after the error toast. Calling it
        // here as well would finish this activity before MiSound is started.
        openMiSound();
    }

    private void openMiSound() {
        Intent intent = new Intent(MISOUND_ACTION);
        intent.setComponent(new ComponentName(MISOUND_PACKAGE,
                "com.miui.misound.HeadsetSettingsActivity"));
        try {
            startActivity(intent);
        } catch (ActivityNotFoundException | SecurityException e) {
            Toast.makeText(this, R.string.misound_missing, Toast.LENGTH_LONG).show();
        }
        finish();
    }
}
