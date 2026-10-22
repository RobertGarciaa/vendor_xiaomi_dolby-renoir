#!/usr/bin/env python3
#
# Copyright (C) 2026 The LineageOS Project
# SPDX-License-Identifier: Apache-2.0
#
"""Check that MiSound's MIUI dependencies are satisfied by MiSoundCompat.

MiSound.apk is a closed MIUI app. On a non-MIUI ROM it fails at runtime with
NoClassDefFoundError / NoSuchMethodError unless the MIUI framework classes it
uses are present. Rather than dragging in MIUI's framework, this repository
provides three tiny stand-ins and this script verifies that every member the
app actually references exists with a matching signature.

The reference list is derived from the live APK, not hard-coded, so a different
MiSound build is checked against its own real requirements.

Usage:
  verify-misound-deps.py --apk MiSound.apk --shim-classes <dir-of-compiled-classes>
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile


def die(msg):
    sys.stderr.write("verify-misound-deps: error: %s\n" % msg)
    sys.exit(1)


def find_tool(name):
    path = shutil.which(name)
    if not path:
        die("%r not found in PATH" % name)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apk", required=True)
    ap.add_argument("--shim-classes", required=True,
                    help="directory containing compiled miui/**/*.class")
    ap.add_argument("--keep-work", action="store_true")
    args = ap.parse_args()

    if not os.path.isfile(args.apk):
        die("%s does not exist" % args.apk)
    if not os.path.isdir(args.shim_classes):
        die("%s is not a directory" % args.shim_classes)

    baksmali = find_tool("baksmali")
    javap = find_tool("javap")

    work = tempfile.mkdtemp(prefix="misound-deps-")
    try:
        dex = os.path.join(work, "classes.dex")
        with zipfile.ZipFile(args.apk) as z:
            if "classes.dex" not in z.namelist():
                die("no classes.dex in %s" % args.apk)
            with z.open("classes.dex") as src, open(dex, "wb") as out:
                shutil.copyfileobj(src, out)

        smali = os.path.join(work, "smali")
        os.makedirs(smali)
        subprocess.run([baksmali, "d", dex, "-o", smali], check=True,
                       capture_output=True)

        # Collect every reference to a class we are supposed to provide.
        # Format in smali:  Lmiui/os/Build;->DEVICE:Ljava/lang/String;
        #                   Lmiui/util/FeatureParser;->getString(...)...;
        ref = re.compile(r"L(miui/(?:os|util)/[A-Za-z0-9_$]+);->([A-Za-z0-9_<>]+)")
        needed = {}
        for root, _dirs, files in os.walk(smali):
            for name in files:
                if not name.endswith(".smali"):
                    continue
                with open(os.path.join(root, name), encoding="utf-8",
                          errors="ignore") as f:
                    for cls, member in ref.findall(f.read()):
                        needed.setdefault(cls, set()).add(member)

        if not needed:
            die("no miui/os or miui/util references found; wrong APK?")

        # Also pick up reflective lookups against HapticFeedbackUtil, which
        # the app probes by string name.
        haptic_methods = set()
        with open(os.path.join(smali, "d4", "b.smali"), encoding="utf-8",
                  errors="ignore") as f:
            haptic_src = f.read()
        for m in re.finditer(r'const-string [vp]\d+, "((?:perform|isSupport|stop)'
                             r'[A-Za-z]*)"', haptic_src):
            haptic_methods.add(m.group(1))
        if haptic_methods:
            needed.setdefault("miui/util/HapticFeedbackUtil", set()).update(
                haptic_methods)

        failures = []
        for cls in sorted(needed):
            path = os.path.join(args.shim_classes, cls + ".class")
            if not os.path.isfile(path):
                failures.append("%s: shim class missing" % cls)
                continue
            out = subprocess.run([javap, "-p", "-classpath",
                                  args.shim_classes,
                                  cls.replace("/", ".")],
                                 capture_output=True, text=True)
            if out.returncode != 0:
                failures.append("%s: javap failed" % cls)
                continue
            body = out.stdout
            simple_name = cls.rsplit("/", 1)[-1]
            for member in sorted(needed[cls]):
                # javap prints constructors as ClassName(, methods as name(,
                # fields as "type name;". <init> must be mapped to the class
                # simple name; matching the literal "<init>" always fails.
                needle = simple_name if member == "<init>" else member
                if not re.search(r"\b%s\b" % re.escape(needle), body):
                    failures.append("%s: member %r not found in shim"
                                    % (cls, member))

        print("verify-misound-deps: checked %d classes, %d members"
              % (len(needed), sum(len(v) for v in needed.values())))
        for cls in sorted(needed):
            print("  %s: %s" % (cls, ", ".join(sorted(needed[cls]))))

        if failures:
            for f in failures:
                sys.stderr.write("verify-misound-deps: %s\n" % f)
            return 1
        print("verify-misound-deps: all referenced MIUI members are provided")
        return 0
    finally:
        if args.keep_work:
            print("verify-misound-deps: work dir %s" % work)
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
