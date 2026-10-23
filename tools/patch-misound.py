#!/usr/bin/env python3
#
# Copyright (C) 2026 The LineageOS Project
# SPDX-License-Identifier: Apache-2.0
#
"""Reproducible MiSound APK fixup for renoir.

Why this exists
---------------
Redwood's MiSound.apk asks AudioEffect for implementation UUID
9d4921da-8225-4f29-aefa-39537a04bcaa, the descriptor compiled into
libhwdap.so. renoir has no Dolby hardware DSP, so this port ships Redwood's
software engine instead, whose descriptor in libswdap.so is
6ab06da4-c516-4611-8166-452799218539.

AudioFlinger resolves a create() request by matching the UUID that
audio_effects.xml registered (EffectsFactoryState.c:findEffect). A request for
the hardware UUID can therefore never reach the software library, whatever the
library file is called. The app's request has to change.

MiSound also passes its own type UUID ec7178ec-e5e1-4432-a3f4-4657e6795210,
which is not the Redwood DAP type UUID 46d279d9-9be7-453d-9d7c-ef937f675587.
Both are rewritten.

Why the DEX is disassembled and reassembled
-------------------------------------------
Both UUID pairs happen to be 36 ASCII characters, so a raw in-place byte patch
is tempting. It is wrong: DEX string_ids must stay sorted by string content
because ART's DexFile::FindStringId does a binary search. Replacing
"9d4921da..." with "6ab06da4..." moves that string ahead of "8000hz.wav", so
the table becomes unsorted and string lookups can silently miss.

Verified on this exact APK: a byte patch leaves 2 unsorted neighbours, while a
baksmali/smali round trip with the UUIDs edited rebuilds a correctly sorted
pool (41,712 entries, 0 unsorted). This tool therefore patches the smali and
reassembles.

Scope
-----
The UUID edit is confined to the single class that constructs the audio effect
wrapper (c/a in this build). If either UUID appears anywhere else in the
disassembly the tool aborts: those call sites would need individual review, and
a global string replace is not acceptable.

Three pinned y/h UI consumers receive null guards without skipping cleanup.
In Dolby mode GeqView retains its original DAP writer and skips only the
parallel legacy MiSound/Dirac initialization and band writes. No capability
result, missing framework implementation or engine success is invented. The APK is still reassembled with a sorted
DEX string table rather than patched bytewise.

Safety
------
* Input APK SHA-256 is pinned; any other MiSound build aborts.
* Each UUID must occur exactly once in the target class.
* The output APK is re-verified by reading the UUIDs back out of the rebuilt
  DEX and by apksigner.

The APK is a proprietary Xiaomi artifact and is not stored in this repository.
Extract it from the Redwood OTA (see proprietary-files.txt).
"""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

EXPECTED_INPUT_SHA256 = (
    "1b83fbe1ce4f69b7aff557fa5b07c943b84f37c866a2211360e6aad68ea67e89"
)

HW_IMPL_UUID = "9d4921da-8225-4f29-aefa-39537a04bcaa"
SW_IMPL_UUID = "6ab06da4-c516-4611-8166-452799218539"
OLD_TYPE_UUID = "ec7178ec-e5e1-4432-a3f4-4657e6795210"
NEW_TYPE_UUID = "46d279d9-9be7-453d-9d7c-ef937f675587"

# Dex path (without .smali) of the only class allowed to hold these UUIDs:
# the AudioEffect subclass that MiSound uses for Dolby.
EFFECT_CLASS = "c/a"

REPLACEMENTS = (
    (HW_IMPL_UUID, SW_IMPL_UUID, "implementation UUID"),
    (OLD_TYPE_UUID, NEW_TYPE_UUID, "type UUID"),
)


def die(msg):
    sys.stderr.write("patch-misound: error: %s\n" % msg)
    sys.exit(1)


SELECTION_CLASS = "y/h"
SELECTION_GUARD_MARKER = "renoir: effect selection unavailable; skip dependent UI refresh"
CREATE_GUARD_MARKER = "renoir: no effect selection at create; report Dolby inactive"


