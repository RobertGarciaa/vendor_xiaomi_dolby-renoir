/* Copyright (C) 2026 The LineageOS Project
 * SPDX-License-Identifier: Apache-2.0
 */
package org.lineageos.dolby;

import android.content.Context;
import android.content.SharedPreferences;
import android.util.Log;
import android.os.Handler;
import android.os.Looper;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/** Live engine state is authoritative; stored values are for a fresh engine. */
public final class DolbyEffectController {
    private static final String TAG = "DolbyEffect";
    private static DolbyEffectController sInstance;
    private final SharedPreferences mPrefs;
    private final List<Runnable> mListeners = new ArrayList<>();
    private DolbyEffectService mService;
    private final Handler mHandler = new Handler(Looper.getMainLooper());
    private boolean mEnablePending;

    public boolean isEnablePending() { return mEnablePending; }

    /** Acknowledge DMS state asynchronously; never resend a toggle while pending. */
    public void setEnabledAsync(boolean enabled, Callback callback) {
        if (mEnablePending) return;
        final DolbyEffectService service = mService;
        if (service == null) {
            callback.onResult(Result.fail("Dolby service is not running"));
            return;
        }
        mEnablePending = true;
        synchronized (service.lock()) {
            DolbyEffectService.DolbyAudioEffect writer = null;
            try {
                writer = service.ensureControlLocked();
                if (writer == null) throw new IllegalStateException("Dolby effect is unavailable");
                writer.setDsOn(enabled);
            } catch (RuntimeException ex) {
                Log.e(TAG, "Enable command failed", ex);
                mEnablePending = false;
                callback.onResult(Result.fail("Engine rejected change: " + ex.getMessage()));
                return;
            } finally {
                service.releaseControlLocked(writer);
            }
        }
        // SET_PARAM acceptance precedes DMS parameter-update delivery. Readback
        // immediately after SET can still contain the previous state.
        mHandler.postDelayed(new Runnable() {
            private int remaining = 20;
            @Override public void run() {
                Boolean actual = mService == service ? readEnabled() : null;
                if (actual != null && actual == enabled) {
                    finish(Result.ok());
                } else if (mService != service || --remaining == 0) {
                    Log.w(TAG, "Enable confirmation failed: target=" + enabled + " actual=" + actual);
                    finish(Result.fail("Dolby state change was not confirmed"));
                } else {
                    mHandler.postDelayed(this, 50);
                }
            }
            private void finish(Result result) {
                mEnablePending = false;
                captureEngineState("enable confirmation");
                if (result.ok) service.notifyStateChanged();
                callback.onResult(result);
            }
        }, 50);
    }

