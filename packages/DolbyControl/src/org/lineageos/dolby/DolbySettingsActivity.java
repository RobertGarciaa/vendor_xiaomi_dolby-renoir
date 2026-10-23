/* Copyright (C) 2026 The LineageOS Project
 * SPDX-License-Identifier: Apache-2.0
 */
package org.lineageos.dolby;

import android.content.ActivityNotFoundException;
import android.content.ComponentName;
import android.content.Intent;
import android.os.Bundle;
import android.preference.ListPreference;
import android.preference.Preference;
import android.preference.PreferenceActivity;
import android.preference.PreferenceScreen;
import android.preference.SwitchPreference;
import android.widget.Toast;

/** Small DAP entry screen; the graphic equalizer remains the original MiSound UI. */
@SuppressWarnings("deprecation")
public final class DolbySettingsActivity extends PreferenceActivity {
    private DolbyEffectController mController;
    private SwitchPreference mEnabled;
    private ListPreference mProfile;
    private Preference mEqualizer;
    private boolean mListening;
    private final Runnable mRefresh = () -> runOnUiThread(() -> {
        if (mListening && !isFinishing() && !isDestroyed()) refresh();
    });

    @Override
    public void onCreate(Bundle state) {
        super.onCreate(state);
        setTitle(R.string.dolby_title);
        mController = DolbyEffectController.get(this);
        PreferenceScreen screen = getPreferenceManager().createPreferenceScreen(this);
        setPreferenceScreen(screen);

        mEnabled = new SwitchPreference(this);
        mEnabled.setTitle(R.string.dolby_title);
        mEnabled.setPersistent(false);
        mEnabled.setOnPreferenceChangeListener((preference, value) -> {
            showFailure(mController.setEnabled((Boolean) value));
            refresh();
            // Never let Preference overwrite the live readback with the request.
            return false;
        });
        screen.addPreference(mEnabled);

        mProfile = new ListPreference(this);
        mProfile.setTitle(R.string.dolby_profile);
        mProfile.setPersistent(false);
        mProfile.setEntries(new CharSequence[] {
                getString(R.string.profile_dynamic), getString(R.string.profile_movie),
                getString(R.string.profile_music), getString(R.string.profile_voice)});
        mProfile.setEntryValues(new CharSequence[] {
                Integer.toString(DolbyEffectService.PROFILE_DYNAMIC),
                Integer.toString(DolbyEffectService.PROFILE_MOVIE),
                Integer.toString(DolbyEffectService.PROFILE_MUSIC),
                Integer.toString(DolbyEffectService.PROFILE_VOICE)});
        mProfile.setOnPreferenceChangeListener((preference, value) -> {
            try {
                showFailure(mController.setProfile(Integer.parseInt((String) value)));
            } catch (NumberFormatException invalid) {
                Toast.makeText(this, R.string.dolby_unavailable, Toast.LENGTH_SHORT).show();
            }
            refresh();
            return false;
        });
        screen.addPreference(mProfile);

        mEqualizer = new Preference(this);
        mEqualizer.setTitle(R.string.dolby_equalizer);
        mEqualizer.setSummary(R.string.dolby_equalizer_summary);
        mEqualizer.setOnPreferenceClickListener(preference -> {
            if (!DolbyPrefs.isSupported(this)) {
                Toast.makeText(this, R.string.dolby_capability_unavailable, Toast.LENGTH_LONG).show();
                return true;
            }
            Intent intent = new Intent("miui.intent.action.DOLBY_GEQ_SETTING");
            intent.setComponent(new ComponentName("com.miui.misound",
                    "com.miui.misound.dolby.DolbyEqActivity"));
            try {
                startActivity(intent);
            } catch (ActivityNotFoundException | SecurityException unavailable) {
                Toast.makeText(this, R.string.misound_missing, Toast.LENGTH_LONG).show();
            }
            return true;
        });
        screen.addPreference(mEqualizer);
        DolbyEffectService.start(this);
        refresh();
    }

    @Override
    protected void onResume() {
        super.onResume();
        mListening = true;
        mController.addListener(mRefresh);
        DolbyEffectService.start(this);
        refresh();
    }

    @Override
    protected void onPause() {
        mListening = false;
        mController.removeListener(mRefresh);
        super.onPause();
    }

    private void showFailure(DolbyEffectController.Result result) {
        if (!result.ok) Toast.makeText(this, result.message, Toast.LENGTH_LONG).show();
    }

    private void refresh() {
        Boolean enabled = mController.readEnabled();
        Integer profile = mController.readProfile();
        boolean ready = enabled != null && profile != null && DolbyPrefs.isKnownProfile(profile);
        mEnabled.setEnabled(ready);
        mEnabled.setChecked(Boolean.TRUE.equals(enabled));
        mEnabled.setSummary(ready ? null : getString(R.string.dolby_unavailable));
        mProfile.setEnabled(ready);
        boolean supported = DolbyPrefs.isSupported(this);
        mEqualizer.setEnabled(ready && supported);
        mEqualizer.setSummary(supported ? R.string.dolby_equalizer_summary
                : R.string.dolby_capability_unavailable);
        if (ready) {
            mProfile.setValue(Integer.toString(profile));
            mProfile.setSummary(mProfile.getEntry());
        } else {
            mProfile.setValue(null);
            mProfile.setSummary(R.string.dolby_unavailable);
        }
    }
}