def guard_create_preferences_selection(body):
    """Stop onCreatePreferences from comparing a null selection.

    H0 removes the unsupported selector but leaves the preference object and its
    null value in place. w0 now returns early, so execution continues into
    onCreatePreferences, which compares the same value with "dolby" to decide
    whether Dolby is active. Returning early here would skip the rest of the
    screen setup, so a missing selection is resolved to false instead: that is
    the accurate answer, not a substituted effect or a claimed success.
    """
    start = '.method public onCreatePreferences(Landroid/os/Bundle;Ljava/lang/String;)V\n'
    if body.count(start) != 1 or ':renoir_create_selection_done' in body:
        raise ValueError('Unexpected or already patched onCreatePreferences')
    begin = body.index(start)
    end = body.index('.end method', begin)
    method = body[begin:end]
    anchor = ('    invoke-direct {p0}, Ly/h;->r0()V\n'
              '\n    iget-object p1, p0, Ly/h;->w:Lmiuix/preference/DropDownPreference;\n'
              '\n    invoke-virtual {p1}, Lmiuix/preference/DropDownPreference;->getValue()Ljava/lang/String;\n'
              '\n    move-result-object p1\n'
              '\n    const-string p2, "dolby"\n'
              '\n    invoke-virtual {p1, p2}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z\n'
              '\n    move-result p1\n')
    if body.count(anchor) != 1:
        raise ValueError('Pinned onCreatePreferences selection consumer not found')
    if '.registers 8' not in method:
        raise ValueError('Unexpected onCreatePreferences register layout')
    guarded = ('    invoke-direct {p0}, Ly/h;->r0()V\n'
               '\n    iget-object p1, p0, Ly/h;->w:Lmiuix/preference/DropDownPreference;\n'
               '\n    invoke-virtual {p1}, Lmiuix/preference/DropDownPreference;->getValue()Ljava/lang/String;\n'
               '\n    move-result-object p1\n'
               '\n    if-nez p1, :renoir_create_selection_known\n'
               '\n    const-string p1, "'+CREATE_GUARD_MARKER+'"\n'
               '\n    const-string v0, "HeadsetSettings"\n'
               '\n    invoke-static {v0, p1}, Landroid/util/Log;->d(Ljava/lang/String;Ljava/lang/String;)I\n'
               '\n    const/4 p1, 0x0\n'
               '\n    goto :renoir_create_selection_done\n'
               '\n    :renoir_create_selection_known\n'
               '\n    const-string p2, "dolby"\n'
               '\n    invoke-virtual {p1, p2}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z\n'
               '\n    move-result p1\n'
               '\n    :renoir_create_selection_done\n')
    method = method.replace(anchor, guarded)
    return body[:begin] + method + body[end:]


def guard_effect_selection(body):
    """Protect only the pinned null selection consumer; do not invent a value.

    H0 can remove the unsupported selector without clearing its Java member.
    w0 must not call String.equals on a still-null DropDownPreference value.
    The caller x0 already treats null as unavailable. This guard changes no
    engine state and does not turn missing capability into success.
    """
    start = '.method private w0()V\n'
    if body.count(start) != 1 or ':renoir_selection_ready' in body:
        raise ValueError('Unexpected or already patched selection method')
    begin = body.index(start)
    end = body.index('.end method', begin)
    method = body[begin:end]
    anchor = ('    invoke-virtual {v0}, Lmiuix/preference/DropDownPreference;->getValue()Ljava/lang/String;\n'
              '\n    move-result-object v0\n')
    if method.count(anchor) != 1 or '.registers 10' not in method:
        raise ValueError('Pinned selection getter/register layout not found')
    if 'invoke-virtual {v0, v1}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z' not in method:
        raise ValueError('Expected nullable selection consumer not found')
    guard = ('\n    if-nez v0, :renoir_selection_ready\n'
             '\n    const-string v0, "HeadsetSettings"\n'
             '\n    const-string v1, "'+SELECTION_GUARD_MARKER+'"\n'
             '\n    invoke-static {v0, v1}, Landroid/util/Log;->w(Ljava/lang/String;Ljava/lang/String;)I\n'
             '\n    return-void\n'
             '\n    :renoir_selection_ready\n')
    method = method.replace(anchor, anchor + guard)
    return body[:begin] + method + body[end:]


