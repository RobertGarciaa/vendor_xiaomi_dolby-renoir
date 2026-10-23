#!/usr/bin/env python3
"""Reject stale MiSound prebuilts before Soong signs/installs them.

This validates ZIP/DEX integrity and required fixup markers; import-misound.sh
remains responsible for the pinned source, smali scope and sorted DEX strings.
"""
import argparse
import hashlib
from pathlib import Path
import shutil
import struct
import tempfile
import zipfile
import zlib

GUARD_MARKER=b'renoir: effect selection unavailable; skip dependent UI refresh'
REQUIRED_UUIDS=(b'6ab06da4-c516-4611-8166-452799218539',b'46d279d9-9be7-453d-9d7c-ef937f675587')
OLD_UUIDS=(b'9d4921da-8225-4f29-aefa-39537a04bcaa',b'ec7178ec-e5e1-4432-a3f4-4657e6795210')


def verify_dex(data):
    if len(data)<112 or not data.startswith(b'dex\n') or struct.unpack_from('<I',data,32)[0]!=len(data):
        raise ValueError('Invalid/truncated DEX')
    if hashlib.sha1(data[32:]).digest()!=data[12:32]:
        raise ValueError('DEX signature mismatch')
    if zlib.adler32(data[12:])&0xffffffff!=struct.unpack_from('<I',data,8)[0]:
        raise ValueError('DEX checksum mismatch')


def verify_apk(path):
    with zipfile.ZipFile(path) as archive:
        names=archive.namelist()
        if len(names)!=len(set(names)):
            raise ValueError('Duplicate APK entries')
        if {name for name in names if name.endswith('.dex')}!={'classes.dex','classes2.dex'}:
            raise ValueError('Expected main and compatibility DEX')
        main=archive.read('classes.dex');compat=archive.read('classes2.dex')
        verify_dex(main);verify_dex(compat)
        for value in REQUIRED_UUIDS:
            if main.count(value)!=1:raise ValueError('Missing/duplicate software effect UUID')
        if any(value in main for value in OLD_UUIDS):raise ValueError('Hardware effect UUID remains')
        if main.count(GUARD_MARKER)!=1:
            raise ValueError('Stale MiSound APK: rerun tools/import-misound.sh for the selection null guard')
        if b'Lmiui/util/FeatureParser;' not in compat:
            raise ValueError('MIUI FeatureParser compatibility class missing')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    verify_apk(args.input)
    if args.output:
        if args.input.resolve()==args.output.resolve():raise ValueError('Do not overwrite input APK')
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=args.output.parent,delete=False) as temporary:
            staged=Path(temporary.name)
        try:
            shutil.copyfile(args.input,staged);staged.replace(args.output)
        finally:
            staged.unlink(missing_ok=True)
    print('MiSound fixup contract verified; Android runtime/SELinux still require validation')


if __name__=='__main__':main()
