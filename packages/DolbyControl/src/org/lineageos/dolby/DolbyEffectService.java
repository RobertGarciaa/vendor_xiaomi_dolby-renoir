/*
 * Copyright (C) 2026 The LineageOS Project
 * SPDX-License-Identifier: Apache-2.0
 *
 * The persistent keeper of the Dolby software DAP effect on renoir.
 *
 * Why this is a separate process
 * ------------------------------
 * MiSound creates the effect itself, but it releases it in onPause()
 * (see y/h.onPause -> c/a.release). In AudioFlinger the effect lives only while
 * at least one handle is attached: when the last handle disconnects,
 * ThreadBase::disconnectEffectHandle removes the effect module entirely. So
 * settings made in MiSound's UI would stop affecting audio as soon as the
 * screen was left.
 *
 * This service therefore holds its own AudioEffect on the global output mix
 * whenever Dolby is enabled, and applies the persisted parameters to it. The
 * MiSound UI keeps working unchanged for the user; it simply stops being the
 * thing that keeps the effect alive.
 *
 * MiSound uses priority 0. The keeper uses -1 so even a late service start
 * cannot take control from an already-open MiSound screen. An explicit QS
 * write can borrow a priority-0 handle and release it immediately afterwards.
 */

package org.lineageos.dolby;

import android.app.Service;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.media.AudioDeviceCallback;
import android.media.AudioDeviceInfo;
import android.media.AudioManager;
import android.media.audiofx.AudioEffect;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.util.Log;

import java.util.UUID;

public final class DolbyEffectService extends Service {
    private static final String TAG = "DolbyEffectService";

    /** Redwood software DAP descriptor (libswdap.so). */
    public static final UUID DAP_IMPL_UUID =
            UUID.fromString("6ab06da4-c516-4611-8166-452799218539");
    /** Redwood DAP descriptor type, shared by the SW and HW engines. */
    public static final UUID DAP_TYPE_UUID =
            UUID.fromString("46d279d9-9be7-453d-9d7c-ef937f675587");

    // Lower priority than MiSound (0): retain the instance, not exclusive control.
    private static final int EFFECT_PRIORITY = -1;
    private static final int WRITE_PRIORITY = 0;

    /** Dolby command ids, as used by MiSound's AudioEffect wrapper. */
    private static final int CMD_CPDP_VALUES = 5;
    private static final int PARAM_ENABLE = 0;
    private static final int PARAM_PROFILE = 0x0A000000;
    private static final int PARAM_SET_PROFILE_PARAMETER = 0x01000000;

    /**
     * Broadcast MiSound listens for to refresh its own Dolby switch and
     * profile list. Its receiver only re-reads the effect and updates the UI;
     * it does not change anything, so this is a one-way "state changed"
     * notification, not a control channel.
     */
    static final String ACTION_DOLBY_STATE_CHANGED =
            "miui.intent.action.ACTION_SYSTEM_UI_DOLBY_EFFECT_SWITCH";
    static final String MISOUND_PACKAGE = "com.miui.misound";

    static final int PROFILE_DYNAMIC = 0;
    static final int PROFILE_MOVIE = 1;
    static final int PROFILE_MUSIC = 2;
    static final int PROFILE_VOICE = 8;

    /** Parameter ids verified to exist in the Redwood DAP descriptor. */
    static final int P_HEADPHONE_VIRTUALIZER = 101;
    static final int P_SPEAKER_VIRTUALIZER = 102;
    static final int P_VOLUME_LEVELER_ENABLE = 103;
    static final int P_IEQ_PRESET = 104;
    static final int P_DIALOGUE_ENHANCER_ENABLE = 105;
    static final int P_DIALOGUE_ENHANCER_AMOUNT = 108;
    static final int P_GEQ_BAND_GAINS = 110;
    static final int P_BASS_ENHANCER_ENABLE = 111;
    static final int P_STEREO_WIDENING_AMOUNT = 113;

