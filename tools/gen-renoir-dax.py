#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Generate renoir DAX from pinned Redwood settings.

With --donor, copy original taoyao landscape optimizer gains, including positive
values. Without it reproduce static-v1. All other bytes remain unchanged.
These are experimental candidates, not acoustic calibrations.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import xml.etree.ElementTree as ET

STOCK_SHA256 = 'd7e21ddb0f9d58330b655dd120799b3db46428f6840f87e707239644693a1a9c'


DONOR_SHA256 = '592576b5796841090534859d8caa0c6ac6f87a9ed618910bd51af4a0c4487b8e'


def derive(stock, donor=None):
    digest = hashlib.sha256(stock).hexdigest()
    if digest != STOCK_SHA256:
        raise ValueError('input is not the pinned Redwood DAX source')
    root = ET.fromstring(stock)
    targets = [t for t in root.findall('tuning') if t.get('name') == 'speaker_landscape']
    if len(targets) != 1 or targets[0].get('endpoint_type') != 'speaker':
        raise ValueError('expected exactly one speaker_landscape speaker tuning')
    blocks = list(re.finditer(rb'<tuning\b[^>]*\bname="speaker_landscape"[^>]*>.*?</tuning>',
                              stock, re.S))
    if len(blocks) != 1:
        raise ValueError('ambiguous landscape source block')
    block = blocks[0]
    optimizer = list(re.finditer(rb'<audio-optimizer-bands>.*?</audio-optimizer-bands>',
                                 block[0], re.S))
    if len(optimizer) != 1:
        raise ValueError('ambiguous optimizer block')
    opt = optimizer[0]
    donor_bands = None
    if donor is not None:
        if hashlib.sha256(donor).hexdigest() != DONOR_SHA256:
            raise ValueError('input is not the pinned taoyao reference')
        donor_root = ET.fromstring(donor)
        donor_targets = [t for t in donor_root.findall('tuning')
                         if t.get('name') == 'speaker_landscape' and t.get('endpoint_type') == 'speaker']
        if len(donor_targets) != 1:
            raise ValueError('ambiguous donor landscape tuning')
        bands = donor_targets[0].findall('.//band_optimizer')
        donor_bands = {int(b.get('frequency')): b for b in bands}
        source_bands = targets[0].findall('.//band_optimizer')
        if len(bands) != 20 or len(donor_bands) != 20 or len(source_bands) != 20 or set(donor_bands) != {int(b.get('frequency')) for b in source_bands}:
            raise ValueError('donor/source frequency grid mismatch')
    changes = []

    def band(match):
        element = ET.fromstring(match[0])
        frequency = int(element.get('frequency'))
        def gain(m):
            value = int(m['value'])
            channel = m['channel'].decode()
            target = int(donor_bands[frequency].get('gain_' + channel)) if donor_bands is not None else min(0, value)
            if target == value:
                return m[0]
            changes.append(dict(frequency=frequency, channel=channel, before=value, after=target))
            return m['prefix'] + str(target).encode() + b'"'

        return re.sub(rb'(?P<prefix>gain_(?P<channel>left|right)=")(?P<value>-?\d+)"',
                      gain, match[0])

    tuned_opt, count = re.subn(rb'<band_optimizer\b[^>]*/>', band, opt[0])
    if count != 20 or not changes:
        raise ValueError('expected 20 optimizer bands and at least one positive gain')
    tuned_block = block[0][:opt.start()] + tuned_opt + block[0][opt.end():]
    output = stock[:block.start()] + tuned_block + stock[block.end():]
    # Full semantic comparison with the exact authorized transform. This also
    # catches accidental edits to other endpoints or protection parameters.
    for b in targets[0].findall('.//band_optimizer'):
        for channel in ('left', 'right'):
            key = 'gain_' + channel
            b.set(key, donor_bands[int(b.get('frequency'))].get(key) if donor_bands is not None else str(min(0, int(b.get(key)))))
    if ET.tostring(root) != ET.tostring(ET.fromstring(output)):
        raise ValueError('unexpected semantic change outside authorized gains')
    return output, dict(candidate='renoir-taoyao-original-v1' if donor is not None else 'renoir-static-v1', measured=False,
                        source_sha256=digest, donor_sha256=DONOR_SHA256 if donor is not None else None, output_sha256=hashlib.sha256(output).hexdigest(),
                        changes=changes, policy='taoyao original landscape gains when donor supplied; otherwise static-v1; '
                        'all other bytes preserved; raw units, not dB')


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--stock', required=True, type=Path)
    ap.add_argument('--donor', type=Path, help='pinned taoyao reference; omit for static-v1 rollback')
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--report', type=Path)
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()
    outputs = [args.out] + ([args.report] if args.report else [])
    if len({p.resolve() for p in ([args.stock, args.donor] if args.donor else [args.stock]) + outputs}) != (2 if args.donor else 1) + len(outputs):
        ap.error('input, output and report must be different files')
    try:
        output, report = derive(args.stock.read_bytes(), args.donor.read_bytes() if args.donor else None)
        if args.check:
            if args.out.read_bytes() != output:
                raise ValueError('generated DAX is stale or differs from selected candidate')
        else:
            atomic_write(args.out, output)
        if args.report:
            atomic_write(args.report, (json.dumps(report, indent=2) + '\n').encode())
    except (ValueError, OSError, ET.ParseError) as e:
        ap.exit(1, f'gen-renoir-dax: {e}\n')
    print(f"{report['candidate']}: {len(report['changes'])} gain values changed; sha256={report['output_sha256']}")


if __name__ == '__main__':
    main()
