# MiSound entry crash and capability property — 2026-10-23

Observed on the flashed renoir ROM: Settings → Sound & vibration → Dolby Atmos
starts DolbyControl, which opens com.miui.misound.HeadsetSettingsActivity.
MiSound crashes in y.h.w0 with String.equals called on null. The DMS service
and DolbyControl remain alive; AudioFlinger lists the software DAP successfully.

MiSound logs SELinux denial reading ro.vendor.audio.dolby.dax.support, labeled
vendor_audio_prop. It treats Dolby as unavailable, removes the effect selector,
and returns from H0 without giving the still-referenced preference a value.
w0 then dereferences that null value. This is not fixed by clearing app data.

Fixes:

- Give only this exact, boolean capability a dedicated vendor-restricted
  property type. Grant read access to platform_app_all (which includes Android
  17 platform_app_36) and shell. Do not open every vendor_audio_prop to apps,
  make SELinux permissive, or grant property writes.
- Add a scoped y/h.w0 null guard during the pinned MiSound smali fixup. It logs
  the unavailable selection and skips that dependent refresh; it does not choose
  a fake effect or claim engine success. UUID conversion and DEX reassembly/
  sorted string checks remain in place.
- Verify the guard, software UUIDs and compatibility DEX before Soong imports
  MiSound. A stale prebuilt must fail with an import-misound.sh instruction.
- Do not compile a cached policy containing old Dolby rules and describe it as
  validation of changed source. The policy smoke checker now refuses that case.

## Regeneration status of the prebuilt APK

The prebuilt has been regenerated and is no longer stale:

    sha256 07ff845b8e398c5b601623f0674f3fadadf7d10ebd05ee26117c22e650112b1c

The Redwood OTA dump this tree normally imports from is no longer available, so
the pinned original APK was patched directly with tools/patch-misound.py instead
of tools/import-misound.sh --dump. The input hash still matched the pinned value
(1b83fbe1...a67e89). The output carries one guard marker, one software
implementation UUID, one software type UUID, no hardware UUID, both DEX files,
and passes apksigner and the APK contract check.

Updating the APK alone does not install the SELinux fix: both changes must be in
the same build. The source fix does not alter the extracted native blobs or the
DAX tuning XML.

## What has and has not been verified

Verified for this change:

- All module tests pass, and the regenerated APK passes the contract checker.
- The guard is present in the rebuilt classes.dex and sits before the nullable
  String.equals call in y/h.w0; the method is void and its caller already
  treats a missing selection as unavailable, so returning early changes no
  engine state and selects no fallback effect.
- The new property type compiles: checkpolicy accepts the type and its neverallow
  against a combined neverallow policy, and property_info_checker resolves
  u:object_r:vendor_dolby_config_prop:s0.
- The crash and its cause were reproduced on the flashed ROM: MiSound runs as
  platform_app_36 and is denied read on vendor_audio_prop immediately before the
  NullPointerException in y.h.w0.

Not verified, and required before this can be called fixed:

- Full partitioned-policy/neverallow build, ROM build and flash.
- The property resolving to the new type on a booted device, and getprop
  returning true from a platform app rather than an empty value.
- MiSound opening without the crash under enforcing SELinux, and the Dolby
  entry actually controlling audio.

Keep application data; do not use pm clear as a fix.
