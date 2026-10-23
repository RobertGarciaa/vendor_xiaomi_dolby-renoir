# vendor/xiaomi/dolby-renoir

Dolby Atmos for the Xiaomi Mi 11 Lite 5G (renoir), built from the Redwood
HyperOS Dolby stack.

The goal is a working port, not a reimplementation: Redwood's original MiSound
app provides the UI, profiles and equalizer, and Redwood's software DAP engine
does the audio processing. Only what is required to run that combination on a
PixelOS renoir build has been changed.

## What this is, and what it is not

- **Not** a new Dolby settings UI. MiSound is reused; this repo adds the entry
  point Settings links to, a Quick Settings tile, and the process that keeps
  the effect alive.
- **Not** a POCO sound-alike. A generated renoir static-v1 speaker candidate
  caps positive landscape optimizer gains at zero while preserving existing
  cuts, portrait, headphone and protection settings. It is not acoustically
  calibrated. See [tuning details and rollback](docs/renoir-dax-static-v1.md).
- **Not** Dolby Vision, AC-3/E-AC-3/AC-4 decoding, or the Dolby camera/video
  blobs. This repo is audio effects only.

## Placement and enabling

This repository lives at `vendor/xiaomi/dolby-renoir` in the ROM tree:

```
<rom root>/
└── vendor/xiaomi/dolby-renoir/
```

The renoir device tree enables the port with `TARGET_ENABLE_XIAOMI_DOLBY ?= true`
before inheriting the common product file. Both `device.mk` and `BoardConfig.mk`
use that flag. The integration is intended for this renoir build.

When enabled, `device.mk` inherits `vendor/xiaomi/dolby-renoir/dolby.mk`, and BoardConfig adds:

```make
BOARD_VENDOR_SEPOLICY_DIRS += vendor/xiaomi/dolby-renoir/sepolicy/vendor
SYSTEM_EXT_PUBLIC_SEPOLICY_DIRS += vendor/xiaomi/dolby-renoir/sepolicy/public
```

Public policy declares the DMS HAL attributes. Vendor policy grants DMS access
to `hal_audio_default`, the domain of `/vendor/bin/hw/android.hardware.audio.service`,
which hosts the binderized effects factory on this product. Its Linux UID is
`audioserver`; that does not make its SELinux domain `audioserver`.
No new audioserver coredomain-to-vendor-data rule is needed.

The common makefile installs the stock `sku_shima/audio_effects.xml` only when
Dolby is disabled. When enabled, Dolby installs the extended file exactly once.
This avoids AOSP's first-entry-wins duplicate-copy rule while retaining a working
stock config when the port is disabled.

## Building the apps

`DolbyControl` (Settings entry, tile, effect owner) builds normally from source.

`MiSound` is a proprietary Xiaomi APK. It is not committed. Build the patched
copy once before the ROM build:

```bash
vendor/xiaomi/dolby-renoir/tools/import-misound.sh --dump /path/to/redwood-dump
```

This verifies the input APK against a pinned SHA-256, rewrites the Dolby effect
UUIDs, bundles the MIUI compatibility shims, signs with the platform key and
writes `proprietary/product/app/MiSound/MiSound.apk`. `Android.bp` imports that
file as the `MiSound` module and signs it with the build's platform certificate.
For a checkout outside the ROM tree, add `--rom-root /path/to/rom` to the command.
The previous output APK is replaced only after signature and DEX verification.
Extraction validates the entire dump input before replacing any existing blob.

## Why the app is patched

MiSound asks for implementation UUID `9d4921da-8225-4f29-aefa-39537a04bcaa`
and type `ec7178ec-e5e1-4432-a3f4-4657e6795210`. Those belong to the hardware
DAP. This port ships the software DAP, whose descriptor is
`6ab06da4-c516-4611-8166-452799218539`, with type
`46d279d9-9be7-453d-9d7c-ef937f675587`.

AudioFlinger resolves a create request by matching the UUID registered in
`audio_effects.xml` (`EffectsFactoryState.c:findEffect`), so a request for the
hardware UUID can never reach the software library no matter what the file on
disk is called. Both UUIDs in the app are rewritten.

The rewrite is done on smali, not on raw DEX bytes. A byte patch would leave
the DEX `string_ids` table unsorted (measured: 2 unsorted neighbours) and ART's
`DexFile::FindStringId` binary-searches that table. The smali round trip
rebuilds a sorted pool (41,712 entries, 0 unsorted) and the tool rejects its own
output if it is ever not sorted.

The UUID edit is confined to the single class that constructs the effect
wrapper. Each UUID must appear exactly once, and only there; otherwise the tool
aborts rather than editing an unrelated call path.

## MIUI compatibility

MiSound references three MIUI framework classes that do not exist on PixelOS:

