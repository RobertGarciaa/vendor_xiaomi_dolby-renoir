#!/usr/bin/env python3
#
# Copyright (C) 2026 The LineageOS Project
# SPDX-License-Identifier: Apache-2.0
#
"""Copy the Dolby blobs out of a Redwood dump and verify them.

This repository is hand-maintained: Android.bp declares the Soong modules
explicitly, so it does not use extract-utils' makefile/bp generation (which
would overwrite Android.bp). This script therefore only does the one thing that
needs automating - copy the files listed in proprietary-files.txt and check
them against the pinned hashes.

Usage:
  ./extract-files.py <redwood-dump-dir>
  ./extract-files.py --verify-only

The dump is the extracted OTA tree, e.g.
  redwood_global-ota_full-OS2.0.17.0.UMSMIXM-user-14.0-4ddcd3c40c
containing product/ and vendor/ at its root.
"""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROPRIETARY = os.path.join(HERE, 'proprietary')
SUMS = os.path.join(HERE, 'proprietary-files.sha256sum')
LIST = os.path.join(HERE, 'proprietary-files.txt')


def die(msg):
    sys.stderr.write('extract-files: error: %s\n' % msg)
    sys.exit(1)


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def read_sums():
    expected = []
    with open(SUMS) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            digest, size, rel = line.split(None, 2)
            expected.append((digest, int(size), rel))
    return expected


def read_list():
    paths = []
    with open(LIST) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            paths.append(line)
    return paths


def extract(dump):
    expected = read_sums()
    listed = read_list()

    # The list and the checksum file must describe the same set, or a blob
    # would be silently copied without verification.
    if sorted(p for _d, _s, p in expected) != sorted(listed):
        missing = set(listed) - {p for _d, _s, p in expected}
        extra = {p for _d, _s, p in expected} - set(listed)
        die('proprietary-files.txt and proprietary-files.sha256sum disagree\n'
            '  only in list: %s\n  only in sums: %s'
            % (sorted(missing), sorted(extra)))

    for path in listed:
        src = os.path.join(dump, path)
        if not os.path.isfile(src):
            die('%s not found in the dump' % path)

    # Validate the complete input before replacing any existing output.
    for digest, _size, path in expected:
        src = os.path.join(dump, path)
        actual = sha256(src)
        if actual != digest:
            die('%s: sha256 %s != expected %s\n'
                'The dump does not match the pinned Redwood build.'
                % (path, actual, digest))
    for digest, _size, path in expected:
        src = os.path.join(dump, path)
        dst = os.path.join(PROPRIETARY, path)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        # Keep the executable bit for binaries.
        if '/bin/' in path or path.endswith('-service'):
            os.chmod(dst, 0o755)
        else:
            os.chmod(dst, 0o644)
        print('extract-files: %s' % path)

    print('extract-files: %d blobs copied and verified' % len(expected))


def verify_only():
    expected = read_sums()
    failures = []
    for digest, size, path in expected:
        local = os.path.join(PROPRIETARY, path)
        if not os.path.isfile(local):
            failures.append('%s: missing' % path)
            continue
        actual_size = os.path.getsize(local)
        if actual_size != size:
            failures.append('%s: size %d != %d' % (path, actual_size, size))
            continue
        actual = sha256(local)
        if actual != digest:
            failures.append('%s: sha256 %s != %s' % (path, actual, digest))
    if failures:
        for f in failures:
            sys.stderr.write('extract-files: %s\n' % f)
        return 1
    print('extract-files: %d blobs verified' % len(expected))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('dump', nargs='?',
                    help='Redwood dump root (contains product/ and vendor/)')
    ap.add_argument('--verify-only', action='store_true',
                    help='only check the blobs already in proprietary/')
    args = ap.parse_args()

    if args.verify_only:
        rc = verify_only()
    else:
        if not args.dump:
            die('a dump directory is required (or pass --verify-only)')
        if not os.path.isdir(args.dump):
            die('%s is not a directory' % args.dump)
        extract(args.dump)
        rc = 0

    if rc == 0:
        # Reuse the shared verifier so the UUID/effects checks always run too.
        rc = subprocess.call([sys.executable,
                              os.path.join(HERE, 'tools', 'verify-blobs.py'),
                              '--dir', HERE])
    return rc


if __name__ == '__main__':
    sys.exit(main())
