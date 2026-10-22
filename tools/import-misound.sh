#!/bin/bash
#
# Copyright (C) 2026 The LineageOS Project
# SPDX-License-Identifier: Apache-2.0
#
# Build the ported MiSound APK from a Redwood dump.
#
# Run this once, before building the ROM, from the ROM root:
#
#   vendor/xiaomi/dolby-renoir/tools/import-misound.sh \
#       --dump /path/to/redwood-dump
#
# It extracts MiSound.apk from the dump, verifies its SHA-256 against the pinned
# value, rewrites the Dolby effect UUIDs to the software DAP, bundles the MIUI
# compatibility shims as classes2.dex, signs the result with the platform key,
# and writes it to vendor/xiaomi/dolby-renoir/proprietary/product/app/MiSound/.
#
# The output is not committed. It is not byte-reproducible, because zip entries carry build-time metadata, so instead of
# pinning an output hash this script prints the result and patch-misound.py
# re-verifies the things that actually matter: the two software UUIDs are
# present exactly once, the string pool is sorted, and the shim classes2.dex is
# a valid DEX. The input hash is pinned and is the real safety gate.
#
# Requirements: java, javac, baksmali, smali, zipalign, apksigner, d8. In the
# AOSP tree these are all under prebuilts/ and out/host/linux-x86/bin.
#

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$HERE")"

DUMP=""
ANDROID_JAR=""
BUILD_TOOLS=""
SIGNING_KEYS=""
ROM_ROOT=""

usage() {
    sed -n '2,30p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 1
}

while [ $# -gt 0 ]; do
    case "$1" in
        --rom-root) ROM_ROOT="$2"; shift 2 ;;
        --dump) DUMP="$2"; shift 2 ;;
        --android-jar) ANDROID_JAR="$2"; shift 2 ;;
        --build-tools) BUILD_TOOLS="$2"; shift 2 ;;
        --signing-keys) SIGNING_KEYS="$2"; shift 2 ;;
        -h|--help) usage ;;
        *) echo "unknown argument: $1" >&2; usage ;;
    esac
done

[ -n "$DUMP" ] || { echo "--dump is required" >&2; exit 1; }

# Find the ROM root by walking up for prebuilts/, so this works regardless of
# the current directory and whether the repo is linked or copied into the tree.
probe="${ROM_ROOT:-$REPO}"
for _ in 1 2 3 4 5 6 7 8; do
    if [ -d "$probe/prebuilts" ]; then ROM_ROOT="$probe"; break; fi
    probe="$(dirname "$probe")"
done
if [ -z "$ROM_ROOT" ]; then
    echo "could not find the ROM root (a directory containing prebuilts/)" >&2
    echo "pass --rom-root /path/to/ROM (supports an external checkout)" >&2
    exit 1
fi

# Defaults relative to the ROM root. ANDROID_JAR must expose the public SDK
# only; the shims use no hidden APIs.
ANDROID_JAR="${ANDROID_JAR:-$ROM_ROOT/prebuilts/sdk/current/public/android.jar}"
BUILD_TOOLS="${BUILD_TOOLS:-$ROM_ROOT/out/host/linux-x86/bin}"
SIGNING_KEYS="${SIGNING_KEYS:-$ROM_ROOT/build/make/target/product/security}"

for f in "$ANDROID_JAR" "$BUILD_TOOLS/zipalign" "$BUILD_TOOLS/apksigner" \
         "$SIGNING_KEYS/platform.pk8" "$SIGNING_KEYS/platform.x509.pem"; do
    [ -e "$f" ] || { echo "missing: $f" >&2; exit 1; }
done

OUT_DIR="$REPO/proprietary/product/app/MiSound"
OUT_APK="$OUT_DIR/MiSound.apk"
SRC_APK="$DUMP/product/app/MiSound/MiSound.apk"

[ -f "$SRC_APK" ] || { echo "MiSound.apk not found at $SRC_APK" >&2; exit 1; }

mkdir -p "$OUT_DIR"

python3 "$HERE/patch-misound.py" \
    --rom-root "$ROM_ROOT" \
    --apk "$SRC_APK" \
    --out "$OUT_APK" \
    --platform-key "$SIGNING_KEYS/platform.pk8" \
    --platform-cert "$SIGNING_KEYS/platform.x509.pem" \
    --build-tools "$BUILD_TOOLS" \
    --shim-src "$REPO/packages/MiSoundCompat/src" \
    --android-jar "$ANDROID_JAR"

echo
echo "MiSound patched and installed at:"
echo "  $OUT_APK"
echo "  sha256 $(sha256sum "$OUT_APK" | cut -d' ' -f1)"
echo
echo "This hash is informational: ZIP build metadata can vary, so the APK is"
echo "not byte-stable between runs. patch-misound.py already verified the two"
echo "software UUIDs, the sorted string pool and the shim classes2.dex."
