#!/usr/bin/env python3
"""Compile Dolby rules with a cached product's combined neverallow policy.

This is an offline smoke/neverallow check, NOT a replacement for rebuilding the
product's partitioned policy, public mappings, compatibility tests or image.
It reads the existing AOSP out tree and writes only to a temporary directory.
"""
from pathlib import Path
import argparse,re,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--android-root',required=True,type=Path);a=p.parse_args()
src=a.android_root/'system/sepolicy'
baseline=a.android_root/'out/soong/.intermediates/system/sepolicy/sepolicy_neverallows.checkpolicy.conf/android_common/sepolicy_neverallows.checkpolicy.conf'
compiler=a.android_root/'out/host/linux-x86/bin/checkpolicy'
files=[src/'public/global_macros',src/'public/te_macros',ROOT/'sepolicy/public/attributes']
files+=sorted((ROOT/'sepolicy/private').glob('*.te'))+sorted((ROOT/'sepolicy/vendor').glob('*.te'))
r=subprocess.run(['m4','-Dtarget_full_treble=true','-Dtarget_build_variant=userdebug']+[str(f) for f in files],capture_output=True,text=True,check=True)
s=baseline.read_text();pos=re.search(r'^attribute\s',s,re.M)
if not pos:raise SystemExit('No attribute insertion point in baseline')
attrs='\n'.join(line for line in r.stdout.splitlines() if line.startswith('attribute '))+'\n'
rules='\n'.join(line for line in r.stdout.splitlines() if not line.startswith('attribute '))+'\n'
s=s[:pos.start()]+attrs+s[pos.start():]
pos=re.search(r'^role\s',s,re.M)
if not pos:raise SystemExit('No role section in baseline')
s=s[:pos.start()]+rules+s[pos.start():]
with tempfile.TemporaryDirectory(prefix='dolby-policy-') as d:
 f=Path(d)/'policy.conf';f.write_text(s)
 subprocess.run([str(compiler),'-M','-c','30','-o',str(Path(d)/'policy'),str(f)],check=True)
 print('PASS: Dolby + cached combined policy compiled with neverallows enabled')
 print('Partitioned policy / public mappings / live enforcing remain unverified')
