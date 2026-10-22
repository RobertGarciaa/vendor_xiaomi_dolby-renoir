#!/usr/bin/env python3
"""Compile Dolby rules with a cached product's combined neverallow policy.

This is an offline smoke/neverallow check, NOT a replacement for rebuilding the
product's partitioned policy, public mappings, compatibility tests or image.
It reads the existing AOSP out tree and writes only to a temporary directory.

Two modes, chosen automatically:

  * The cached baseline already contains the Dolby policy. This happens once the
    product has been built with Dolby enabled, because the policy is part of the
    tree by then. The baseline is compiled as-is.
  * The baseline does not contain it (fresh out tree, or Dolby not yet built).
    The rules are expanded with m4 and merged into a copy of the baseline.

Merging unconditionally would declare the hal_dolby_dms attributes twice and
checkpolicy rejects the duplicate, so the mode is detected rather than assumed.
"""
from pathlib import Path
import argparse
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MARKER = 'hal_dolby_dms'

parser = argparse.ArgumentParser()
parser.add_argument('--android-root', required=True, type=Path)
args = parser.parse_args()

src = args.android_root / 'system/sepolicy'
baseline = (args.android_root / 'out/soong/.intermediates/system/sepolicy/'
            'sepolicy_neverallows.checkpolicy.conf/android_common/'
            'sepolicy_neverallows.checkpolicy.conf')
compiler = args.android_root / 'out/host/linux-x86/bin/checkpolicy'

if not baseline.is_file():
    sys.exit('baseline policy not found: %s\n'
             'Build the product once, or point --android-root at a tree that '
             'has been built.' % baseline)
if not compiler.is_file():
    sys.exit('checkpolicy not found: %s' % compiler)

s = baseline.read_text()

if MARKER in s:
    mode = 'baseline already contains the Dolby policy; compiling as-is'
else:
    mode = 'baseline does not contain it; merging expanded rules'
    files = [src / 'public/global_macros', src / 'public/te_macros',
             ROOT / 'sepolicy/public/attributes']
    files += sorted((ROOT / 'sepolicy/private').glob('*.te'))
    files += sorted((ROOT / 'sepolicy/vendor').glob('*.te'))
    r = subprocess.run(
        ['m4', '-Dtarget_full_treble=true', '-Dtarget_build_variant=userdebug']
        + [str(f) for f in files],
        capture_output=True, text=True, check=True)

    pos = re.search(r'^attribute\s', s, re.M)
    if not pos:
        sys.exit('No attribute insertion point in baseline')
    attrs = '\n'.join(line for line in r.stdout.splitlines()
                      if line.startswith('attribute ')) + '\n'
    rules = '\n'.join(line for line in r.stdout.splitlines()
                      if not line.startswith('attribute ')) + '\n'
    s = s[:pos.start()] + attrs + s[pos.start():]

    pos = re.search(r'^role\s', s, re.M)
    if not pos:
        sys.exit('No role section in baseline')
    s = s[:pos.start()] + rules + s[pos.start():]

print(mode)

with tempfile.TemporaryDirectory(prefix='dolby-policy-') as d:
    conf = Path(d) / 'policy.conf'
    conf.write_text(s)
    proc = subprocess.run(
        [str(compiler), '-M', '-c', '30', '-o', str(Path(d) / 'policy'),
         str(conf)],
        capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit('checkpolicy failed:\n%s' % (proc.stderr or proc.stdout))
    print('PASS: Dolby + cached combined policy compiled with neverallows '
          'enabled')
    print('Partitioned policy / public mappings / live enforcing remain '
          'unverified')