DESTROY_GUARD_MARKER = "renoir: no effect selection at destroy; preserve cleanup"
GEQ_GUARD_MARKER = "renoir: Dolby GEQ uses DAP without legacy sound effects"
GEQ_CLASS = "com/miui/misound/view/GeqView"


def replace_method(body, signature, transform):
    start = '.method ' + signature + '\n'
    if body.count(start) != 1:
        raise ValueError('Pinned method not found: ' + signature)
    begin = body.index(start)
    end = body.index('.end method', begin)
    original = body[begin:end]
    return body[:begin] + transform(original) + body[end:]


def replace_once(body, anchor, replacement):
    if body.count(anchor) != 1:
        raise ValueError('Pinned instruction block missing or duplicated')
    return body.replace(anchor, replacement, 1)


def guard_destroy_selection(body):
    """Null means no selected effect; always execute original teardown."""
    def apply(method):
        if '.registers 6' not in method or ':renoir_destroy_selection_done' in method:
            raise ValueError('Unexpected or already patched onDestroy')
        anchor = ('    const-string v2, "dolby"\n\n'
                  '    invoke-virtual {v1, v2}, Ljava/lang/String;->equals(Ljava/lang/Object;)Z\n\n'
                  '    move-result v1\n')
        guard = ('    if-nez v1, :renoir_destroy_selection_known\n\n'
                 '    const-string v1, "HeadsetSettings"\n\n'
                 '    const-string v2, "' + DESTROY_GUARD_MARKER + '"\n\n'
                 '    invoke-static {v1, v2}, Landroid/util/Log;->w(Ljava/lang/String;Ljava/lang/String;)I\n\n'
                 '    const/4 v1, 0x0\n\n'
                 '    goto :renoir_destroy_selection_done\n\n'
                 '    :renoir_destroy_selection_known\n' + anchor + '\n'
                 '    :renoir_destroy_selection_done\n')
        return replace_once(method, anchor, guard)
    return replace_method(body, 'public onDestroy()V', apply)


