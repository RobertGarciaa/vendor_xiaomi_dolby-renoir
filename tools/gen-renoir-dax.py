#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Derive the renoir static-v1 candidate from an immutable Redwood DAX source.

Only positive landscape speaker optimizer gains become zero. Existing cuts,
portrait, headphone/user presets, regulators and all other bytes are retained.
This is an unmeasured candidate, not an acoustic calibration.
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


def derive(stock):
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
    changes = []

    def band(match):
        element = ET.fromstring(match[0])
        frequency = int(element.get('frequency'))
        def gain(m):
            value = int(m['value'])
            if value <= 0:
                return m[0]
            changes.append(dict(frequency=frequency, channel=m['channel'].decode(),
                                before=value, after=0))
            return m['prefix'] + b'0"'
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
            b.set(key, str(min(0, int(b.get(key)))))
    if ET.tostring(root) != ET.tostring(ET.fromstring(output)):
        raise ValueError('unexpected semantic change outside authorized gains')
    return output, dict(candidate='renoir-static-v1', measured=False,
                        source_sha256=digest, output_sha256=hashlib.sha256(output).hexdigest(),
                        changes=changes, policy='cap positive landscape optimizer gains at zero; '
                        'preserve all cuts and every other parameter; raw units, not dB')


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
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--report', type=Path)
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()
    outputs = [args.out] + ([args.report] if args.report else [])
    if len({p.resolve() for p in [args.stock] + outputs}) != 1 + len(outputs):
        ap.error('input, output and report must be different files')
    try:
        output, report = derive(args.stock.read_bytes())
        if args.check:
            if args.out.read_bytes() != output:
                raise ValueError('generated DAX is stale or differs from static-v1')
        else:
            atomic_write(args.out, output)
        if args.report:
            atomic_write(args.report, (json.dumps(report, indent=2) + '\n').encode())
    except (ValueError, OSError, ET.ParseError) as e:
        ap.exit(1, f'gen-renoir-dax: {e}\n')
    print(f"renoir-static-v1: {len(report['changes'])} gain values reduced; sha256={report['output_sha256']}")


if __name__ == '__main__':
    main()
