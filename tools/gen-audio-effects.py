#!/usr/bin/env python3
#
# Copyright (C) 2026 The LineageOS Project
# SPDX-License-Identifier: Apache-2.0
#
"""Generate the Dolby-extended audio_effects.xml from a pinned stock file.

The stock Qualcomm audio_effects.xml is left byte-for-byte intact except for
one inserted <library> and one inserted <effect>. Voice call AEC/NS, the
offload bundle and every existing proxy stay exactly as the product ships them.

The implementation UUID written here MUST match the descriptor compiled into
the libswdap.so that is actually installed. Redwood's libswdap.so exports
6ab06da4-c516-4611-8166-452799218539 (SW DAP). Redwood's libhwdap.so and Sony's
libswdap.so export 9d4921da-8225-4f29-aefa-39537a04bcaa instead; using that
UUID with the Redwood SW blob makes AudioFlinger fail the lookup.
"""

import argparse
import hashlib
import re
import sys
import xml.etree.ElementTree as ET

# Descriptor read out of Redwood vendor/lib64/soundfx/libswdap.so: the
# implementation UUID registered below is the key the effects factory uses to
# query the library's descriptor, so it must match the blob exactly.
#
# The descriptor type (46d279d9-9be7-453d-9d7c-ef937f675587) is not written
# into this file. AudioFlinger resolves by implementation UUID when one is
# given, and the type in audio_effects.xml is informational; the type that
# matters is the one the library returns, and MiSound is patched to request
# that same type. Recording it here only as a comment keeps the XML to the two
# lines that have an effect.
DAP_IMPL_UUID = "6ab06da4-c516-4611-8166-452799218539"
DAP_LIBRARY = "dap"
DAP_EFFECT = "dap"

# Symbols that must exist exactly once in the stock file for the insertion
# anchors to be trustworthy.
ANCHOR_LIBRARIES_OPEN = r"(?P<indent>[ \t]*)</libraries>"
ANCHOR_EFFECTS_CLOSE = r"(?P<indent>[ \t]*)</effects>"


def die(msg):
    sys.stderr.write("gen-audio-effects: error: %s\n" % msg)
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stock", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--check", action="store_true",
                    help="fail if --out differs from the generated content")
    args = ap.parse_args()

    with open(args.stock, "r", encoding="utf-8") as f:
        src = f.read()

    try:
        tree = ET.fromstring(src)
    except ET.ParseError as error:
        die("invalid input XML: " + str(error))
    for tag in ("libraries", "effects"):
        if sum(e.tag.rsplit("}", 1)[-1] == tag for e in tree.iter()) != 1:
            die("expected exactly one " + tag + " section")

    # Refuse to operate on a file whose Dolby entries already exist: that means
    # the input is not the pinned stock file.
    if DAP_IMPL_UUID in src or 'name="%s"' % DAP_LIBRARY in src:
        die("%s already contains a dap entry; refusing to double-register"
            % args.stock)

    lib_open = re.search(ANCHOR_LIBRARIES_OPEN, src)
    eff_close = re.search(ANCHOR_EFFECTS_CLOSE, src)
    if not lib_open or not eff_close:
        die("could not locate </libraries> or </effects> anchors")

    indent = lib_open.group("indent") + "    "
    library_line = '%s<library name="%s" path="libswdap.so"/>\n' % (
        indent, DAP_LIBRARY)
    effect_line = ('%s<effect name="%s" library="%s" uuid="%s"/>\n'
                   % (eff_close.group("indent"), DAP_EFFECT, DAP_LIBRARY,
                      DAP_IMPL_UUID))

    out = (src[:lib_open.start()]
           + library_line
           + src[lib_open.start():eff_close.start()]
           + effect_line
           + src[eff_close.start():])

    # Exactly one implementation of the effect, and the UUID agrees with the
    # descriptor we expect the loader to see.
    if out.count('uuid="%s"' % DAP_IMPL_UUID) != 1:
        die("expected exactly one dap effect entry after generation")
    if out.count('<effect name="%s"' % DAP_EFFECT) != 1:
        die("expected exactly one effect element named %s" % DAP_EFFECT)
    if out.count('<library name="%s"' % DAP_LIBRARY) != 1:
        die("expected exactly one library element named %s" % DAP_LIBRARY)
    # Sanity: every pre-existing effect/library name survived.
    for name in re.findall(r'<(?:effect|effectProxy|library) name="([^"]+)"', src):
        if out.count('name="%s"' % name) != src.count('name="%s"' % name):
            die("existing entry %r was altered" % name)

    data = out.encode("utf-8")
    if args.check:
        try:
            with open(args.out, "rb") as f:
                cur = f.read()
        except FileNotFoundError:
            die("%s does not exist" % args.out)
        if cur != data:
            die("%s is stale; regenerate it" % args.out)
        print("gen-audio-effects: %s is up to date (sha256 %s)"
              % (args.out, hashlib.sha256(data).hexdigest()))
        return

    with open(args.out, "wb") as f:
        f.write(data)
    print("gen-audio-effects: wrote %s (sha256 %s)"
          % (args.out, hashlib.sha256(data).hexdigest()))


if __name__ == "__main__":
    main()
