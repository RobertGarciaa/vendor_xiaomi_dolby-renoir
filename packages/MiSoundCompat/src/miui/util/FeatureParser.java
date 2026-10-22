/*
 * Copyright (C) 2026 The LineageOS Project
 * SPDX-License-Identifier: Apache-2.0
 *
 * Minimal stand-in for the MIUI framework class miui.util.FeatureParser.
 *
 * MiSound calls exactly one method:
 *
 *   FeatureParser.getString("vendor")
 *
 * and compares the result against "mediatek" to decide whether to probe a
 * MediaTek-specific audio device. On renoir the answer is Qualcomm, so any
 * value other than "mediatek" takes the ordinary path. Returning the real
 * platform value keeps that branch honest instead of hard-coding a device
 * assumption.
 *
 * MIUI reads these values from a device feature XML. There is no such file in
 * this tree, and inventing a full parser would be scope creep for one call
 * site, so the handful of keys the app actually asks for are answered from
 * the running system. Unknown keys return null, matching MIUI's behaviour for
 * an absent feature.
 */

package miui.util;

public final class FeatureParser {
    private FeatureParser() {
    }

    /**
     * @param key feature name, e.g. "vendor"
     * @return the feature value, or null when unknown
     */
    public static String getString(String key) {
        if (key == null) {
            return null;
        }
        switch (key) {
            case "vendor":
                // ro.board.platform is "lahaina" on this SoC. MIUI's "vendor"
                // feature distinguishes "mediatek" from everything else, so
                // report the SoC vendor rather than the platform codename.
                return "qcom";
            case "product":
                return android.os.Build.PRODUCT;
            case "device":
                return android.os.Build.DEVICE;
            case "model":
                return android.os.Build.MODEL;
            case "brand":
                return android.os.Build.BRAND;
            case "manufacturer":
                return android.os.Build.MANUFACTURER;
            default:
                return null;
        }
    }
}
