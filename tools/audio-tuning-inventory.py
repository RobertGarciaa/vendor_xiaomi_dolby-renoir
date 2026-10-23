#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Inventory stock tuning blobs without interpreting undocumented DSP coefficients."""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def inventory(path):
    b = Path(path).read_bytes()
    result = dict(name=Path(path).name, size=len(b), sha256=hashlib.sha256(b).hexdigest())
    if b.startswith(b'QCMSNDDB'):
        if len(b) < 32 or b[16:20] != b'AVDB':
            raise ValueError('unsupported QCMSNDDB variant')
        unpacked, stored = struct.unpack_from('<II', b, 24)
        if stored != len(b) - 32 or unpacked != stored:
            raise ValueError('unsupported compressed/invalid QCMSNDDB file')
        chunks = []
        pos = 32
        while pos < len(b):
            if pos + 12 > len(b):
                raise ValueError('truncated chunk header')
            tag = b[pos:pos + 8].decode('ascii')
            size = struct.unpack_from('<I', b, pos + 8)[0]
            if pos + 12 + size > len(b):
                raise ValueError(f'truncated chunk {tag}')
            payload = b[pos + 12:pos + 12 + size]
            chunks.append(dict(tag=tag, offset=pos, size=size,
                               sha256=hashlib.sha256(payload).hexdigest()))
            pos += 12 + size
        result.update(format='QCMSNDDB AVDB', chunks=chunks, consumed=pos,
                      interpretation='Chunk framing only; module IDs, LUTs and coefficient units undecoded.')
    elif b.startswith(b'SPKD'):
        tags = {}
        # Candidate tags only: do not treat values after COEF as byte lengths.
        for tag in (b'SPKD', b'SPMD', b'MMFD', b'MAXS', b'MODL', b'SMPR', b'NSOS', b'COEF'):
            hits = []
            pos = 0
            while True:
                pos = b.find(tag, pos)
                if pos < 0:
                    break
                if pos + 8 <= len(b):
                    hits.append(dict(offset=pos, following_u32=struct.unpack_from('<I', b, pos + 4)[0]))
                pos += 4
            tags[tag.decode()] = hits
        result.update(format='SPKD tag candidates', tags=tags,
                      interpretation='Byte-pattern inventory, not a verified file grammar or filter response.')
    else:
        raise ValueError('unsupported tuning signature')
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('blobs', nargs='+')
    ap.add_argument('--json', required=True)
    args = ap.parse_args()
    result = [inventory(p) for p in args.blobs]
    Path(args.json).write_text(json.dumps(result, indent=2) + '\n')
    for r in result:
        print(r['name'], r['size'], r['format'], r['sha256'])


if __name__ == '__main__':
    main()
