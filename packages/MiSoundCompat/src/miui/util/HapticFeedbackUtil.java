/*
 * Copyright (C) 2026 The LineageOS Project
 * SPDX-License-Identifier: Apache-2.0
 *
 * Minimal stand-in for the MIUI framework class miui.util.HapticFeedbackUtil.
 *
 * MiSound's haptic helper (d4/b) probes this class reflectively and only calls
 * the members it finds. The members it looks for are:
 *
 *   static boolean isSupportLinearMotorVibrate()
 *   HapticFeedbackUtil(Context, boolean)
 *   boolean performExtHapticFeedback(int)
 *   boolean isSupportExtHapticFeedback(int)         (reflective, optional)
 *   boolean performHapticFeedback(int, double, String)
 *   void    stop()
 *   ... plus the VibrationAttributes overloads, all looked up in try/catch
 *
 * None of this is needed for Dolby audio. If the class is absent MiSound logs
 * "MIUI Haptic Implementation is not available" and falls back, but the
 * reflective lookups are wrapped in try/catch and the constructor call is not
 * (d4/b.b() would throw NoClassDefFoundError). Providing a plain AOSP-backed
 * implementation keeps the app from crashing on a non-MIUI ROM while doing
 * something honest: vibrate through the public Android API, or report that
 * nothing happened.
 *
 * The VibrationAttributes overloads are deliberately omitted. MIUI probes for
 * them with Class.getMethod in a try/catch, so their absence simply disables
 * those code paths instead of breaking the app.
 */

package miui.util;

import android.content.Context;
import android.os.Build;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.os.VibratorManager;

public class HapticFeedbackUtil {
    private final Context mContext;
    private final boolean mIsHapticEnabled;

    public HapticFeedbackUtil(Context context, boolean isHapticEnabled) {
        mContext = context == null ? null : context.getApplicationContext();
        mIsHapticEnabled = isHapticEnabled;
    }

    /**
     * renoir has a linear (x-axis) motor, but this shim does not claim MIUI's
     * extended haptic waveform support, because it cannot reproduce those
     * waveforms. Reporting false keeps MiSound on its standard path.
     */
    public static boolean isSupportLinearMotorVibrate() {
        return false;
    }

    /** No MIUI extended waveforms are available here. */
    public boolean isSupportExtHapticFeedback(int feedbackConstant) {
        return false;
    }

    /**
     * MIUI effect ids have no AOSP equivalent, so an "extended" request is
     * reported as not performed rather than silently mapped onto an unrelated
     * waveform.
     */
    public boolean performExtHapticFeedback(int feedbackConstant) {
        return false;
    }

    public boolean performHapticFeedback(int feedbackConstant) {
        return performHapticFeedback(feedbackConstant, 1.0);
    }

    public boolean performHapticFeedback(int feedbackConstant, double scale) {
        Vibrator vibrator = getVibrator();
        if (vibrator == null || !vibrator.hasVibrator() || !mIsHapticEnabled) {
            return false;
        }
        // MIUI ids do not map onto AOSP constants. A short, low-amplitude tick
        // is the closest honest equivalent for a UI acknowledgement.
        vibrator.vibrate(VibrationEffect.createOneShot(10,
                VibrationEffect.DEFAULT_AMPLITUDE));
        return true;
    }

    public boolean performHapticFeedback(int feedbackConstant, double scale,
            String reason) {
        return performHapticFeedback(feedbackConstant, scale);
    }

    public void stop() {
        Vibrator vibrator = getVibrator();
        if (vibrator != null) {
            vibrator.cancel();
        }
    }

    private Vibrator getVibrator() {
        if (mContext == null) {
            return null;
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            VibratorManager manager =
                    mContext.getSystemService(VibratorManager.class);
            return manager == null ? null : manager.getDefaultVibrator();
        }
        return mContext.getSystemService(Vibrator.class);
    }
}
