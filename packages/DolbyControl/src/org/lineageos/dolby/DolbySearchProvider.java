/*
 * Copyright (C) 2026 The LineageOS Project
 * SPDX-License-Identifier: Apache-2.0
 *
 * Search provider for Dolby settings.
 *
 * Uses this app's own authority (org.lineageos.dolby.search) rather than
 * com.android.settings. The LTPO reference commit reused the Settings
 * authority, which collides with the real Settings provider and can break
 * search indexing. Only one entry is published: Dolby settings, which opens
 * the entry activity and forwards into MiSound.
 */

package org.lineageos.dolby;

import android.content.Context;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.provider.SearchIndexablesContract;
import android.provider.SearchIndexablesProvider;

public final class DolbySearchProvider extends SearchIndexablesProvider {
    @Override
    public boolean onCreate() {
        return true;
    }

    @Override
    public Cursor queryXmlResources(String[] projection) {
        MatrixCursor cursor = new MatrixCursor(
                SearchIndexablesContract.INDEXABLES_XML_RES_COLUMNS);
        return cursor;
    }

    @Override
    public Cursor queryRawData(String[] projection) {
        MatrixCursor cursor = new MatrixCursor(
                SearchIndexablesContract.INDEXABLES_RAW_COLUMNS);
        Context context = getContext();
        if (context == null) {
            return cursor;
        }
        // The platform asks for the full column set; every column in the
        // contract must be filled or the row is rejected during indexing.
        Object[] row =
                new Object[SearchIndexablesContract.INDEXABLES_RAW_COLUMNS.length];
        row[SearchIndexablesContract.COLUMN_INDEX_RAW_RANK] = 0;
        row[SearchIndexablesContract.COLUMN_INDEX_RAW_TITLE] =
                context.getString(R.string.dolby_title);
        row[SearchIndexablesContract.COLUMN_INDEX_RAW_SUMMARY_ON] =
                context.getString(R.string.dolby_summary);
        row[SearchIndexablesContract.COLUMN_INDEX_RAW_SUMMARY_OFF] =
                context.getString(R.string.dolby_summary);
        row[SearchIndexablesContract.COLUMN_INDEX_RAW_ENTRIES] = null;
        row[SearchIndexablesContract.COLUMN_INDEX_RAW_KEYWORDS] =
                context.getString(R.string.dolby_keywords);
        row[SearchIndexablesContract.COLUMN_INDEX_RAW_SCREEN_TITLE] =
                context.getString(R.string.dolby_title);
        row[SearchIndexablesContract.COLUMN_INDEX_RAW_CLASS_NAME] =
                DolbySettingsActivity.class.getName();
        row[SearchIndexablesContract.COLUMN_INDEX_RAW_ICON_RESID] =
                R.drawable.ic_dolby;
        row[SearchIndexablesContract.COLUMN_INDEX_RAW_INTENT_ACTION] =
                "com.android.settings.action.IA_SETTINGS";
        row[SearchIndexablesContract.COLUMN_INDEX_RAW_INTENT_TARGET_PACKAGE] =
                context.getPackageName();
        row[SearchIndexablesContract.COLUMN_INDEX_RAW_INTENT_TARGET_CLASS] =
                DolbySettingsActivity.class.getName();
        row[SearchIndexablesContract.COLUMN_INDEX_RAW_KEY] = "dolby_settings";
        row[SearchIndexablesContract.COLUMN_INDEX_RAW_USER_ID] = 0;
        row[SearchIndexablesContract.COLUMN_INDEX_RAW_PAYLOAD_TYPE] = null;
        row[SearchIndexablesContract.COLUMN_INDEX_RAW_PAYLOAD] = null;
        cursor.addRow(row);
        return cursor;
    }

    @Override
    public Cursor queryNonIndexableKeys(String[] projection) {
        MatrixCursor cursor = new MatrixCursor(
                SearchIndexablesContract.NON_INDEXABLES_KEYS_COLUMNS);
        return cursor;
    }
}
