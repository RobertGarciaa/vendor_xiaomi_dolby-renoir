#!/usr/bin/env python3
"""Pin Redwood's VNDK30 foundation and isolate ONLY its DMS consumer.
No machine code changes. Raw extraction hashes remain unchanged. No platform
library is replaced; build-time outputs change one SONAME/DT_NEEDED string.
"""
import argparse
import hashlib
from pathlib import Path
import os
import shutil
import struct
import subprocess
import tempfile
import zipfile

FOUNDATION_SHA = '060ec055a6d4cb5b893d4606953769297c6f6dfcee16490e9410f46b39c4ac29'
DMS_SHA = '3122ae6728d5a3c58a1c6d6496988d75fd361672bab25a6a976bd1cc9c241f3f'
OLD = b'libstagefright_foundation.so'
NEW = b'libsf_dolby_renoir.so'
RELATIVE = 'compat/vndk30/lib64/libstagefright_foundation.so'
OUTPUT_SHA = {
    'provider': 'bf31302c0218790212762e5402d3a2537f581c47d66c59d1dead84ef89110401',
    'consumer': 'a0f271a97d0bcb9e84759253966a4f042ce83b06513a65306d8b84c9050c3b33',
}


def pinned(data, expected):
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise ValueError('Input SHA256 mismatch: expected ' + expected + ', actual ' + actual)


def isolate(data, mode):
    pinned(data, FOUNDATION_SHA if mode == 'provider' else DMS_SHA)
    if data[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', data, 18)[0] != 183:
        raise ValueError('Expected little-endian AArch64 ELF64')
    phoff = struct.unpack_from('<Q', data, 32)[0]
    entsize, count = struct.unpack_from('<HH', data, 54)
    loads, dynamic = [], None
    for i in range(count):
        p = struct.unpack_from('<IIQQQQQQ', data, phoff + i * entsize)
        if p[0] == 1:
            loads.append((p[3], p[2], p[5]))
        elif p[0] == 2:
            dynamic = (p[2], p[5])
    if not dynamic:
        raise ValueError('Missing PT_DYNAMIC')
    entries = []
    for off in range(dynamic[0], sum(dynamic), 16):
        tag, value = struct.unpack_from('<qQ', data, off)
        if tag == 0:
            break
        entries.append((tag, value))
    def tag_value(tag):
        matches = [v for t, v in entries if t == tag]
        if len(matches) != 1:
            raise ValueError('Missing/duplicate dynamic tag ' + str(tag))
        return matches[0]
    address, size = tag_value(5), tag_value(10)
    maps = [o + address - v for v, o, n in loads if v <= address and address + size <= v + n]
    if len(maps) != 1:
        raise ValueError('Invalid dynamic string table')
    base = maps[0]
    wanted = 14 if mode == 'provider' else 1
    targets = []
    for tag, value in entries:
        if tag != wanted:
            continue
        if value >= size:
            raise ValueError('Dynamic string out of bounds')
        start = base + value
        end = data.index(b'\0', start, base + size)
        if data[start:end] == OLD:
            targets.append(start)
    if len(targets) != 1 or len(NEW) > len(OLD):
        raise ValueError('Expected exactly one original foundation reference')
    out = bytearray(data)
    start = targets[0]
    out[start:start + len(OLD)] = NEW + b'\0' * (len(OLD) - len(NEW))
    result = bytes(out)
    pinned(result, OUTPUT_SHA[mode])
    return result


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.dms-compat-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
            os.fchmod(stream.fileno(), 0o644)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def extract(dump, debugfs):
    apex = dump / 'system_ext/apex/com.android.vndk.v30.apex'
    with tempfile.TemporaryDirectory(prefix='dolby-vndk30-') as tmp:
        root = Path(tmp)
        # zipfile checks the payload CRC, even if unrelated OTA partitions failed.
        with zipfile.ZipFile(apex) as archive:
            with archive.open('apex_payload.img') as src, (root / 'payload.img').open('wb') as dst:
                shutil.copyfileobj(src, dst)
        target = root / 'foundation.so'
        subprocess.run([debugfs, '-R', 'dump /lib64/libstagefright_foundation.so ' + str(target),
                        str(root / 'payload.img')], check=True, capture_output=True)
        data = target.read_bytes()
        pinned(data, FOUNDATION_SHA)
        return data


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode', choices=['extract', 'verify', 'provider', 'consumer'], required=True)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--output', type=Path)
    p.add_argument('--debugfs', default=shutil.which('debugfs'))
    a = p.parse_args()
    if a.mode == 'extract':
        if not a.debugfs:
            p.error('debugfs is required for the ext4 APEX payload')
        data = extract(a.input, a.debugfs)
    else:
        data = a.input.read_bytes()
        if a.mode == 'verify':
            pinned(data, FOUNDATION_SHA)
        else:
            data = isolate(data, a.mode)
    if a.mode != 'verify':
        if not a.output or a.output.resolve() == a.input.resolve():
            p.error('a separate --output is required')
        atomic_write(a.output, data)
    print('DMS foundation ' + a.mode + ' verified: ' + hashlib.sha256(data).hexdigest())


if __name__ == '__main__':
    main()
