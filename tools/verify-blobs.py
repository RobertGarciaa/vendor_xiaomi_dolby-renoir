#!/usr/bin/env python3
#
# Copyright (C) 2026 The LineageOS Project
# SPDX-License-Identifier: Apache-2.0
#
"""Verify that the Dolby blobs in this repository match pinned hashes.

Two things are checked:

  1. Every entry in proprietary-files.sha256sum exists under proprietary/ and
     has the recorded SHA-256. Source paths in the OTA and install paths in
     the tree are identical for this module, so the recorded path is used
     directly.
  2. The implementation UUID compiled into the installed libswdap.so is the
     software DAP UUID that audio_effects_dolby.xml registers. A mismatch here
     is the single most likely way for this port to end up with a toggle that
     does nothing, so it is checked mechanically rather than by eye.

Exit status is non-zero on any failure.
"""

import argparse
import hashlib
import os
import re
import sys

SDAP_SW_UUID = "6ab06da4-c516-4611-8166-452799218539"
SDAP_HW_UUID = "9d4921da-8225-4f29-aefa-39537a04bcaa"


def die(msg):
    sys.stderr.write("verify-blobs: error: %s\n" % msg)
    sys.exit(1)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def uuid_forms(uuid_str):
    """Return the byte sequences an effect_uuid_t may take on disk.

    effect_uuid_t is a packed struct of uint32 + uint16 + uint16 + uint16 +
    uint8[6]. The multi-byte fields are written in host (little-endian) order
    while the last six node bytes are an array, so the on-disk bytes are:

        timeLow LE | timeMid LE | timeHi LE | clockSeq LE | node[6]

    The descriptor in Redwood's libswdap.so was confirmed to use exactly this
    layout (the SW UUID appears at file offset 204112 as
    a4 6d b0 6a 16 c5 11 46 66 81 45 27 99 21 85 39). Also accept the plain
    big-endian byte order so the check still works if a vendor ever emits the
    RFC 4122 wire form.
    """
    h = uuid_str.replace("-", "")
    time_low = int(h[0:8], 16)
    time_mid = int(h[8:12], 16)
    time_hi = int(h[12:16], 16)
    clock_seq = int(h[16:20], 16)
    node = bytes.fromhex(h[20:32])
    packed = (time_low.to_bytes(4, "little")
              + time_mid.to_bytes(2, "little")
              + time_hi.to_bytes(2, "little")
              + clock_seq.to_bytes(2, "little")
              + node)
    big_endian = bytes.fromhex(h)
    return {packed, big_endian}


def read_uuid_at(path, offset):
    with open(path, "rb") as f:
        f.seek(offset)
        return f.read(16)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.getcwd(),
                    help="repository root (default: cwd)")
    ap.add_argument("--skip-uuid", action="store_true",
                    help="only check file hashes")
    args = ap.parse_args(argv)

    root = os.path.abspath(args.dir)
    sums = os.path.join(root, "proprietary-files.sha256sum")
    if not os.path.isfile(sums):
        die("%s missing" % sums)

    expected = []
    with open(sums) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            digest, size, path = line.split(None, 2)
            expected.append((digest, int(size), path))

    failures = []
    missing = 0
    for digest, size, path in expected:
        local = os.path.join(root, "proprietary", path)
        if not os.path.isfile(local):
            missing += 1
            continue
        actual_size = os.path.getsize(local)
        if actual_size != size:
            failures.append("%s: size %d != expected %d"
                            % (path, actual_size, size))
            continue
        actual = sha256_file(local)
        if actual != digest:
            failures.append("%s: sha256 %s != expected %s"
                            % (path, actual, digest))

    if missing:
        sys.stderr.write(
            "verify-blobs: %d blob(s) not present under proprietary/.\n"
            "This repository does not redistribute proprietary Xiaomi files.\n"
            "Run extract-files.py against a Redwood dump first.\n"
            % missing)
        for digest, size, path in expected:
            local = os.path.join(root, "proprietary", path)
            if not os.path.isfile(local):
                sys.stderr.write("  missing: proprietary/%s\n" % path)
        return 1

    if failures:
        for f in failures:
            sys.stderr.write("verify-blobs: %s\n" % f)
        return 1

    print("verify-blobs: %d blobs match proprietary-files.sha256sum"
          % len(expected))

    # DMS's private legacy foundation is a separately pinned APEX extraction,
    # not a modified vendor source blob from proprietary-files.sha256sum.
    from dms_foundation_compat import pinned, FOUNDATION_SHA, RELATIVE
    try:
        with open(os.path.join(root, 'proprietary', RELATIVE), 'rb') as stream:
            pinned(stream.read(), FOUNDATION_SHA)
    except (OSError, ValueError) as error:
        die('DMS foundation missing/stale; rerun extract-files.py: ' + str(error))
    print('verify-blobs: DMS private VNDK30 foundation matches pinned source')

    if args.skip_uuid:
        return 0

    effects = os.path.join(root, "configs", "audio", "audio_effects_dolby.xml")
    if not os.path.isfile(effects):
        die("%s missing" % effects)
    with open(effects, encoding="utf-8") as f:
        text = f.read()
    if SDAP_SW_UUID not in text:
        die("audio_effects_dolby.xml does not register the software DAP UUID "
            "%s" % SDAP_SW_UUID)
    if SDAP_HW_UUID in text:
        die("audio_effects_dolby.xml registers the hardware DAP UUID %s, "
            "which libswdap.so does not export" % SDAP_HW_UUID)

    for directory in ("lib", "lib64"):
        sdap = os.path.join(root, "proprietary", "vendor", directory,
                            "soundfx", "libswdap.so")
        if not os.path.isfile(sdap):
            die("%s missing" % sdap)
        # The descriptor UUID lives in .rodata. Rather than trust a fixed offset,
        # search the file for the on-disk encodings of each candidate UUID.
        with open(sdap, "rb") as f:
            blob = f.read()
        has_sw = any(form in blob for form in uuid_forms(SDAP_SW_UUID))
        has_hw = any(form in blob for form in uuid_forms(SDAP_HW_UUID))
        if not has_sw:
            die("libswdap.so does not contain the software DAP UUID %s; "
                "this is not the Redwood software engine" % SDAP_SW_UUID)
        if has_hw:
            die("libswdap.so contains the hardware DAP UUID %s; refusing to "
                "register the software UUID against this blob" % SDAP_HW_UUID)

        print("verify-blobs: libswdap.so exposes %s and not %s"
              % (SDAP_SW_UUID, SDAP_HW_UUID))
    return 0


if __name__ == "__main__":
    sys.exit(main())