    private final Handler mHandler = new Handler(Looper.getMainLooper());
    private final Object mLock = new Object();

    private AudioManager mAudioManager;
    private DolbyAudioEffect mEffect;
    private AudioDeviceCallback mDeviceCallback;
    private BroadcastReceiver mUserReceiver;
    private boolean mAudioServerReady = true;
    private boolean mDestroyed;

    @Override
    public void onCreate() {
        super.onCreate();
        mAudioManager = getSystemService(AudioManager.class);

        if (!DolbyPrefs.isSupported(this)) {
            Log.i(TAG, "Dolby is not marked supported on this device");
        }

        mDeviceCallback = new AudioDeviceCallback() {
            @Override
            public void onAudioDevicesAdded(AudioDeviceInfo[] added) {
                onRouteChanged("devices added");
            }

            @Override
            public void onAudioDevicesRemoved(AudioDeviceInfo[] removed) {
                onRouteChanged("devices removed");
            }
        };
        mAudioManager.registerAudioDeviceCallback(mDeviceCallback, mHandler);

        // AudioEffect handles become invalid when audioserver dies even if
        // this app survives. Recreate only after the server is available.
        mAudioManager.setAudioServerStateCallback(mHandler::post,
                new AudioManager.AudioServerStateCallback() {
                    @Override
                    public void onAudioServerDown() {
                        if (mDestroyed) return;
                        mHandler.removeCallbacks(mCapture);
                        synchronized (mLock) {
                            mAudioServerReady = false;
                            releaseEffectLocked();
                        }
                        DolbyEffectController.get(DolbyEffectService.this)
                                .captureEngineState("audio server down");
                    }

                    @Override
                    public void onAudioServerUp() {
                        if (mDestroyed) return;
                        synchronized (mLock) {
                            mAudioServerReady = true;
                        }
                        DolbyEffectController.get(DolbyEffectService.this)
                                .applyPersistedState("audio server up");
                    }
                });

        // Retire this user's service when another user becomes active.
        mUserReceiver = new BroadcastReceiver() {
            @Override
            public void onReceive(Context context, Intent intent) {
                // SharedPreferences belongs to this service's user; a broadcast
                // does not switch its Context to another user's storage.
                if (intent.getIntExtra(Intent.EXTRA_USER_HANDLE, -1)
                        != android.os.UserHandle.myUserId()) stopSelf();
            }
        };
        IntentFilter filter = new IntentFilter(Intent.ACTION_USER_SWITCHED);
        registerReceiver(mUserReceiver, filter);

        DolbyEffectController.get(this).attachService(this);
        Log.i(TAG, "service created");
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        // Restart if killed: the effect has to come back without user action.
        return START_STICKY;
    }