def guard_dolby_geq(body):
    """Keep the stock DAP writer; bypass legacy effects only in Dolby mode.

    w is initialized by the original DAP capability check. Preserve paint,
    curve/mirror updates and custom preset persistence. All three reads of u
    (legacy init plus two band writers) must be covered; never patch p0/c or
    globally pretend the absent MiSound/Dirac framework effect exists.
    """
    if ':renoir_legacy_init' in body:
        raise ValueError('GEQ already patched')
    if body.count('->u:Lp0/c;') != 3:
        raise ValueError('Unexpected legacy effect field access count')
    def init(method):
        anchor = '    invoke-static {}, Lp0/c;->r()Lp0/c;\n'
        guard = ('    iget-boolean v0, p0, Lcom/miui/misound/view/GeqView;->w:Z\n\n'
                 '    if-eqz v0, :renoir_legacy_init\n\n'
                 '    const-string v0, "GeqView"\n\n'
                 '    const-string v1, "' + GEQ_GUARD_MARKER + '"\n\n'
                 '    invoke-static {v0, v1}, Landroid/util/Log;->i(Ljava/lang/String;Ljava/lang/String;)I\n\n'
                 '    return-void\n\n'
                 '    :renoir_legacy_init\n')
        if '.registers 4' not in method:
            raise ValueError('Unexpected GEQ init registers')
        return replace_once(method, anchor, guard + anchor)
    body = replace_method(body, 'private a()V', init)
    def preset(method):
        anchor = ('    invoke-virtual {p0, p2}, Lcom/miui/misound/view/GeqView;->f([F)V\n')
        # d() has already computed/transmitted the 20 DAP bands. e() is
        # only the parallel legacy writer, but its UI mirror update stays.
        guard = ('\n    iget-boolean v0, p0, Lcom/miui/misound/view/GeqView;->w:Z\n\n'
                 '    if-nez v0, :cond_2b\n')
        if '.registers 5' not in method or method.count(':cond_2b\n') != 2:
            raise ValueError('Unexpected GEQ preset layout')
        return replace_once(method, anchor, anchor + guard)
    body = replace_method(body, 'public e(I[F)V', preset)
    def touch(method):
        anchor = '    iget-object v0, p0, Lcom/miui/misound/view/GeqView;->u:Lp0/c;\n'
        guard = ('    iget-boolean v0, p0, Lcom/miui/misound/view/GeqView;->w:Z\n\n'
                 '    if-nez v0, :renoir_legacy_band_done\n\n')
        method = replace_once(method, anchor, guard + anchor)
        call = '    invoke-virtual {v0, v1, v6, p1}, Lp0/c;->z(Landroid/content/Context;IF)V\n'
        return replace_once(method, call, call + '\n    :renoir_legacy_band_done\n')
    return replace_method(body, 'public onTouchEvent(Landroid/view/MotionEvent;)Z', touch)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_tool(name, extra_dirs=()):
    for d in extra_dirs:
        candidate = os.path.join(d, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    path = shutil.which(name)
    if not path:
        die("required tool %r not found in PATH%s"
            % (name, " or " + ", ".join(extra_dirs) if extra_dirs else ""))
    return path


def find_rom_root(start):
    """Find the AOSP/LineageOS tree root by walking up for prebuilts/.

    The repository sits at <rom>/vendor/xiaomi/dolby-renoir in a real tree, but it is
    also checked out outside a tree during development. Rather than assume a
    fixed depth, walk up until a directory containing prebuilts/ is found.
    """
    override = os.environ.get("DOLBY_ROM_ROOT")
    if override:
        if not os.path.isdir(os.path.join(override, "prebuilts")):
            die("invalid ROM root: " + override)
        return os.path.abspath(override)
    path = start
    for _ in range(8):
        if os.path.isdir(os.path.join(path, 'prebuilts')):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return None


def find_javac():
    """Locate javac, including the copy shipped in an AOSP prebuilts tree."""
    path = shutil.which('javac')
    if path:
        return path
    rom = find_rom_root(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if rom:
        prebuilts = os.path.join(rom, 'prebuilts', 'jdk')
        if os.path.isdir(prebuilts):
            # Prefer the newest JDK that has a javac.
            for entry in sorted(os.listdir(prebuilts), reverse=True):
                for suffix in [('bin', 'javac'), ('linux-x86', 'bin', 'javac')]:
                    candidate = os.path.join(prebuilts, entry, *suffix)
                    if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                        return candidate
    die("javac not found on PATH and not under an AOSP prebuilts/jdk")


def find_jar_tool(name):
    """Locate baksmali/smali as a launcher or as a jar in an AOSP tree.

    AOSP ships these as jars under prebuilts/extract-tools/common/smali, not as
    binaries on PATH, so a build machine has no `baksmali` command. Returns the
    argv prefix to run the tool.
    """
    path = shutil.which(name)
    if path:
        return [path]

    rom = find_rom_root(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    jar = (os.path.join(rom, 'prebuilts', 'extract-tools', 'common', 'smali',
                        name + '.jar') if rom else None)
    if jar and os.path.isfile(jar):
        java = shutil.which('java')
        if not java:
            die("found %s but no java on PATH" % jar)
        return [java, '-jar', jar]

    die("required tool %r not found: no `%s` on PATH and no jar under "
        "prebuilts/extract-tools/common/smali (searched upward for a ROM root)"
        % (name, name))


def run(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        die("command failed (%d): %s\n%s"
            % (proc.returncode, " ".join(cmd),
               (proc.stderr or proc.stdout).strip()[-4000:]))
    return proc.stdout


def read_uleb128(buf, off):
    result = 0
    shift = 0
    while True:
        b = buf[off]
        off += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, off
        shift += 7


def dex_strings_sorted(dex):
    """Return (num_strings, list_of_unsorted_neighbour_pairs)."""
    import struct

    if not dex.startswith(b"dex\n"):
        die("classes.dex does not start with the DEX magic")
    string_ids_size, string_ids_off = struct.unpack_from("<II", dex, 0x38)
    prev = None
    prev_idx = -1
    unsorted = []
    for i in range(string_ids_size):
        data_off = struct.unpack_from("<I", dex, string_ids_off + 4 * i)[0]
        _u16len, start = read_uleb128(dex, data_off)
        end = dex.index(b"\x00", start)
        # DEX ordering is UTF-16 code-unit order, not raw MUTF-8 byte order.
        # In particular U+0000 is encoded C0 80 and sorts before ASCII.
        encoded = dex[start:end]
        cur = []
        k = 0
        while k < len(encoded):
            c = encoded[k]
            if c < 0x80:
                cur.append(c); k += 1
            elif c & 0xE0 == 0xC0 and k + 1 < len(encoded):
                cur.append(((c & 0x1F) << 6) | (encoded[k+1] & 0x3F)); k += 2
            elif c & 0xF0 == 0xE0 and k + 2 < len(encoded):
                cur.append(((c & 0x0F) << 12) | ((encoded[k+1] & 0x3F) << 6)
                           | (encoded[k+2] & 0x3F)); k += 3
            else:
                die("invalid MUTF-8 in string_ids")
        cur = tuple(cur)
        if len(cur) != _u16len:
            die("DEX UTF-16 length mismatch")
        if prev is not None and prev >= cur:
            unsorted.append((prev_idx, prev, i, cur))
        prev = cur
        prev_idx = i
    return string_ids_size, unsorted


def extract_dex(apk, dest):
    with zipfile.ZipFile(apk) as z:
        if "classes.dex" not in z.namelist():
            die("%s has no classes.dex" % apk)
        with z.open("classes.dex") as src, open(dest, "wb") as out:
            shutil.copyfileobj(src, out)


def build_compat_dex(work, javac, d8, compat_src, android_jar):
    """Compile the MIUI shims and return a path to a classes2.dex.

    MiSound references miui.os.Build, miui.util.FeatureParser and
    miui.util.HapticFeedbackUtil. Those live in MIUI's framework and are not on
    a PixelOS device. ArtifactLoader would fail with NoClassDefFoundError for
    the classes the app touches, so they are compiled here and merged into the
    APK as a secondary dex, which ART loads through the normal multidex path.
    """
    classes = os.path.join(work, "compat-classes")
    dexdir = os.path.join(work, "compat-dex")
    os.makedirs(classes, exist_ok=True)
    os.makedirs(dexdir, exist_ok=True)

    sources = []
    for root, _dirs, files in os.walk(compat_src):
        for name in files:
            if name.endswith(".java"):
                sources.append(os.path.join(root, name))
    if not sources:
        die("no shim sources found under %s" % compat_src)

    run([javac, "-source", "17", "-target", "17", "-Xlint:-options",
         "-classpath", android_jar, "-d", classes] + sorted(sources))

    class_files = []
    for root, _dirs, files in os.walk(classes):
        for name in files:
            if name.endswith(".class"):
                class_files.append(os.path.join(root, name))
    if not class_files:
        die("shim compilation produced no classes")

    run([d8, "--min-api", "33", "--output", dexdir] + sorted(class_files))
    dex = os.path.join(dexdir, "classes.dex")
    if not os.path.isfile(dex):
        die("d8 did not produce %s" % dex)
    return dex


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom-root", help="AOSP tree for tool discovery from an external checkout")
    ap.add_argument("--apk", required=True, help="unmodified MiSound.apk")
    ap.add_argument("--out", required=True, help="patched, signed APK")
    ap.add_argument("--platform-key", required=True)
    ap.add_argument("--platform-cert", required=True)
    ap.add_argument("--build-tools", default=None,
                    help="directory holding zipalign/apksigner/d8")
    ap.add_argument("--shim-src", default=None,
                    help="MiSoundCompat src dir; when given, shims are compiled "
                         "and merged as classes2.dex")
    ap.add_argument("--android-jar", default=None,
                    help="android.jar / framework.jar for compiling the shims")
    ap.add_argument("--keep-work", action="store_true")
    args = ap.parse_args()
    if args.rom_root:
        os.environ["DOLBY_ROM_ROOT"] = args.rom_root

    for path in (args.apk, args.platform_key, args.platform_cert):
        if not os.path.isfile(path):
            die("%s does not exist" % path)

    digest = sha256_file(args.apk)
    if digest != EXPECTED_INPUT_SHA256:
        die("input MiSound.apk hash mismatch\n  expected %s\n  actual   %s\n"
            "This tool only patches the Redwood MiSound build it was written "
            "for. Re-derive the class map and update EXPECTED_INPUT_SHA256 "
            "before using it on a different APK."
            % (EXPECTED_INPUT_SHA256, digest))

    extra = (args.build_tools,) if args.build_tools else ()
    zipalign = find_tool("zipalign", extra)
    apksigner = find_tool("apksigner", extra)
    baksmali = find_jar_tool("baksmali")
    smali = find_jar_tool("smali")

    work = tempfile.mkdtemp(prefix="misound-patch-")
    try:
        compat_dex = None
        if args.shim_src:
            if not args.android_jar:
                die("--shim-src requires --android-jar")
            javac = find_javac()
            d8 = find_tool("d8", extra)
            compat_dex = build_compat_dex(os.path.join(work, "compat"),
                                          javac, d8, args.shim_src, args.android_jar)
            print("patch-misound: built shim dex %s" % compat_dex)
        dex = os.path.join(work, "classes.dex")
        smali_dir = os.path.join(work, "smali")
        extract_dex(args.apk, dex)

        print("patch-misound: disassembling classes.dex")
        os.makedirs(smali_dir)
        run(baksmali + ["d", dex, "-o", smali_dir])

        target_rel = EFFECT_CLASS + ".smali"
        target = os.path.join(smali_dir, target_rel)
        if not os.path.isfile(target):
            die("%s not found; this MiSound build has a different class map"
                % target_rel)

        with open(target, "r", encoding="utf-8") as f:
            body = f.read()

        if SW_IMPL_UUID in body or NEW_TYPE_UUID in body:
            die("target APK already carries the software UUIDs; input looks "
                "pre-patched")

        for old, _new, label in REPLACEMENTS:
            count = body.count(old)
            if count != 1:
                die("expected exactly one %s in %s, found %d"
                    % (label, target_rel, count))

        offenders = []
        for root, _dirs, files in os.walk(smali_dir):
            for name in files:
                if not name.endswith(".smali"):
                    continue
                path = os.path.join(root, name)
                rel = os.path.relpath(path, smali_dir)
                if rel == target_rel:
                    continue
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
                if any(old in text for old, _n, _l in REPLACEMENTS):
                    offenders.append(rel)
        if offenders:
            die("UUID strings also appear outside %s:\n  %s\n"
                "Refusing to patch: those call sites need individual review."
                % (target_rel, "\n  ".join(sorted(offenders)[:10])))

        for old, new, label in REPLACEMENTS:
            print("patch-misound:   %s\n    %s -> %s" % (label, old, new))
        patched = body
        for old, new, _label in REPLACEMENTS:
            patched = patched.replace(old, new)
        with open(target, "w", encoding="utf-8") as f:
            f.write(patched)

        selection_target = os.path.join(smali_dir, SELECTION_CLASS + '.smali')
        try:
            with open(selection_target, 'r', encoding='utf-8') as f:
                selection_body = f.read()
            guarded = guard_effect_selection(selection_body)
            guarded = guard_create_preferences_selection(guarded)
            guarded = guard_destroy_selection(guarded)
        except (OSError, ValueError) as error:
            die('selection null guard: '+str(error))
        with open(selection_target, 'w', encoding='utf-8') as f:
            f.write(guarded)
        print('patch-misound: guarded all three nullable effect-selection consumers')

        geq_target = os.path.join(smali_dir, GEQ_CLASS + '.smali')
        try:
            with open(geq_target, 'r', encoding='utf-8') as f:
                geq_body = guard_dolby_geq(f.read())
        except (OSError, ValueError) as exc:
            die(str(exc))
        with open(geq_target, 'w', encoding='utf-8') as f:
            f.write(geq_body)

        print("patch-misound: reassembling classes.dex")
        patched_dex = os.path.join(work, "classes-patched.dex")
        run(smali + ["a", smali_dir, "-o", patched_dex])

        # The reassembled pool must stay sorted, or ART's binary-search string
        # lookup can miss entries. This is the check that caught the raw
        # byte-patch approach being wrong.
        rebuilt_bytes = open(patched_dex, "rb").read()
        for marker in (SELECTION_GUARD_MARKER, CREATE_GUARD_MARKER, DESTROY_GUARD_MARKER, GEQ_GUARD_MARKER):
            if rebuilt_bytes.count(marker.encode('ascii')) != 1:
                die('guard marker missing/duplicated in rebuilt DEX: '+marker)
        count, unsorted = dex_strings_sorted(rebuilt_bytes)
        if unsorted:
            die("reassembled DEX has an unsorted string_ids table "
                "(%d unsorted neighbours); refusing to ship it" % len(unsorted))
        print("patch-misound: string_ids sorted (%d entries)" % count)

        unsigned = os.path.join(work, "unsigned.apk")
        aligned = os.path.join(work, "aligned.apk")
        with zipfile.ZipFile(args.apk) as zin, \
                zipfile.ZipFile(unsigned, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                if info.filename.startswith("META-INF/") and info.filename.upper().endswith(
                        (".RSA", ".DSA", ".EC", ".SF", "MANIFEST.MF")):
                    continue
                data = (open(patched_dex, "rb").read()
                        if info.filename == "classes.dex"
                        else zin.read(info.filename))
                zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                zi.compress_type = info.compress_type
                zi.external_attr = info.external_attr
                zi.internal_attr = info.internal_attr
                zi.create_system = info.create_system
                zout.writestr(zi, data)

            if compat_dex:
                # Secondary dex holding the MIUI shim classes. ART loads
                # classes2.dex through the ordinary multidex path, so the app's
                # references to miui.os.Build and friends resolve on a device
                # that has no MIUI framework.
                with open(compat_dex, "rb") as f:
                    shim = f.read()
                zi = zipfile.ZipInfo("classes2.dex", date_time=(2009, 1, 1, 0, 0, 0))
                zi.compress_type = zipfile.ZIP_DEFLATED
                zi.external_attr = 0o644 << 16
                zout.writestr(zi, shim)

        run([zipalign, "-f", "-p", "4", unsigned, aligned])
        signed = os.path.join(work, "signed.apk")
        run([apksigner, "sign",
             "--key", args.platform_key,
             "--cert", args.platform_cert,
             "--out", signed, aligned])
        run([apksigner, "verify", signed])

        # Read the UUIDs back out of the signed artifact.
        verify_dex = os.path.join(work, "verify.dex")
        extract_dex(signed, verify_dex)
        blob = open(verify_dex, "rb").read()
        for old, new, label in REPLACEMENTS:
            if new.encode() not in blob:
                die("output APK is missing the patched %s" % label)
            if old.encode() in blob:
                die("output APK still contains the original %s" % label)
        _count, unsorted = dex_strings_sorted(blob)
        if unsorted:
            die("output APK has an unsorted string_ids table")

        if compat_dex:
            with zipfile.ZipFile(signed) as z:
                if "classes2.dex" not in z.namelist():
                    die("output APK is missing the shim classes2.dex")
                shim_blob = z.read("classes2.dex")
            if not shim_blob.startswith(b"dex\n"):
                die("classes2.dex in the output is not a DEX file")

        # Keep a previously verified output intact if any preceding step fails.
        output_dir = os.path.dirname(os.path.abspath(args.out))
        os.makedirs(output_dir, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=output_dir, suffix=".apk", delete=False) as out:
            staged = out.name
        try:
            shutil.copyfile(signed, staged)
            os.replace(staged, args.out)
        finally:
            if os.path.exists(staged): os.unlink(staged)
        print("patch-misound: wrote %s (sha256 %s)"
              % (args.out, sha256_file(args.out)))
    finally:
        if args.keep_work:
            print("patch-misound: work dir kept at %s" % work)
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