| Class | Members used |
|---|---|
| `miui.os.Build` | `DEVICE`, `IS_TABLET` |
| `miui.util.FeatureParser` | `getString(String)` |
| `miui.util.HapticFeedbackUtil` | `isSupportLinearMotorVibrate()`, `performExtHapticFeedback(int)`, `isSupportExtHapticFeedback(int)`, `performHapticFeedback(int,double)`, `performHapticFeedback(int,double,String)`, `stop()`, constructor |

`packages/MiSoundCompat` implements exactly those members and is merged into
the APK as `classes2.dex`, so ART's normal multidex path loads it. Nothing
else of MIUI is ported. The haptic shim reports that MIUI's extended haptics
are unavailable rather than pretending, and vibrates through the public
Android API where it can.

`tools/verify-misound-deps.py` extracts the reference list from the live APK
and checks it against the compiled shims.

## Effect ownership and persistence

MiSound releases its effect in `onPause()`. In AudioFlinger an effect lives
only while a handle is attached: `ThreadBase::disconnectEffectHandle` removes
the effect when the last handle disconnects. A toggle owned by MiSound's
activity would therefore stop working as soon as the screen closed.

`DolbyControl` holds a session-0 keeper at priority **-1**. MiSound uses **0**,
so the keeper does not take control even if it starts after MiSound. A passive
handle remains attached; reads do not release/recreate it. Explicit QS changes
borrow a priority-0 writer when necessary and release it in `finally`, returning
control to an open MiSound screen. Higher-priority rejection is reported.

Effect parameter/control/enable callbacks capture live state, including readable
per-profile parameters and the 20-band EQ. Route changes observe the engine and
do not overwrite MiSound edits with stale preferences. A new keeper restores
saved state only if it owns control. An audioserver state callback discards dead
handles and restores state after the server returns; it requires the platform
signature permission `MODIFY_AUDIO_ROUTING`.

The framework byte-array GET API returns the number of bytes read, not
`SUCCESS=0`. The wrapper accepts sufficient positive lengths and rejects short
or negative replies. Setters verify engine readback. QS uses live state and
shows `STATE_UNAVAILABLE` if the engine cannot be read.

DolbyControl is a platform-signed system app with `persistent=true`. AOSP marks
apps from scanned system partitions (including system_ext) as system apps; the
original claim that persistence inherently requires `/system` was incorrect.
Its current placement remains `/system/priv-app`. The same partition installs
`etc/permissions/privapp-permissions-dolby-renoir.xml`, explicitly allowing
`MODIFY_AUDIO_ROUTING`. Omitting this entry caused a real enforcing-build
system_server boot loop on 2026-10-23; platform signing is not an exemption
from this build's privileged permission check. MiSound is a non-privileged product
app, also platform-signed. A privapp allowlist does not restrict signature grants
for that app; see [the permission notes](docs/misound-permissions.md).

## Blob provenance

Source OTA:

```
redwood_global-ota_full-OS2.0.17.0.UMSMIXM-user-14.0-4ddcd3c40c
DAX3_3.6.1.6_r1
```

Extracted files, with sizes, are listed in `proprietary-files.sha256sum`:

| File | SHA-256 |
|---|---|
| `vendor/lib64/soundfx/libswdap.so` | `cc3950d8c847d98f0c128fca38f949fdbd1e18cb3ac384ba77c24142efb2a1a0` |
| `vendor/lib64/libdapparamstorage.so` | `f44f1be657cd2363f57c06aa8bc7f6e0089ba5756eab8fbc7388811023128b31` |
| `vendor/lib64/libdlbdsservice.so` | `3122ae6728d5a3c58a1c6d6496988d75fd361672bab25a6a976bd1cc9c241f3f` |
| `vendor/lib64/vendor.dolby.hardware.dms@2.0.so` | `ebe979cf25664a3bfc5a707a27c07eb732a8145c03294bb3b2395c2b4ee7e34e` |
| `vendor/lib64/vendor.dolby.hardware.dms@2.0-impl.so` | `24af1041e3caef59d76e23f235e287be51cd07e387ec299042ead829755db835` |
| `vendor/bin/hw/vendor.dolby.hardware.dms@2.0-service` | `d7da5c108a086c2832da319a6c82bbc06e65ab25a949a7ba2056600ecaffd345` |
| `vendor/etc/dolby/dax-default.xml` | `d7e21ddb0f9d58330b655dd120799b3db46428f6840f87e707239644693a1a9c` |
| `vendor/etc/vintf/manifest/manifest_vendor.dolby.hardware.dms.xml` | `1168fc7a98712222b9e3b9a705c3c06acfe7b287f38fdd3e0cf7793fa8aa4dfd` |
| `vendor/etc/init/vendor.dolby.hardware.dms@2.0-service.rc` | `4e51845631d8f9765761892a5a01a883ebc3c21a9227c251969356c9b60f9d52` |

MiSound input APK (output APK hash varies with ZIP build metadata):