    /** Starts the effect owner. Safe to call repeatedly. */
    static void start(Context context) {
        // Plain startService, not startForegroundService: this app is a
        // persistent platform component (see AndroidManifest.xml), so its
        // process is kept alive and restarted by the system, and it does not
        // need a foreground notification to survive. A foreground service
        // would require a visible notification for an audio effect, which is
        // the wrong UX.
        context.startService(new Intent(context, DolbyEffectService.class));
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onDestroy() {
        mDestroyed = true;
        if (mAudioManager != null) {
            mAudioManager.clearAudioServerStateCallback();
            if (mDeviceCallback != null) {
                mAudioManager.unregisterAudioDeviceCallback(mDeviceCallback);
            }
        }
        if (mUserReceiver != null) {
            unregisterReceiver(mUserReceiver);
        }
        mHandler.removeCallbacksAndMessages(null);
        DolbyEffectController.get(this).detachService();
        synchronized (mLock) {
            releaseEffectLocked();
        }
        Log.i(TAG, "service destroyed");
        super.onDestroy();
    }

    private void onRouteChanged(String reason) {
        Log.i(TAG, "route changed: " + reason);
        // DMS already knows the new route. Never push stale private prefs over
        // changes made by MiSound; observe the live engine instead.
        DolbyEffectController.get(this).captureEngineState(reason);
    }

    // ---- effect ownership -------------------------------------------------

    void ensureEffectLocked() {
        // A passive handle is still valid. Reads must never steal MiSound's
        // control or destroy the last keeper merely because hasControl=false.
        if (mEffect != null || !mAudioServerReady || mDestroyed) return;
        try {
            mEffect = new DolbyAudioEffect(EFFECT_PRIORITY, 0);
            final DolbyAudioEffect observed = mEffect;
            observed.setControlStatusListener((effect, granted) ->
                    scheduleCapture(observed));
            observed.setEnableStatusListener((effect, enabled) ->
                    scheduleCapture(observed));
            observed.setParameterListener((effect, status, param, value) -> {
                if (status == AudioEffect.SUCCESS) scheduleCapture(observed);
            });
        } catch (RuntimeException e) {
            Log.e(TAG, "could not create the Dolby effect", e);
            mEffect = null;
        }
    }

    private final Runnable mCapture = () ->
            DolbyEffectController.get(this).captureEngineState("effect changed");

    private void scheduleCapture(DolbyAudioEffect observed) {
        mHandler.post(() -> {
            synchronized (mLock) {
                if (mEffect != observed) return;
            }
            // Coalesce parameter bursts (e.g. EQ drag), not periodic polling.
            mHandler.removeCallbacks(mCapture);
            mHandler.postDelayed(mCapture, 100);
        });
    }

    void releaseEffectLocked() {
        if (mEffect != null) {
            // Deliberately does NOT disable the effect. Releasing a handle only
            // gives up control; the effect keeps running as long as another
            // handle is attached, and turning audio processing off here would
            // make a control re-acquire audible. Disabling is an explicit user
            // action, handled in DolbyEffectController.setEnabled.
            try {
                mEffect.release();
            } catch (Exception e) {
                Log.w(TAG, "error while releasing the effect", e);
            }
            mEffect = null;
        }
    }

    /** A short-lived equal-priority handle for an explicit write only. */
    DolbyAudioEffect ensureControlLocked() {
        ensureEffectLocked();
        if (mEffect == null || mEffect.hasControl()) return mEffect;
        DolbyAudioEffect temporary = new DolbyAudioEffect(WRITE_PRIORITY, 0);
        if (!temporary.hasControl()) {
            temporary.release();
            throw new IllegalStateException("Another effect owner has higher priority");
        }
        return temporary;
    }

    void releaseControlLocked(DolbyAudioEffect effect) {
        // Preserve the passive keeper. Releasing the temporary writer returns
        // control to the still-open MiSound handle, without reopening its UI.
        if (effect != null && effect != mEffect) effect.release();
    }

    DolbyAudioEffect getEffectLocked() {
        ensureEffectLocked();
        return mEffect;
    }

    Object lock() {
        return mLock;
    }

    /**
     * Tells MiSound that Dolby state changed underneath it, so an open settings
     * screen refreshes its switch and profile list. MiSound's receiver for this
     * action only re-reads the effect, so no state is changed here.
     */
    void notifyStateChanged() {
        Intent intent = new Intent(ACTION_DOLBY_STATE_CHANGED);
        intent.setPackage(MISOUND_PACKAGE);
        sendBroadcast(intent);
    }

    /** Minimal AudioEffect wrapper speaking the Dolby DAP parameter protocol. */
    static final class DolbyAudioEffect extends AudioEffect {
        DolbyAudioEffect(int priority, int session) {
            super(DAP_TYPE_UUID, DAP_IMPL_UUID, priority, session);
        }

        void setInt(int param, int value) throws IllegalStateException {
            byte[] buf = new byte[12];
            putInt(param, buf, 0);
            putInt(1, buf, 4);
            putInt(value, buf, 8);
            int ret = setParameter(CMD_CPDP_VALUES, buf);
            check(ret, "setInt(" + param + ")");
        }

        int getInt(int param) throws IllegalStateException {
            byte[] buf = new byte[12];
            putInt(param, buf, 0);
            int ret = getParameter(CMD_CPDP_VALUES + param, buf);
            checkRead(ret, 4, buf.length, "getInt(" + param + ")");
            return readInt(buf, 0);
        }

        void setProfileParameter(int profile, int param, int[] values)
                throws IllegalStateException {
            byte[] buf = new byte[(values.length + 4) * 4];
            int off = 0;
            putInt(PARAM_SET_PROFILE_PARAMETER, buf, off);
            off += 4;
            putInt(values.length + 1, buf, off);
            off += 4;
            putInt(profile, buf, off);
            off += 4;
            putInt(param, buf, off);
            off += 4;
            for (int v : values) {
                putInt(v, buf, off);
                off += 4;
            }
            int ret = setParameter(CMD_CPDP_VALUES, buf);
            check(ret, "setProfileParameter(" + param + ")");
        }

        int[] getProfileParameter(int profile, int param, int length)
                throws IllegalStateException {
            // The Dolby wire format packs param, profile and a command suffix
            // into one int: (param << 16) | (profile << 8) | 0x05. All
            // parameters this port uses are < 0x100 and profiles are < 0x10, so
            // the shift is safe; assert it rather than silently truncating.
            if (param < 0 || param > 0xFF || profile < 0 || profile > 0xFF) {
                throw new IllegalArgumentException(
                        "param/profile out of range: " + param + "/" + profile);
            }
            if (length < 1 || length > 20) {
                throw new IllegalArgumentException("Invalid parameter length " + length);
            }
            byte[] buf = new byte[(length + 2) * 4];
            int cmd = (param << 16) + (profile << 8) + 0x01000005;
            int ret = getParameter(cmd, buf);
            checkRead(ret, length * 4, buf.length, "getProfileParameter(" + param + ")");
            int[] out = new int[length];
            for (int i = 0; i < length; i++) {
                out[i] = readInt(buf, i * 4);
            }
            return out;
        }

        void setProfile(int profile) throws IllegalStateException {
            setInt(PARAM_PROFILE, profile);
        }

        int getProfile() throws IllegalStateException {
            return getInt(PARAM_PROFILE);
        }

        void setDsOn(boolean on) throws IllegalStateException {
            setInt(PARAM_ENABLE, on ? 1 : 0);
            int ret = setEnabled(on);
            if (ret != SUCCESS) {
                throw new IllegalStateException("setEnabled returned " + ret);
            }
        }

        boolean getDsOn() throws IllegalStateException {
            return getInt(PARAM_ENABLE) > 0;
        }

        private static void checkRead(int ret, int required, int capacity, String what) {
            // AudioEffect.getParameter returns the number of bytes read, NOT
            // SUCCESS (0). Refuse short replies instead of reading zero padding.
            if (ret < required || ret > capacity) {
                throw new IllegalStateException(what + " returned " + ret
                        + " bytes; required " + required + ".." + capacity);
            }
        }

        private static void check(int ret, String what) {
            if (ret != SUCCESS) {
                throw new IllegalStateException(what + " returned " + ret);
            }
        }

        private static void putInt(int value, byte[] dst, int off) {
            dst[off] = (byte) (value & 0xFF);
            dst[off + 1] = (byte) ((value >>> 8) & 0xFF);
            dst[off + 2] = (byte) ((value >>> 16) & 0xFF);
            dst[off + 3] = (byte) ((value >>> 24) & 0xFF);
        }

        private static int readInt(byte[] src, int off) {
            return (src[off] & 0xFF)
                    | ((src[off + 1] & 0xFF) << 8)
                    | ((src[off + 2] & 0xFF) << 16)
                    | ((src[off + 3] & 0xFF) << 24);
        }
    }
}
