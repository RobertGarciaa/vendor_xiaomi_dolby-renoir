#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Generate renoir DAX from pinned Redwood settings.

With --donor, copy original taoyao landscape optimizer gains. Add
--speaker-settings to transfer both speaker tuning blocks and profile speaker
endpoints. Without donor reproduce static-v1. Other bytes remain unchanged.
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


def derive_speaker_settings(stock, donor):
    """Transfer speaker-only tuning and profile endpoints, retaining other bytes."""
    # Validate both pinned inputs and retain the previous candidate contract.
    derive(stock, donor)
    root, reference = ET.fromstring(stock), ET.fromstring(donor)
    changes = []

    def semantic(element):
        return (element.tag, tuple(sorted(element.attrib.items())),
                (element.text or '').strip(), tuple(semantic(c) for c in element))

    def replace_block(source, pattern, new):
        matches = list(re.finditer(pattern, source, re.S))
        donors = list(re.finditer(pattern, donor, re.S))
        if len(matches) != 1 or len(donors) != 1:
            raise ValueError('missing or ambiguous speaker block')
        m = matches[0]
        if semantic(ET.fromstring(m[0])) != semantic(ET.fromstring(donors[0][0])):
            changes.append(new)
        return source[:m.start()] + donors[0][0] + source[m.end():]

    output = stock
    for name in ('speaker_landscape', 'speaker_portrait'):
        a = root.findall("./tuning[@name='" + name + "']")
        b = reference.findall("./tuning[@name='" + name + "']")
        if len(a) != 1 or len(b) != 1 or a[0].attrib != b[0].attrib:
            raise ValueError('speaker routing/format mismatch')
        # Device mapping must remain identical, not just the tuning name.
        if [semantic(c) for c in a[0] if c.tag != 'data'] != [semantic(c) for c in b[0] if c.tag != 'data']:
            raise ValueError('speaker device mapping mismatch')
        pattern = rb'<tuning\b[^>]*\bname="' + name.encode() + rb'"[^>]*>.*?</tuning>'
        output = replace_block(output, pattern, 'tuning/' + name)
        index = list(root).index(a[0])
        root.remove(a[0])
        root.insert(index, ET.fromstring(ET.tostring(b[0])))

    source_profiles = root.findall('profile')
    donor_profiles = reference.findall('profile')
    if len({p.get('id') for p in source_profiles}) != len(source_profiles) or {p.get('id') for p in source_profiles} != {p.get('id') for p in donor_profiles}:
        raise ValueError('profile identity mismatch')
    for profile in source_profiles:
        profile_id = profile.get('id')
        candidates = [p for p in donor_profiles if p.get('id') == profile_id]
        if len(candidates) != 1 or profile.attrib != candidates[0].attrib:
            raise ValueError('profile metadata mismatch')
        original_data, donor_data = profile.find('data'), candidates[0].find('data')
        original_speaker = original_data.findall("endpoint_type[@id='speaker']")
        donor_speaker = donor_data.findall("endpoint_type[@id='speaker']")
        if len(original_speaker) != 1 or len(donor_speaker) != 1:
            raise ValueError('ambiguous profile speaker endpoint')
        pattern = rb'<profile\b[^>]*\bid="' + re.escape(profile_id.encode()) + rb'"[^>]*>.*?</profile>'
        matches = list(re.finditer(pattern, output, re.S))
        donor_matches = list(re.finditer(pattern, donor, re.S))
        if len(matches) != 1 or len(donor_matches) != 1:
            raise ValueError('ambiguous profile block')
        endpoint_pattern = rb'<endpoint_type\b[^>]*\bid="speaker"[^>]*>.*?</endpoint_type>'
        local, donor_local = matches[0][0], donor_matches[0][0]
        old = list(re.finditer(endpoint_pattern, local, re.S))
        new = list(re.finditer(endpoint_pattern, donor_local, re.S))
        if len(old) != 1 or len(new) != 1:
            raise ValueError('ambiguous endpoint block')
        if semantic(original_speaker[0]) != semantic(donor_speaker[0]):
            changes.append('profile/' + profile_id + '/speaker')
        updated = local[:old[0].start()] + new[0][0] + local[old[0].end():]
        output = output[:matches[0].start()] + updated + output[matches[0].end():]
        index = list(original_data).index(original_speaker[0])
        original_data.remove(original_speaker[0])
        original_data.insert(index, ET.fromstring(ET.tostring(donor_speaker[0])))

    if semantic(root) != semantic(ET.fromstring(output)):
        raise ValueError('unexpected change outside authorized speaker settings')
    return output, dict(candidate='renoir-taoyao-speaker-v2', measured=False,
                        source_sha256=STOCK_SHA256, donor_sha256=DONOR_SHA256,
                        output_sha256=hashlib.sha256(output).hexdigest(), changes=changes,
                        policy='original taoyao landscape/portrait speaker tuning and profile speaker endpoints; '
                        'preserve profile globals, presets, other endpoints, engine and renoir hardware calibration')


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
    ap.add_argument('--speaker-settings', action='store_true', help='extend donor transfer to both speaker tunings and profile speaker endpoints')
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--report', type=Path)
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()
    if args.speaker_settings and args.donor is None:
        ap.error('--speaker-settings requires --donor')
    outputs = [args.out] + ([args.report] if args.report else [])
    if len({p.resolve() for p in ([args.stock, args.donor] if args.donor else [args.stock]) + outputs}) != (2 if args.donor else 1) + len(outputs):
        ap.error('input, output and report must be different files')
    try:
        if args.speaker_settings:
            output, report = derive_speaker_settings(args.stock.read_bytes(), args.donor.read_bytes())
        else:
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
    print(f"{report['candidate']}: {len(report['changes'])} changed entries; sha256={report['output_sha256']}")


if __name__ == '__main__':
    main()
