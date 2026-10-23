#!/usr/bin/env python3
"""Compile Dolby rules with a cached product's combined neverallow policy.

This is an offline smoke/neverallow check, NOT a replacement for rebuilding the
product's partitioned policy, public mappings, compatibility tests or image.
It reads the existing AOSP out tree and writes only to a temporary directory.

A cached baseline that already contains Dolby is rejected: compiling that old
copy cannot validate changed source rules. A baseline without Dolby can be used
for a limited expanded-rule smoke test. The real partitioned policy still must
be rebuilt by the user; this script never certifies the current image.
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
    sys.exit('Cached policy already contains Dolby rules. Compiling it as-is would not validate current source changes. Rebuild the product policy; no source-validation PASS is emitted.')
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
