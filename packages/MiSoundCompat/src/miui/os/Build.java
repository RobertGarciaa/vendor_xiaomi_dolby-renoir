/*
 * Copyright (C) 2026 The LineageOS Project
 * SPDX-License-Identifier: Apache-2.0
 *
 * Minimal stand-in for the MIUI framework class miui.os.Build.
 *
 * MiSound reads exactly two fields from it:
 *   Build.DEVICE    - for per-device branches (aries, thyme) that do not
 *                     apply to renoir
 *   Build.IS_TABLET - for layout selection
 *
 * Only those two are provided. Nothing here tries to emulate MIUI as a whole.
 * DEVICE is the real product device, so MiSound's existing "is this a
 * different Xiaomi phone" checks evaluate correctly and the renoir-specific
 * paths are simply not taken.
 */

package miui.os;

public final class Build {
    /** Product device name, e.g. "renoir". */
    public static final String DEVICE = android.os.Build.DEVICE;

    /**
     * Whether the device ships a tablet form factor.
     *
     * android.os.Build.CHARACTERISTICS is a hidden field, so it is not
     * available from a platform app compiled against the public SDK. MiSound's
     * own MIUIX helper reads ro.build.characteristics directly for the same
     * decision, so this does the equivalent using the substring test MIUI
     * applies ("tablet" appearing anywhere in the list).
     */
    public static final boolean IS_TABLET = isTablet();

    private static boolean isTablet() {
        String characteristics = getSystemProperty("ro.build.characteristics");
        return characteristics != null && characteristics.contains("tablet");
    }

    private static String getSystemProperty(String key) {
        try {
            Class<?> sp = Class.forName("android.os.SystemProperties");
            return (String) sp.getMethod("get", String.class).invoke(null, key);
        } catch (ReflectiveOperationException e) {
            return null;
        }
    }

    private Build() {
    }
}
