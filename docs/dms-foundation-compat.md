# renoir DMS legacy foundation boundary

The Redwood DAX3 DMS binary embeds the VNDK30 AHandler layout: a 32-bit
counter at +0x2c, SortedVector at +0x30, derived Looper at +0x58 and DsManager
at +0x60. Android 17's foundation uses a 64-bit counter at +0x30, vector at
+0x38, and a delivery mutex at +0x60. It must not operate on the DMS object.
The current library tries to lock the DsManager pointer as a mutex. On the
reported enforcing user build, the DMS event thread consumed one full CPU and
parameter writes returned success without changing the readback after 1s.
A private provider fixes this boundary without changing platform/audio-HAL
foundation libraries or synthesizing parameter success.

## Inputs and generation

The private foundation is extracted from Redwood's
`system_ext/apex/com.android.vndk.v30.apex`, `apex_payload.img`,
`/lib64/libstagefright_foundation.so`. Its raw SHA256 is
`060ec055a6d4cb5b893d4606953769297c6f6dfcee16490e9410f46b39c4ac29`.
The source APEX observed in OS2.0.17.0.UMSMIXM has SHA256
`495cc145f18650af76ab9b64ac7dfc989c0c4893f03690bf91b60a22fc3250f2`.
The extracted ELF hash, not the APEX packaging hash, is the mandatory pin.
ZIP payload CRC is checked during extraction. Host `debugfs` is required.
VNDK33 and the stock system foundation have different AHandler layouts and
must not be substituted merely because their exported symbols match.

`extract-files.py <redwood-dump>` now also populates the ignored raw input
`proprietary/compat/vndk30/lib64/libstagefright_foundation.so`.
`extract-files.py --verify-only` and `tools/verify-blobs.py` verify this pin.
The original twelve vendor files remain byte-for-byte pinned.

Two Soong genrules use `tools/dms_foundation_compat.py`:

- Provider: change only the foundation DT_SONAME string to
  `libsf_dolby_renoir.so`.
- Consumer: change only libdlbdsservice's DT_NEEDED string for foundation to
  `libsf_dolby_renoir.so`.

Both edits fit in the original dynamic string, leave ELF size and instruction
bytes unchanged, require the exact original SHA256, and reject prepatched
inputs. Build outputs are separate from raw extraction files. The private
provider is ELF64 only because DMS is 64-bit. The 32-bit audio HAL and SW DAP
are unchanged. No global library replacement or linker public-list change is
needed. Only the DMS process dependency graph requests the private SONAME.

## Capability property

`ro.vendor.audio.dolby.dax.support` already had a dedicated exact bool label
and readers. Publishing it from `/vendor/build.prop` uses vendor_init's
property-service identity. Add set_prop for this one restricted property;
read permission does not grant write permission. Do not allow applications or
shell to set it and do not broaden access to all vendor audio properties.
The value remains the product's `true`, rather than a hardcoded UI override.

## Validation and limits

Local checks: original source pins, exact dynamic-tag changes, unchanged
bytes outside the single dynamic string, tampered/reapplied input rejection,
Soong syntax, and matching-ABI strong import closure for both outputs.
These checks are not a ROM build or live proof of linker selection.

After a user build/flash, confirm:

1. Capability value `true`, label `vendor_dolby_config_prop`, no denial.
2. DMS event thread idle without audio/UI work rather than a continuous 100% CPU.
3. Actual DMS mapping uses `libsf_dolby_renoir.so` when inspection is available.
4. UI and QS enable/disable, profile changes and service dumps agree. A DMS
   set request is asynchronous; immediate readback is not an acknowledgement.
   If only short acknowledgement latency remains after the ABI fix, verify
   ordering and use bounded asynchronous completion, not a blind sleep or
   suppression of the mismatch check.
5. Original MiSound GEQ preset/custom changes modify the actual 20 values of
   parameter110, and playback/output behavior changes as expected.
6. Reboot restores confirmed state; no unbounded handler CPU, crashes, leaks
   or changes to unrelated audio routes.

Raw extraction and symbol closure have been checked locally; the updated
native/provider policy has not yet been built into a ROM or tested on device.