```
product/app/MiSound/MiSound.apk
sha256 1b83fbe1ce4f69b7aff557fa5b07c943b84f37c866a2211360e6aad68ea67e89
```

The renoir `android.hardware.audio.service` (including its effects factory)
is **32-bit**. Ship both ABIs of `libswdap`, `libdapparamstorage`, and the
`vendor.dolby.hardware.dms@2.0` client library. The DMS daemon, implementation,
and service dependencies remain 64-bit. No change to the device audio HAL,
amp firmware, calibration or system libraries is required for this correction.

The earlier report of nine unresolved 32-bit symbols was a checker bug: its
lookup searched `vendor/lib64` before `vendor/lib` for either ABI. The corrected
check selects only the requested ELF class/machine and uses the runtime APEX
for Bionic symlinks. Same-ABI checks resolve the three original 32-bit blobs;
this is static evidence, not a substitute for effect creation and playback.

After building, before flashing, run:

```bash
python3 vendor/xiaomi/dolby-renoir/tools/check-product-install.py \
    --product-out out/target/product/renoir
```

The product check must find the system DolbyControl permission allowlist and
the DAP library matching the actual audio service. Check transitive ELF
symbols with `tools/check-elf-deps.py` as described in
[the ABI correction record](docs/effect-host-abi.md).

### Not redistributed

`proprietary/` is git-ignored. The Xiaomi binaries are not redistributed by
this repository; they are reproduced from the OTA by the scripts above and
verified against the hashes recorded here. This repository's source licence
does not apply to those blobs.

## Extraction and regeneration

```bash
# vendor blobs: copies proprietary-files.txt out of the dump and checks every
# file against proprietary-files.sha256sum, then runs the extra checks
./extract-files.py /path/to/redwood-dump
python3 tools/verify-blobs.py --dir .

# patched MiSound
tools/import-misound.sh --dump /path/to/redwood-dump

# regenerate and check the effects XML
python3 tools/gen-audio-effects.py \
    --stock configs/audio/audio_effects_stock.xml \
    --out configs/audio/audio_effects_dolby.xml
python3 tools/gen-audio-effects.py \
    --stock configs/audio/audio_effects_stock.xml \
    --out configs/audio/audio_effects_dolby.xml --check
```

`gen-audio-effects.py` adds exactly one `<library>` and one `<effect>` to the
stock Qualcomm file and refuses to run if either is already present or if any
pre-existing effect would change. Voice-call AEC/NS, the offload bundle and
every existing proxy are preserved.

## Verification status

See `OPENCODE-HANDOFF-DOLBY.md` in the review folder for the per-route table
and the full list of what has and has not been exercised.

The source-level AudioEffect contract test, real-framework Java compilation,
APK patch/sign/DEX verification, blob hashes and effects XML check have passed.
An offline combined-policy test compiles the existing product policy plus Dolby
rules with neverallow assertions enabled. This does not replace Soong's full
split-policy/mapping build or enforcing-device tests.

```bash
python3 tests/test_controller.py
python3 tests/test_tools.py
python3 tests/check_policy.py --android-root /path/to/rom
```

A full ROM build, on-device effect creation, route-specific audio quality,
reboot/audioserver recovery and SELinux enforcement remain unverified. Test
MiSound UI edits → QS toggle → UI edits → close/reopen → reboot, plus speaker,
wired/USB/Bluetooth routes and disable rollback on renoir. Multi-user handover
is not validated; a retiring user's service stops rather than reusing its
preferences as another user's state.

## Disabling and rollback

Set `TARGET_ENABLE_XIAOMI_DOLBY := false` consistently for product and board
configuration (or pass it as a build variable). This omits Dolby modules and its
policy, and restores the stock shima effects file in the common makefile.
Do not merely delete the repository while its enabled inheritance remains.

## Licensing

Source files here are Apache-2.0, matching the LineageOS convention. The
proprietary blobs and the MiSound APK remain Xiaomi's, are not covered by that
licence, and are not distributed by this repository.

## Renoir speaker candidate (static-v1)

Soong derives the installed `/vendor/etc/dolby/dax-default.xml` from the pinned
Redwood input using `renoir_dax_tuning_generator` and `renoir_dax_static_v1`.
The extracted proprietary XML and its recorded hash remain unchanged. Extraction
therefore cannot silently overwrite the candidate policy. Only 13 positive raw
optimizer gains in nine landscape bands become zero. This is an unmeasured
starting point, not a proof of better frequency response or speaker safety.

```sh
python3 tools/gen-renoir-dax.py \
  --stock proprietary/vendor/etc/dolby/dax-default.xml \
  --out /tmp/dax-renoir-static-v1.xml --report /tmp/dax-renoir-static-v1.json
python3 tests/test_dax_tuning.py
```

[Candidate policy, measurement procedure and rollback](docs/renoir-dax-static-v1.md).
No dedicated Android measurement APK has been implemented.
