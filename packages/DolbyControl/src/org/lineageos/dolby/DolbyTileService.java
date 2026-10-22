/*
 * Copyright (C) 2026 The LineageOS Project
 * SPDX-License-Identifier: Apache-2.0
 *
 * Quick Settings tile for Dolby.
 *
 * Tap toggles the engine; the tile state is read back after the change, so a
 * rejected toggle shows as failed instead of optimistically flipping the icon.
 * Long press opens Settings, which routes on into MiSound via
 * DolbySettingsActivity.
 *
 * The tile does not create its own AudioEffect. It goes through the same
 * controller as the settings entry, and control is arbitrated there: MiSound
 * owns the effect while its UI is open, this service takes it back otherwise.
 */

package org.lineageos.dolby;

import android.graphics.drawable.Icon;
import android.service.quicksettings.Tile;
import android.service.quicksettings.TileService;
import android.widget.Toast;

public final class DolbyTileService extends TileService {
    private final Runnable mRefresh = this::refresh;

    @Override
    public void onStartListening() {
        super.onStartListening();
        DolbyEffectController.get(this).addListener(mRefresh);
        DolbyEffectService.start(this);
        refresh();
    }

    @Override
    public void onClick() {
        super.onClick();
        DolbyEffectController controller = DolbyEffectController.get(this);
        Boolean actual = controller.readEnabled();
        if (actual == null) {
            DolbyEffectService.start(this);
            refresh();
            return;
        }
        boolean target = !actual;
        DolbyEffectController.Result result = controller.setEnabled(target);
        if (!result.ok) {
            Toast.makeText(this, result.message, Toast.LENGTH_SHORT).show();
        }
        refresh();
    }

    @Override
    public void onStopListening() {
        DolbyEffectController.get(this).removeListener(mRefresh);
        super.onStopListening();
    }

    @Override
    public void onTileAdded() {
        super.onTileAdded();
        DolbyEffectService.start(this);
        refresh();
    }


    private void refresh() {
        Tile tile = getQsTile();
        if (tile == null) {
            return;
        }
        DolbyEffectController controller = DolbyEffectController.get(this);
        Boolean actual = controller.readEnabled();
        if (actual == null) {
            // Engine not reachable: unavailable is the honest state.
            tile.setState(Tile.STATE_UNAVAILABLE);
        } else {
            tile.setState(actual ? Tile.STATE_ACTIVE : Tile.STATE_INACTIVE);
        }
        tile.setIcon(Icon.createWithResource(this, R.drawable.ic_dolby));
        tile.setLabel(getString(R.string.dolby_title));
        Integer profile = controller.readProfile();
        tile.setSubtitle(actual == null || profile == null
                ? getString(R.string.dolby_unavailable)
                : getString(profileLabel(profile)));
        tile.updateTile();
    }

    private int profileLabel(int profile) {
        switch (profile) {
            case DolbyEffectService.PROFILE_MOVIE:
                return R.string.profile_movie;
            case DolbyEffectService.PROFILE_MUSIC:
                return R.string.profile_music;
            case DolbyEffectService.PROFILE_VOICE:
                return R.string.profile_voice;
            case DolbyEffectService.PROFILE_DYNAMIC:
            default:
                return R.string.profile_dynamic;
        }
    }

}
