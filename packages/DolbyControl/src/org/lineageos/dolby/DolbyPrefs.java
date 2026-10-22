/*
 * Copyright (C) 2026 The LineageOS Project
 * SPDX-License-Identifier: Apache-2.0
 *
 * Persisted, read-back-confirmed Dolby state.
 *
 * Values are captured from the live engine and restored for a fresh effect.
 * They never override an already-active MiSound owner during observation.
 *
 * Storage is device-protected so the state survives direct boot and can be
 * restored before the user unlocks.
 */

package org.lineageos.dolby;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.SystemProperties;

import java.util.Locale;

final class DolbyPrefs {
    static final String FILE = "dolby";

    static final String KEY_ENABLED = "enabled";
    static final String KEY_PROFILE = "profile";

    /** Profiles the engine documents and the UI exposes. */
    static final int[] KNOWN_PROFILES = {
            DolbyEffectService.PROFILE_DYNAMIC,
            DolbyEffectService.PROFILE_MOVIE,
            DolbyEffectService.PROFILE_MUSIC,
            DolbyEffectService.PROFILE_VOICE,
    };

    private DolbyPrefs() {
    }

    static SharedPreferences get(Context context) {
        Context storage = context.isDeviceProtectedStorage()
                ? context
                : context.createDeviceProtectedStorageContext();
        return storage.getSharedPreferences(FILE, Context.MODE_PRIVATE);
    }

    /**
     * Whether this product ships the Dolby stack. Set by dolby.mk in the vendor
     * build.prop. This mirrors the check MiSound itself makes, so the UI and
     * the app agree about support.
     */
    static boolean isSupported(Context context) {
        return SystemProperties.getBoolean("ro.vendor.audio.dolby.dax.support", false);
    }

    static boolean isKnownProfile(int profile) {
        for (int known : KNOWN_PROFILES) {
            if (known == profile) {
                return true;
            }
        }
        return false;
    }

    static String profileParameterKey(int profile, int param) {
        return String.format(Locale.US, "p%d_%d", profile, param);
    }

    static String joinInts(int[] values) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < values.length; i++) {
            if (i > 0) {
                sb.append(',');
            }
            sb.append(values[i]);
        }
        return sb.toString();
    }

    /** @return parsed values, or null when absent or malformed */
    static int[] parseInts(String value) {
        if (value == null || value.isEmpty()) {
            return null;
        }
        String[] parts = value.split(",");
        int[] out = new int[parts.length];
        try {
            for (int i = 0; i < parts.length; i++) {
                out[i] = Integer.parseInt(parts[i].trim());
            }
        } catch (NumberFormatException e) {
            return null;
        }
        return out;
    }
}
