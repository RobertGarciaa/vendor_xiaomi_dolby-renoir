#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Collect an explicitly requested, read-only ADB audio-route snapshot.

Never changes mixer controls, volume, properties, SELinux, calibration, or EQ.
The caller supplies an empty output directory and optional device serial.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('output', type=Path)
    ap.add_argument('--serial')
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    adb = ['adb'] + (['-s', args.serial] if args.serial else [])
    commands = {
        'identity': ['getprop'],
        'cards': ['cat', '/proc/asound/cards'],
        'mixer': ['tinymix'],
        'audio-flinger': ['dumpsys', 'media.audio_flinger'],
        'audio-policy': ['dumpsys', 'media.audio_policy'],
        'tfa-firmware-sha256': ['sha256sum', '/vendor/firmware/tfa98xx.cnt'],
    }
    manifest = []
    for name, command in commands.items():
        cmd = adb + ['shell'] + command
        try:
            p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)
            content, status = p.stdout, p.returncode
        except subprocess.TimeoutExpired as e:
            content, status = (e.stdout or b'') + b'\nTIMEOUT\n', None
        target = args.output / (name + '.txt')
        target.write_bytes(content)
        manifest.append(dict(file=target.name, command=cmd, returncode=status,
                             sha256=hashlib.sha256(content).hexdigest()))
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('Read-only snapshot saved to', args.output)
    print('Review returncode in manifest; denied/missing commands are not successful evidence.')


if __name__ == '__main__':
    main()
