#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Read-only DAX band inventory. Raw gain units are intentionally not called dB."""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def audit(path):
    data = Path(path).read_bytes()
    root = ET.fromstring(data)
    result = {'sha256': hashlib.sha256(data).hexdigest(),
              'format': root.find('format_version').attrib,
              'speaker_tunings': [], 'geq_presets': []}
    for preset in root.findall('preset'):
        if preset.get('type') != 'geq':
            continue
        bands = [dict(frequency=int(b.get('frequency')), gain=int(b.get('gain')))
                 for b in preset.findall('.//band_geq')]
        result['geq_presets'].append({'id': preset.get('id'), 'bands': bands})
    for tuning in root.findall('tuning'):
        if tuning.get('endpoint_type') != 'speaker':
            continue
        bands = [dict(frequency=int(b.get('frequency')), left=int(b.get('gain_left')),
                      right=int(b.get('gain_right')))
                 for b in tuning.findall('.//band_optimizer')]
        flags = {b.tag: b.get('value') for b in tuning.iter()
                 if 'enable' in b.tag and 'value' in b.attrib}
        result['speaker_tunings'].append(dict(
            attributes=tuning.attrib, bands=bands, flags=flags,
            asymmetric_bands=sum(b['left'] != b['right'] for b in bands),
            nonzero_bands=sum(bool(b['left'] or b['right']) for b in bands)))
    for tuning in result['speaker_tunings']:
        freqs = [b['frequency'] for b in tuning['bands']]
        if not freqs or len(set(freqs)) != len(freqs) or freqs != sorted(freqs):
            raise ValueError('missing/duplicate/unordered optimizer bands')
    result['mirrored_pairs'] = []
    tunings = result['speaker_tunings']
    for i, a in enumerate(tunings):
        for b in tunings[i + 1:]:
            if a['asymmetric_bands'] and a['bands'] == [dict(frequency=x['frequency'],
                    left=x['right'], right=x['left']) for x in b['bands']]:
                result['mirrored_pairs'].append([a['attributes']['name'], b['attributes']['name']])
    result['limitations'] = [
        'XML values are static configuration, not active device readback.',
        'Shared frequency grid does not prove shared processing state or gain units.',
        'DAX L/R to physical speaker mapping requires the active HAL route and orientation.']
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('xml')
    ap.add_argument('--json', required=True)
    args = ap.parse_args()
    result = audit(args.xml)
    Path(args.json).write_text(json.dumps(result, indent=2) + '\n')
    for t in result['speaker_tunings']:
        print(t['attributes']['name'], 'bands=', len(t['bands']),
              'nonzero=', t['nonzero_bands'], 'asymmetric=', t['asymmetric_bands'])
    print('Mirrored pairs:', result['mirrored_pairs'])


if __name__ == '__main__':
    main()
