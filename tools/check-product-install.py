#!/usr/bin/env python3
"""Read-only pre-flash checks for installed Dolby permissions and effect-host ELF ABI.

Checks completed product out files, not source files. Does not build, flash,
modify images or prove runtime compatibility. A successful run still requires
full ELF dependency, boot, effect creation and live SELinux/audio validation.
"""
import argparse
import hashlib
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from misound_apk_contract import verify_apk
from dms_foundation_compat import OUTPUT_SHA


def elf_class(path):
    try:
        with path.open('rb') as stream:
            header = stream.read(5)
    except OSError:
        return None
    return {1: 32, 2: 64}.get(header[4]) if header[:4] == b'\x7fELF' else None


def check(out):
    errors = []
    # Refuse a product assembled before the DMS ABI boundary was fixed.
    for mode, name in [('consumer', 'libdlbdsservice.so'),
                       ('provider', 'libsf_dolby_renoir.so')]:
        path = out / 'vendor/lib64' / name
        try:
            if hashlib.sha256(path.read_bytes()).hexdigest() != OUTPUT_SHA[mode]:
                errors.append('DMS compatibility ' + mode + ' missing/stale: ' + str(path))
        except OSError as failure:
            errors.append('DMS compatibility ' + mode + ': ' + str(failure))
    try:
        verify_apk(out/'product/app/MiSound/MiSound.apk')
    except Exception as failure:
        errors.append('MiSound fixup contract: '+str(failure))
    contexts=out/'vendor/etc/selinux/vendor_property_contexts'
    expected='ro.vendor.audio.dolby.dax.support u:object_r:vendor_dolby_config_prop:s0 exact bool'
    try:
        normalized=[' '.join(line.split()) for line in contexts.read_text().splitlines()]
        if expected not in normalized:errors.append('Dolby capability exact property context missing/stale')
    except OSError as failure:
        errors.append('Vendor property contexts unavailable: '+str(failure))
    app = out / 'system/priv-app/DolbyControl/DolbyControl.apk'
    xml = out / 'system/etc/permissions/privapp-permissions-dolby-renoir.xml'
    if not app.is_file():
        errors.append('DolbyControl APK missing from expected system/priv-app location')
    try:
        doc = ET.parse(xml).getroot()
        names = {n.get('name') for p in doc.findall('privapp-permissions')
                 if p.get('package') == 'org.lineageos.dolby'
                 for n in p.findall('permission')}
        if 'android.permission.MODIFY_AUDIO_ROUTING' not in names:
            errors.append('DolbyControl MODIFY_AUDIO_ROUTING allowlist entry missing')
    except (OSError, ET.ParseError) as failure:
        errors.append('System Dolby allowlist missing/invalid: ' + str(failure))
    service = out / 'vendor/bin/hw/android.hardware.audio.service'
    bits = elf_class(service)
    if bits is None:
        errors.append('Cannot identify effect host ABI; inspect actual effects factory service')
    else:
        library = out / ('vendor/lib64' if bits == 64 else 'vendor/lib') / 'soundfx/libswdap.so'
        if elf_class(library) != bits:
            errors.append(f'Effect host is ELF{bits}, but matching {library} missing/invalid')
        else:
            print(f'PASS: ELF{bits} effect host has matching DAP (dependency ABI still needs validation)')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--product-out', type=Path, required=True)
    args = parser.parse_args()
    errors = check(args.product_out)
    for error in errors:
        print('FAIL: ' + error, file=sys.stderr)
    if errors:
        return 1
    print('PASS: install checks; live boot/audio/SELinux validation remains required')
    return 0


if __name__ == '__main__':
    sys.exit(main())