    private DolbyEffectController(Context context) { mPrefs = DolbyPrefs.get(context); }
    public static synchronized DolbyEffectController get(Context context) {
        if (sInstance == null) sInstance = new DolbyEffectController(context.getApplicationContext());
        return sInstance;
    }
    void attachService(DolbyEffectService service) {
        mService = service;
        applyPersistedState("service attached");
    }
    void detachService() { mService = null; notifyListeners(); }
    public void addListener(Runnable listener) {
        if (!mListeners.contains(listener)) mListeners.add(listener);
    }
    public void removeListener(Runnable listener) { mListeners.remove(listener); }
    private void notifyListeners() {
        for (Runnable listener : new ArrayList<>(mListeners)) listener.run();
    }
    public static final class Result {
        public final boolean ok;
        public final String message;
        private Result(boolean ok, String message) { this.ok = ok; this.message = message; }
        static Result ok() { return new Result(true, null); }
        static Result fail(String message) { return new Result(false, message); }
    }
    public interface Callback { void onResult(Result result); }
    public boolean isEnabledRequested() { return mPrefs.getBoolean(DolbyPrefs.KEY_ENABLED, false); }
    public int getRequestedProfile() {
        return mPrefs.getInt(DolbyPrefs.KEY_PROFILE, DolbyEffectService.PROFILE_DYNAMIC);
    }
    public Boolean readEnabled() {
        DolbyEffectService service = mService;
        if (service == null) return null;
        synchronized (service.lock()) {
            try {
                DolbyEffectService.DolbyAudioEffect e = service.getEffectLocked();
                return e == null ? null : e.getDsOn();
            } catch (RuntimeException ex) { Log.w(TAG, "readEnabled failed", ex); return null; }
        }
    }
    public Integer readProfile() {
        DolbyEffectService service = mService;
        if (service == null) return null;
        synchronized (service.lock()) {
            try {
                DolbyEffectService.DolbyAudioEffect e = service.getEffectLocked();
                return e == null ? null : e.getProfile();
            } catch (RuntimeException ex) { Log.w(TAG, "readProfile failed", ex); return null; }
        }
    }
    public boolean hasControl() {
        DolbyEffectService service = mService;
        if (service == null) return false;
        synchronized (service.lock()) {
            DolbyEffectService.DolbyAudioEffect e = service.getEffectLocked();
            return e != null && e.hasControl();
        }
    }
    private interface Mutation { void run(DolbyEffectService.DolbyAudioEffect effect); }
    private Result mutate(Mutation mutation) {
        DolbyEffectService service = mService;
        if (service == null) return Result.fail("Dolby service is not running");
        synchronized (service.lock()) {
            DolbyEffectService.DolbyAudioEffect writer = null;
            try {
                writer = service.ensureControlLocked();
                if (writer == null) return Result.fail("Dolby effect is unavailable");
                mutation.run(writer);
            } catch (RuntimeException ex) {
                Log.e(TAG, "Engine rejected change", ex);
                return Result.fail("Engine rejected change: " + ex.getMessage());
            } finally {
                service.releaseControlLocked(writer);
            }
        }
        captureEngineState("explicit change");
        service.notifyStateChanged();
        return Result.ok();
    }
    public Result setEnabled(boolean enabled) {
        return mutate(e -> {
            // The live profile/EQ must survive a QS enable/disable unchanged.
            e.setDsOn(enabled);
            if (e.getDsOn() != enabled) throw new IllegalStateException("Enable readback mismatch");
        });
    }
    public Result setProfile(int profile) {
        if (!DolbyPrefs.isKnownProfile(profile)) return Result.fail("Unknown profile " + profile);
        return mutate(e -> {
            e.setProfile(profile);
            if (e.getProfile() != profile) throw new IllegalStateException("Profile readback mismatch");
        });
    }
    public Result setProfileParameter(int param, int[] values, String label) {
        if (param < 101 || param > 116 || values == null
                || values.length != (param == 110 ? 20 : 1)) return Result.fail("Invalid parameter");
        return mutate(e -> {
            int profile = e.getProfile();
            e.setProfileParameter(profile, param, values);
            if (!Arrays.equals(e.getProfileParameter(profile, param, values.length), values))
                throw new IllegalStateException(label + " readback mismatch");
        });
    }
    public int[] getProfileParameter(int param, int length) {
        DolbyEffectService service = mService;
        if (service == null) return null;
        synchronized (service.lock()) {
            try {
                DolbyEffectService.DolbyAudioEffect e = service.getEffectLocked();
                return e == null ? null : e.getProfileParameter(e.getProfile(), param, length);
            } catch (RuntimeException ex) { Log.w(TAG, "Parameter read failed", ex); return null; }
        }
    }
    /** Observe changes from MiSound without recreating handles or writing state. */
    void captureEngineState(String reason) {
        DolbyEffectService service = mService;
        if (service == null) return;
        synchronized (service.lock()) {
            DolbyEffectService.DolbyAudioEffect e = service.getEffectLocked();
            if (e == null) { notifyListeners(); return; }
            try {
                boolean enabled = e.getDsOn();
                int profile = e.getProfile();
                if (!DolbyPrefs.isKnownProfile(profile)) {
                    Log.w(TAG, "Unrecognized live profile; not persisting " + profile);
                    notifyListeners();
                    return;
                }
                SharedPreferences.Editor edit = mPrefs.edit()
                        .putBoolean(DolbyPrefs.KEY_ENABLED, enabled)
                        .putInt(DolbyPrefs.KEY_PROFILE, profile);
                // MiSound's EQ editor updates multiple profiles. Capture each
                // verified parameter, including profiles not currently active.
                for (int p : DolbyPrefs.KNOWN_PROFILES) {
                    for (int param = 101; param <= 116; param++) {
                        String key = DolbyPrefs.profileParameterKey(p, param);
                        try {
                            int[] value = e.getProfileParameter(p, param, param == 110 ? 20 : 1);
                            edit.putString(key, DolbyPrefs.joinInts(value));
                        } catch (RuntimeException unsupported) {
                            // Preserve absence, not invented defaults; never
                            // restore stale data for an unreadable parameter.
                            edit.remove(key);
                        }
                    }
                }
                edit.apply();
            } catch (RuntimeException ex) { Log.w(TAG, "Capture failed: " + reason, ex); }
        }
        notifyListeners();
    }
    /** Restore on initial service creation, not on queries or route notifications. */
    public void applyPersistedState(String reason) {
        DolbyEffectService service = mService;
        if (service == null) return;
        synchronized (service.lock()) {
            DolbyEffectService.DolbyAudioEffect writer = null;
            try {
                DolbyEffectService.DolbyAudioEffect keeper = service.getEffectLocked();
                if (keeper == null) return;
                if (!keeper.hasControl()) {
                    // An existing MiSound owner already has authoritative state.
                    captureEngineState("existing owner");
                    return;
                }
                writer = service.ensureControlLocked();
                int profile = getRequestedProfile();
                if (!DolbyPrefs.isKnownProfile(profile)) profile = DolbyEffectService.PROFILE_DYNAMIC;
                for (int p : DolbyPrefs.KNOWN_PROFILES) {
                    for (int param = 101; param <= 116; param++) {
                        int[] value = DolbyPrefs.parseInts(mPrefs.getString(
                                DolbyPrefs.profileParameterKey(p, param), null));
                        if (value != null && value.length == (param == 110 ? 20 : 1)) {
                            writer.setProfileParameter(p, param, value);
                            if (!Arrays.equals(value, writer.getProfileParameter(p, param, value.length)))
                                throw new IllegalStateException("Restored parameter mismatch");
                        }
                    }
                }
                writer.setProfile(profile);
                boolean enabled = isEnabledRequested();
                writer.setDsOn(enabled);
                if (writer.getProfile() != profile || writer.getDsOn() != enabled)
                    throw new IllegalStateException("Restore readback mismatch");
            } catch (RuntimeException ex) { Log.e(TAG, "Restore failed: " + reason, ex); }
            finally { service.releaseControlLocked(writer); }
        }
        notifyListeners();
    }
}
