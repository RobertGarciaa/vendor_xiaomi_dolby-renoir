#!/usr/bin/env python3
"""Resolve strong dynamic imports using only matching ELF class and machine.

Requires readelf. --blob-root overlays unmodified source blobs on a built
--product-out for pre-build checks. No loading, building or device changes.
This checks symbols/versions, not runtime linker namespace reachability or C++
object layout. The resolved provider paths are recorded for manual review.
"""
import argparse
from functools import lru_cache
import json
from pathlib import Path
import re
import struct
import subprocess
import sys


def run(*args):
    return subprocess.check_output(['readelf', *args], text=True, env=None)


@lru_cache(None)
def elf_info(path):
    with Path(path).open('rb') as stream:
        h = stream.read(20)
    if len(h) < 20 or h[:4] != b'\x7fELF' or h[4] not in (1, 2) or h[5] not in (1, 2):
        raise ValueError(f'not a supported ELF: {path}')
    return (32 if h[4] == 1 else 64, struct.unpack('<H' if h[5] == 1 else '>H', h[18:20])[0])


@lru_cache(None)
def symbols(path):
    defined, required = set(), set()
    for line in run('--dyn-syms', '-W', str(path)).splitlines():
        # GNU readelf prints ARM IFUNC as multiword '<OS specific>: 10'.
        # Parse the binding/visibility/index/name tail; a trailing '(2)' is
        # a version index, not the symbol name.
        match = re.match(r'^\s*\d+:\s+[0-9a-fA-F]+\s+\d+\s+.*?\s+'
                         r'(LOCAL|GLOBAL|WEAK|UNIQUE)\s+(\w+)\s+(\w+)\s+(\S+)', line)
        if not match:
            continue
        binding, visibility, index, spelling = match.groups()
        name, _, version = spelling.partition('@')
        key = (name, version.lstrip('@'))
        if index == 'UND':
            if binding != 'WEAK':
                required.add(key)
        elif binding in ('GLOBAL', 'WEAK', 'UNIQUE') and visibility in ('DEFAULT', 'PROTECTED'):
            defined.add(key)
    return defined, required


@lru_cache(None)
def needed(path):
    return re.findall(r'\(NEEDED\).*?\[(.*?)\]', run('-dW', str(path)))


def resolve_link(path, root):
    for _ in range(16):
        if not path.is_symlink():
            return path if path.is_file() else None
        target = path.readlink()
        path = root / str(target).lstrip('/') if target.is_absolute() else path.parent / target
    raise ValueError(f'symlink loop: {path}')


def library(name, abi, product, overlay):
    lib = 'lib' if abi[0] == 32 else 'lib64'
    for root in ([overlay] if overlay else []) + [product]:
        for directory in (f'vendor/{lib}', f'odm/{lib}', f'system/{lib}',
                          f'system_ext/{lib}', f'apex/com.android.runtime/{lib}/bionic'):
            p = resolve_link(root / directory / name, root)
            if p and elf_info(str(p)) == abi:
                return p
    raise ValueError(f'missing same-ABI dependency: {name}, ELF{abi[0]} machine={abi[1]}')


def check(blob, product, overlay):
    abi = elf_info(str(blob))
    todo = list(needed(str(blob)))
    visited, providers = {}, set()
    while todo:
        name = todo.pop(0)
        if name in visited:
            continue
        p = library(name, abi, product, overlay)
        visited[name] = str(p)
        providers.update(symbols(str(p))[0])
        todo.extend(needed(str(p)))
    _, required = symbols(str(blob))
    unresolved = sorted(name + ('@' + version if version else '')
                        for name, version in required
                        if not any(n == name and (not version or v == version or not v)
                                   for n, v in providers))
    return {'blob': str(blob), 'elf_bits': abi[0], 'machine': abi[1],
            'strong_imports': len(required), 'unresolved': unresolved,
            'providers': visited}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--product-out', type=Path, required=True)
    parser.add_argument('--blob-root', type=Path)
    parser.add_argument('--json', type=Path)
    parser.add_argument('blobs', type=Path, nargs='+')
    a = parser.parse_args()
    reports = []
    for blob in a.blobs:
        try:
            result = check(blob, a.product_out, a.blob_root)
        except (ValueError, OSError, subprocess.CalledProcessError) as failure:
            result = {'blob': str(blob), 'error': str(failure)}
        reports.append(result)
        print(json.dumps(result, ensure_ascii=False))
    if a.json:
        a.json.write_text(json.dumps(reports, ensure_ascii=False, indent=2) + '\n')
    return int(any(r.get('error') or r.get('unresolved') for r in reports))


if __name__ == '__main__':
    sys.exit(main())
